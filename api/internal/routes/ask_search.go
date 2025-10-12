package routes

import (
	"bytes"
	"context"
	"io"
	"net/http"
	"net/url"
	"os"

	"jsonify2ai/api/internal/config"

	"github.com/gin-gonic/gin"
)

func workerURL(base string) string {
	if base != "" {
		return base
	}
	if v := os.Getenv("WORKER_URL"); v != "" {
		return v
	}
	// default for docker compose (API -> worker container)
	return "http://worker:8090"
}

func addAskSearchRoutes(r *gin.Engine, base string, cfg *config.Config) {
	w := workerURL(base)

	// GET /search?q=...&k=...
	r.GET("/search", func(c *gin.Context) {

		q := c.Query("q")
		if q == "" {
			c.JSON(http.StatusBadRequest, gin.H{"ok": false, "error": "missing q"})
			return
		}
		k := c.DefaultQuery("k", "5")
		path := c.Query("path")
		docID := c.Query("document_id")
		params := url.Values{}
		params.Set("q", q)
		params.Set("k", k)
		if path != "" {
			params.Set("path", path)
		}
		if docID != "" {
			params.Set("document_id", docID)
		}
		u := w + "/search?" + params.Encode()

		ctx, cancel := context.WithTimeout(c.Request.Context(), cfg.GetSearchTimeout())
		defer cancel()
		req, _ := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
		// Forward Request-ID to worker
		if requestID := c.GetString("request_id"); requestID != "" {
			req.Header.Set("X-Request-Id", requestID)
		}

		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			c.JSON(http.StatusBadGateway, gin.H{"ok": false, "error": "worker unreachable", "detail": err.Error()})
			return
		}
		defer resp.Body.Close()

		c.Header("Content-Type", "application/json")
		c.Status(resp.StatusCode)
		_, _ = io.Copy(c.Writer, resp.Body)
	})

	// POST /ask  (json body forwarded as-is)
	r.POST("/ask", func(c *gin.Context) {
		body, _ := io.ReadAll(c.Request.Body)
		_ = c.Request.Body.Close()

		ctx, cancel := context.WithTimeout(c.Request.Context(), cfg.GetAskTimeout())
		defer cancel()
		req, _ := http.NewRequestWithContext(ctx, http.MethodPost, w+"/ask", bytes.NewReader(body))
		req.Header.Set("Content-Type", "application/json")
		// Forward Request-ID to worker
		if requestID := c.GetString("request_id"); requestID != "" {
			req.Header.Set("X-Request-Id", requestID)
		}

		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			c.JSON(http.StatusBadGateway, gin.H{"ok": false, "error": "worker unreachable", "detail": err.Error()})
			return
		}
		defer resp.Body.Close()

		c.Header("Content-Type", "application/json")
		c.Status(resp.StatusCode)
		_, _ = io.Copy(c.Writer, resp.Body)
	})
}
