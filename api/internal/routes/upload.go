package routes

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"mime/multipart"
	"net/http"
	"net/textproto"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
)

// UploadHandler forwards incoming multipart data directly to the worker /upload endpoint.
// No local filesystem writes, no DB writes. The worker ingests from its dropzone.
type UploadHandler struct{}

func (h *UploadHandler) Post(c *gin.Context) {
	// Resolve worker base URL (env WORKER_URL takes precedence; default to http://worker:8090)
	workerBase := ""
	if v := os.Getenv("WORKER_URL"); v != "" {
		workerBase = v
	} else {
		workerBase = "http://worker:8090"
	}
	workerURL := fmt.Sprintf("%s/upload", workerBase)

	// Parse incoming multipart *without* buffering whole file to disk
	// (Gin already parsed up to its memory limit; we re-stream parts)
	if err := c.Request.ParseMultipartForm(32 << 20); err != nil && err != http.ErrNotMultipart {
		c.JSON(http.StatusBadRequest, gin.H{"ok": false, "error": "invalid multipart", "detail": err.Error()})
		return
	}

	// Build outgoing multipart body
	var body bytes.Buffer
	mw := multipart.NewWriter(&body)

	// Copy all form fields (non-file)
	for key, vals := range c.Request.PostForm {
		for _, v := range vals {
			_ = mw.WriteField(key, v)
		}
	}

	// Copy file parts
	form, _ := c.MultipartForm()
	if form != nil {
		for key, files := range form.File {
			for _, fh := range files {
				src, err := fh.Open()
				if err != nil {
					_ = mw.Close()
					c.JSON(http.StatusBadRequest, gin.H{"ok": false, "error": "failed to open file", "detail": err.Error()})
					return
				}
				defer src.Close()
				// Preserve original filename; attach a request-id so worker logs can correlate
				partHeader := textproto.MIMEHeader{}
				partHeader.Set("Content-Disposition", fmt.Sprintf(`form-data; name="%s"; filename="%s"`, key, fh.Filename))
				if fh.Header.Get("Content-Type") != "" {
					partHeader.Set("Content-Type", fh.Header.Get("Content-Type"))
				}
				pw, err := mw.CreatePart(partHeader)
				if err != nil {
					_ = mw.Close()
					c.JSON(http.StatusInternalServerError, gin.H{"ok": false, "error": "failed to create multipart part", "detail": err.Error()})
					return
				}
				if _, err := io.Copy(pw, src); err != nil {
					_ = mw.Close()
					c.JSON(http.StatusBadRequest, gin.H{"ok": false, "error": "failed to stream file", "detail": err.Error()})
					return
				}
			}
		}
	}
	_ = mw.Close()

	// Forward to worker
	req, err := http.NewRequestWithContext(context.Background(), http.MethodPost, workerURL, &body)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"ok": false, "error": "forward build failed", "detail": err.Error()})
		return
	}
	req.Header.Set("Content-Type", mw.FormDataContentType())
	// Tag a request id for traceability
	req.Header.Set("X-Request-Id", uuid.New().String())

	client := &http.Client{Timeout: 60 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"ok": false, "error": "worker unreachable", "detail": err.Error()})
		return
	}
	defer resp.Body.Close()

	// Read worker JSON once so we can both relay it and trigger processing
	var buf bytes.Buffer
	if _, err := io.Copy(&buf, resp.Body); err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"ok": false, "error": "worker read failed", "detail": err.Error()})
		return
	}

	// Relay the worker's JSON response
	c.Status(resp.StatusCode)
	_, _ = io.Copy(c.Writer, bytes.NewReader(buf.Bytes()))

	// Best-effort: parse worker JSON and trigger processing in the background
	type workerUpload struct {
		Ok       bool   `json:"ok"`
		Path     string `json:"path"`
		Filename string `json:"filename"`
		MIME     string `json:"mime"`
	}
	var wu workerUpload
	if err := json.Unmarshal(buf.Bytes(), &wu); err != nil {
		log.Printf("[api] upload: worker JSON parse failed: %v", err)
		return
	}
	if wu.Path == "" && wu.Filename == "" {
		return // nothing to process
	}

	// Infer kind from extension
	name := wu.Filename
	if name == "" {
		name = filepath.Base(wu.Path)
	}
	ext := strings.ToLower(filepath.Ext(name))
	kind := ""
	switch ext {
	case ".txt", ".md", ".csv", ".json":
		kind = "text"
	case ".pdf":
		kind = "pdf"
	case ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif":
		kind = "image"
	case ".wav", ".mp3", ".m4a", ".flac", ".ogg":
		kind = "audio"
	default:
		// fallback on MIME if available
		if strings.HasPrefix(wu.MIME, "text/") {
			kind = "text"
		} else if wu.MIME == "application/pdf" {
			kind = "pdf"
		} else if strings.HasPrefix(wu.MIME, "image/") {
			kind = "image"
		} else if strings.HasPrefix(wu.MIME, "audio/") {
			kind = "audio"
		}
	}
	if kind == "" {
		log.Printf("[api] upload: unknown kind for %q (mime=%q); skipping process trigger", name, wu.MIME)
		return
	}

	// POST to worker /process/<kind> with {"path": wu.Path}
	processURL := fmt.Sprintf("%s/process/%s", workerBase, kind)
	bodyJSON, _ := json.Marshal(map[string]string{"path": wu.Path})
	go func() {
		ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
		defer cancel()
		req2, err := http.NewRequestWithContext(ctx, http.MethodPost, processURL, bytes.NewReader(bodyJSON))
		if err != nil {
			log.Printf("[api] process build failed: %v", err)
			return
		}
		req2.Header.Set("Content-Type", "application/json")
		if resp2, err := client.Do(req2); err != nil {
			log.Printf("[api] process call failed: %v", err)
		} else {
			_ = resp2.Body.Close()
			log.Printf("[api] process %s triggered for %s (status=%d)", kind, name, resp2.StatusCode)
		}
	}()
}
