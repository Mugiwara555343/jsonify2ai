package routes

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"net/url"
	"os"
	"time"

	"github.com/gin-gonic/gin"
)

// RegisterRoutes registers all routes with the given gin engine
func RegisterRoutes(r *gin.Engine, db *sql.DB, docsDir string, workerBase string) {
	// Basic API-only health (liveness)
	RegisterHealth(r)

	// Upload endpoint - now forwards directly to worker
	r.POST("/upload", (&UploadHandler{}).Post)
	log.Printf("[routes] registered upload endpoint with docsDir=%s", docsDir)

	// Resolve worker base URL (env WORKER_URL takes precedence; default to http://worker:8090)
	getWorkerBase := func() string {
		if v := os.Getenv("WORKER_URL"); v != "" {
			return v
		}
		if workerBase != "" {
			return workerBase
		}
		return "http://worker:8090"
	}

	// Shared HTTP client with sane timeout
	httpClient := &http.Client{Timeout: 15 * time.Second}

	// Helper: forward an HTTP response back to Gin
	forwardResp := func(c *gin.Context, resp *http.Response) {
		defer resp.Body.Close()
		ct := resp.Header.Get("Content-Type")
		if ct == "" {
			ct = "application/json"
		}
		c.Status(resp.StatusCode)
		c.Header("Content-Type", ct)
		_, _ = io.Copy(c.Writer, resp.Body)
	}

	// --------------------------- /health/full ---------------------------
	// Stronger health: verifies worker is reachable & returns ok:true
	r.GET("/health/full", func(c *gin.Context) {
		type workerStatus struct {
			OK bool `json:"ok"`
		}
		apiOK := true // this code path only runs if API itself is up
		workerOK := false

		target := getWorkerBase() + "/status"
		req, err := http.NewRequestWithContext(c.Request.Context(), "GET", target, nil)
		if err == nil {
			if resp, err := httpClient.Do(req); err == nil {
				defer resp.Body.Close()
				var ws workerStatus
				_ = json.NewDecoder(resp.Body).Decode(&ws)
				workerOK = resp.StatusCode < 500 && ws.OK
			}
		}

		c.JSON(http.StatusOK, gin.H{
			"ok":         apiOK && workerOK,
			"api":        apiOK,
			"worker":     workerOK,
			"worker_url": getWorkerBase(),
		})
	})

	// ----------------------------- /status -----------------------------
	// GET /status → forward to worker /status
	r.GET("/status", func(c *gin.Context) {
		target := getWorkerBase() + "/status"
		req, err := http.NewRequestWithContext(c.Request.Context(), "GET", target, nil)
		if err != nil {
			c.JSON(http.StatusBadGateway, gin.H{"ok": false, "error": err.Error()})
			return
		}
		resp, err := httpClient.Do(req)
		if err != nil {
			c.JSON(http.StatusBadGateway, gin.H{"ok": false, "error": err.Error()})
			return
		}
		forwardResp(c, resp)
	})

	// ----------------------------- /search -----------------------------
	// GET /search?q=...&k=...&document_id=...&kind=...&path=...
	r.GET("/search", func(c *gin.Context) {
		q := c.Query("q")
		if q == "" {
			c.JSON(http.StatusBadRequest, gin.H{"ok": false, "error": "missing q"})
			return
		}

		qb := url.Values{}
		qb.Set("q", q)
		if v := c.Query("k"); v != "" {
			qb.Set("k", v)
		}
		// optional scoping filters
		if v := c.Query("document_id"); v != "" {
			qb.Set("document_id", v)
		}
		if v := c.Query("kind"); v != "" {
			qb.Set("kind", v)
		}
		if v := c.Query("path"); v != "" {
			qb.Set("path", v)
		}

		target := getWorkerBase() + "/search?" + qb.Encode()
		req, err := http.NewRequestWithContext(c.Request.Context(), "GET", target, nil)
		if err != nil {
			c.JSON(http.StatusBadGateway, gin.H{"ok": false, "error": err.Error()})
			return
		}
		resp, err := httpClient.Do(req)
		if err != nil {
			c.JSON(http.StatusBadGateway, gin.H{"ok": false, "error": err.Error()})
			return
		}
		forwardResp(c, resp)
	})

	// ------------------------------- /ask -------------------------------
	// POST /ask → forward JSON body to worker /ask
	r.POST("/ask", func(c *gin.Context) {
		body, err := io.ReadAll(c.Request.Body)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"ok": false, "error": "invalid body"})
			return
		}
		target := getWorkerBase() + "/ask"
		req, err := http.NewRequestWithContext(context.Background(), "POST", target, bytes.NewReader(body))
		if err != nil {
			c.JSON(http.StatusBadGateway, gin.H{"ok": false, "error": err.Error()})
			return
		}
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("Accept", "application/json")

		resp, err := httpClient.Do(req)
		if err != nil {
			c.JSON(http.StatusBadGateway, gin.H{"ok": false, "error": err.Error()})
			return
		}
		forwardResp(c, resp)
	})
}
