package routes

import (
	"bytes"
	"context"
	"io"
	"net/http"
	"net/url"
	"os"
	"time"

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

func addAskSearchRoutes(r *gin.Engine, base string) {
	w := workerURL(base)

	// GET /search?q=...&k=...
	r.GET("/search", func(c *gin.Context) {

		q := c.Query("q")
		if q == "" {
			c.String(http.StatusBadRequest, "missing q")
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

		ctx, cancel := context.WithTimeout(c.Request.Context(), 15*time.Second)
		defer cancel()
		req, _ := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)

		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			c.String(http.StatusBadGateway, err.Error())
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

		ctx, cancel := context.WithTimeout(c.Request.Context(), 30*time.Second)
		defer cancel()
		req, _ := http.NewRequestWithContext(ctx, http.MethodPost, w+"/ask", bytes.NewReader(body))
		req.Header.Set("Content-Type", "application/json")

		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			c.String(http.StatusBadGateway, err.Error())
			return
		}
		defer resp.Body.Close()

		c.Header("Content-Type", "application/json")
		c.Status(resp.StatusCode)
		_, _ = io.Copy(c.Writer, resp.Body)
	})
}
