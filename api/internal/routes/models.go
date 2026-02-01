package routes

import (
	"io"
	"net/http"
	"os"
	"time"

	"jsonify2ai/api/internal/config"

	"github.com/gin-gonic/gin"
)

type ModelsHandler struct {
	Config *config.Config
}

func (h *ModelsHandler) getOllamaHost() string {
	// Default to standard Ollama port if not specified
	host := os.Getenv("OLLAMA_HOST")
	if host == "" {
		host = "http://localhost:11434"
	}
	return host
}

// ListModels GET /api/models
func (h *ModelsHandler) ListModels(c *gin.Context) {
	ollamaHost := h.getOllamaHost()
	target := ollamaHost + "/api/tags"

	// Create request with timeout
	client := &http.Client{Timeout: 10 * time.Second}
	req, err := http.NewRequestWithContext(c.Request.Context(), "GET", target, nil)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"ok":     false,
			"error":  "request_creation_failed",
			"detail": err.Error(),
		})
		return
	}

	// Forward request to Ollama
	resp, err := client.Do(req)
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{
			"ok":     false,
			"error":  "ollama_unreachable",
			"detail": err.Error(),
			"host":   ollamaHost,
		})
		return
	}
	defer resp.Body.Close()

	// Parse response
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"ok":     false,
			"error":  "read_response_failed",
			"detail": err.Error(),
		})
		return
	}

	if resp.StatusCode >= 400 {
		c.JSON(resp.StatusCode, gin.H{
			"ok":     false,
			"error":  "ollama_error",
			"detail": string(body),
		})
		return
	}

	// Return raw JSON from Ollama
	// We could unmarshal and re-marshal if we wanted to enforce a schema,
	// but proxying raw JSON is faster and more flexible for now.
	c.Data(resp.StatusCode, "application/json", body)
}
