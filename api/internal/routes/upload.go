package routes

import (
	"database/sql"
	"fmt"
	"io"
	"net/http"
	"os"
	"path"
	"path/filepath"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
)

type UploadHandler struct {
	DB      *sql.DB
	DocsDir string
}

// DetectKindAndMIME detects the kind and MIME type of a file
func DetectKindAndMIME(filePath, fileName string) (kind, mime string, err error) {
	// Read first 512 bytes for MIME detection
	file, err := os.Open(filePath)
	if err != nil {
		return "", "", err
	}
	defer file.Close()

	buf := make([]byte, 512)
	n, err := file.Read(buf)
	if err != nil && err != io.EOF {
		return "", "", err
	}
	buf = buf[:n]

	// Detect MIME type
	mime = http.DetectContentType(buf)

	// Map MIME to kind
	switch {
	case strings.HasPrefix(mime, "text/"):
		return "text", mime, nil
	case strings.HasPrefix(mime, "image/"):
		return "image", mime, nil
	case mime == "application/pdf":
		return "pdf", mime, nil
	case strings.HasPrefix(mime, "audio/"):
		return "audio", mime, nil
	case mime == "application/json" || mime == "application/x-yaml":
		return "text", mime, nil
	default:
		// Check file extension for common text formats
		ext := strings.ToLower(filepath.Ext(fileName))
		switch ext {
		case ".md", ".txt", ".csv", ".tsv", ".json", ".jsonl":
			return "text", mime, nil
		default:
			return "", "", fmt.Errorf("unsupported file type: %s", mime)
		}
	}
}

func (h *UploadHandler) Post(c *gin.Context) {
	// Parse multipart form with 25MB limit
	if err := c.Request.ParseMultipartForm(25 << 20); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"ok": false, "error": "failed to parse multipart form"})
		return
	}

	// Get the uploaded file
	file, header, err := c.Request.FormFile("file")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"ok": false, "error": "no file provided"})
		return
	}
	defer file.Close()

	// Generate document ID
	docID := uuid.New()

	// Sanitize filename (strip path separators, keep base name)
	sanitizedFilename := filepath.Base(header.Filename)
	sanitizedFilename = strings.ReplaceAll(sanitizedFilename, "/", "")
	sanitizedFilename = strings.ReplaceAll(sanitizedFilename, "\\", "")

	// Create destination directory
	dest := path.Join(h.DocsDir, docID.String())
	if err := os.MkdirAll(dest, 0755); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"ok": false, "error": "failed to create directory"})
		return
	}

	// Save file to destination
	destPath := path.Join(dest, sanitizedFilename)
	destFile, err := os.Create(destPath)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"ok": false, "error": "failed to create file"})
		return
	}
	defer destFile.Close()

	if _, err := io.Copy(destFile, file); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"ok": false, "error": "failed to save file"})
		return
	}

	// Detect MIME type and kind
	kind, mime, err := DetectKindAndMIME(destPath, sanitizedFilename)
	if err != nil {
		// Clean up saved file
		os.RemoveAll(dest)
		c.JSON(http.StatusUnsupportedMediaType, gin.H{"ok": false, "error": err.Error()})
		return
	}

	// Get file size
	fileInfo, err := os.Stat(destPath)
	if err != nil {
		os.RemoveAll(dest)
		c.JSON(http.StatusInternalServerError, gin.H{"ok": false, "error": "failed to get file info"})
		return
	}

	// Insert into database if available
	if h.DB != nil {
		_, err = h.DB.Exec(
			"INSERT INTO documents (id, filename, kind, size_bytes, mime) VALUES ($1, $2, $3, $4, $5)",
			docID, sanitizedFilename, kind, fileInfo.Size(), mime,
		)
		if err != nil {
			// Clean up saved file
			os.RemoveAll(dest)
			c.JSON(http.StatusInternalServerError, gin.H{"ok": false, "error": "failed to save to database"})
			return
		}
	} else {
		// Log warning but continue without database
		c.Writer.Header().Set("X-Database-Status", "disconnected")
	}

	c.JSON(http.StatusOK, gin.H{
		"ok":          true,
		"document_id": docID.String(),
	})
}
