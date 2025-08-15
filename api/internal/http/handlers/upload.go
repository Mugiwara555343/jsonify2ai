package handlers

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"unicode/utf8"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
)

const (
	maxFileSize = 5 * 1024 * 1024 // 5MB
)

type WorkerResponse struct {
	Ok         bool   `json:"ok"`
	Chunks     int    `json:"chunks"`
	Embedded   int    `json:"embedded"`
	Upserted   int    `json:"upserted"`
	Collection string `json:"collection"`
	Error      string `json:"error,omitempty"`
}

type UploadResponse struct {
	Ok           bool           `json:"ok"`
	DocumentID   string         `json:"document_id"`
	Filename     string         `json:"filename"`
	Size         int64          `json:"size"`
	Mime         string         `json:"mime"`
	Worker       WorkerResponse `json:"worker"`
}

func UploadHandler(c *gin.Context) {
	// Parse multipart form with 5MB limit
	if err := c.Request.ParseMultipartForm(maxFileSize); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"ok": false, "error": "Failed to parse form"})
		return
	}
	defer c.Request.MultipartForm.RemoveAll()

	// Get the file from form
	file, header, err := c.Request.FormFile("file")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"ok": false, "error": "No file provided"})
		return
	}
	defer file.Close()

	// Check file size
	if header.Size > maxFileSize {
		c.JSON(http.StatusRequestEntityTooLarge, gin.H{"ok": false, "error": "File too large (>5MB)"})
		return
	}

	// Generate document ID
	documentID := uuid.New().String()

	// Create data directory
	dataDir := filepath.Join(".", "data", "documents", documentID)
	if err := os.MkdirAll(dataDir, 0755); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"ok": false, "error": "Failed to create directory"})
		return
	}

	// Save file to disk
	filePath := filepath.Join(dataDir, header.Filename)
	dst, err := os.Create(filePath)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"ok": false, "error": "Failed to save file"})
		return
	}
	defer dst.Close()

	// Copy file content
	written, err := io.Copy(dst, file)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"ok": false, "error": "Failed to write file"})
		return
	}

	// Read file content as UTF-8 text
	file.Seek(0, 0) // Reset to beginning
	content, err := io.ReadAll(file)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"ok": false, "error": "Failed to read file content"})
		return
	}

	// Ensure valid UTF-8
	if !utf8.Valid(content) {
		content = bytes.ToValidUTF8(content, []byte(""))
	}

	// Detect MIME type
	mimeType := detectMimeType(header.Filename, content)

	// Call worker service
	workerBase := os.Getenv("WORKER_BASE")
	if workerBase == "" {
		workerBase = "http://worker:8090"
	}

	workerURL := workerBase + "/process/text"
	workerPayload := map[string]interface{}{
		"document_id": documentID,
		"text":        string(content),
	}

	workerResp, err := callWorkerService(workerURL, workerPayload)
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"ok": false, "error": fmt.Sprintf("Worker service error: %v", err)})
		return
	}

	// Build response
	response := UploadResponse{
		Ok:         true,
		DocumentID: documentID,
		Filename:   header.Filename,
		Size:       written,
		Mime:       mimeType,
		Worker:     *workerResp,
	}

	c.JSON(http.StatusOK, response)
}

func callWorkerService(url string, payload map[string]interface{}) (*WorkerResponse, error) {
	jsonData, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal payload: %v", err)
	}

	resp, err := http.Post(url, "application/json", bytes.NewBuffer(jsonData))
	if err != nil {
		return nil, fmt.Errorf("failed to call worker: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("worker returned status %d: %s", resp.StatusCode, string(body))
	}

	var workerResp WorkerResponse
	if err := json.NewDecoder(resp.Body).Decode(&workerResp); err != nil {
		return nil, fmt.Errorf("failed to decode worker response: %v", err)
	}

	return &workerResp, nil
}

func detectMimeType(filename string, content []byte) string {
	ext := strings.ToLower(filepath.Ext(filename))
	
	switch ext {
	case ".txt":
		return "text/plain"
	case ".md":
		return "text/markdown"
	case ".json":
		return "application/json"
	case ".xml":
		return "application/xml"
	case ".html", ".htm":
		return "text/html"
	case ".css":
		return "text/css"
	case ".js":
		return "application/javascript"
	default:
		// Try to detect from content
		if len(content) > 0 && content[0] == '{' {
			return "application/json"
		}
		if len(content) > 0 && content[0] == '<' {
			return "text/html"
		}
		return "text/plain"
	}
}
