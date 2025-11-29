package routes

import (
	"database/sql"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"

	"jsonify2ai/api/internal/config"
	"jsonify2ai/api/internal/middleware"

	"github.com/gin-gonic/gin"
)

func withCORS(next http.Handler, cfg *config.Config) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		origin := r.Header.Get("Origin")

		// Parse allowed origins from config
		allowedOrigins := make(map[string]bool)
		if cfg.CORSOrigins != "" {
			origins := strings.Split(cfg.CORSOrigins, ",")
			for _, o := range origins {
				allowedOrigins[strings.TrimSpace(o)] = true
			}
		}

		if allowedOrigins[origin] {
			w.Header().Set("Access-Control-Allow-Origin", origin)
			w.Header().Set("Vary", "Origin")
			w.Header().Set("Access-Control-Allow-Credentials", "true")
			w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")
			w.Header().Set("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
		}
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

// WithCORS wraps a Gin engine with CORS middleware
func WithCORS(ginEngine *gin.Engine, cfg *config.Config) http.Handler {
	return withCORS(ginEngine, cfg)
}

// RegisterRoutes registers all routes with the given gin engine
func RegisterRoutes(r *gin.Engine, db *sql.DB, docsDir string, workerBase string, cfg *config.Config) {
	// Basic API-only health (liveness)
	RegisterHealth(r)

	// Initialize rate limiter from environment
	uploadPerMin := 10
	if v := os.Getenv("RATE_UPLOAD_PER_MIN"); v != "" {
		if parsed, err := strconv.Atoi(v); err == nil {
			uploadPerMin = parsed
		}
	}
	askPerMin := 30
	if v := os.Getenv("RATE_ASK_PER_MIN"); v != "" {
		if parsed, err := strconv.Atoi(v); err == nil {
			askPerMin = parsed
		}
	}
	rateLimiter := middleware.NewRateLimiter(uploadPerMin, askPerMin)
	log.Printf("[routes] rate limiter initialized: upload=%d/min ask=%d/min", uploadPerMin, askPerMin)

	// Upload endpoint - now forwards directly to worker (protected + rate limited)
	r.POST("/upload",
		middleware.AuthMiddleware(cfg),
		rateLimiter.Wrap("upload", (&UploadHandler{Config: cfg}).Post))
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

	// Shared HTTP client with configurable timeout
	httpClient := &http.Client{Timeout: cfg.GetAPIProxyTimeout()}

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
			c.JSON(http.StatusBadGateway, gin.H{"ok": false, "error": "request build failed", "detail": err.Error()})
			return
		}
		// Forward Request-ID to worker
		if requestID := c.GetString("request_id"); requestID != "" {
			req.Header.Set("X-Request-Id", requestID)
		}
		resp, err := httpClient.Do(req)
		if err != nil {
			c.JSON(http.StatusBadGateway, gin.H{"ok": false, "error": "worker unreachable", "detail": err.Error()})
			return
		}
		forwardResp(c, resp)
	})

	// ----------------------------- /search -----------------------------
	// GET /search?q=...&k=...&document_id=...&kind=...&path=... (protected)
	r.GET("/search", middleware.AuthMiddleware(cfg), func(c *gin.Context) {
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
			c.JSON(http.StatusBadGateway, gin.H{"ok": false, "error": "request build failed", "detail": err.Error()})
			return
		}
		// Forward Request-ID to worker
		if requestID := c.GetString("request_id"); requestID != "" {
			req.Header.Set("X-Request-Id", requestID)
		}
		resp, err := httpClient.Do(req)
		if err != nil {
			c.JSON(http.StatusBadGateway, gin.H{"ok": false, "error": "worker unreachable", "detail": err.Error()})
			return
		}
		forwardResp(c, resp)
	})

	// ----------------------------- /export -----------------------------
	// GET /export?document_id=...&collection=... (protected)
	r.GET("/export", middleware.AuthMiddleware(cfg), func(c *gin.Context) {
		// proxy GET /export preserving raw query
		target := getWorkerBase() + "/export?" + c.Request.URL.RawQuery
		req, err := http.NewRequestWithContext(c.Request.Context(), "GET", target, nil)
		if err != nil {
			c.JSON(http.StatusBadGateway, gin.H{"ok": false, "error": "request build failed", "detail": err.Error()})
			return
		}
		// Forward Request-ID to worker
		if requestID := c.GetString("request_id"); requestID != "" {
			req.Header.Set("X-Request-Id", requestID)
		}
		// Forward worker auth token if configured
		if cfg.WorkerAuthToken != "" {
			req.Header.Set("Authorization", "Bearer "+cfg.WorkerAuthToken)
		}
		resp, err := httpClient.Do(req)
		if err != nil {
			c.JSON(http.StatusBadGateway, gin.H{"ok": false, "error": "worker unreachable", "detail": err.Error()})
			return
		}
		forwardResp(c, resp)
	})

	// ------------------------- /export/archive -------------------------
	// GET /export/archive?document_id=...&collection=... (protected)
	r.GET("/export/archive", middleware.AuthMiddleware(cfg), func(c *gin.Context) {
		// proxy GET /export/archive preserving raw query
		target := getWorkerBase() + "/export/archive?" + c.Request.URL.RawQuery
		req, err := http.NewRequestWithContext(c.Request.Context(), "GET", target, nil)
		if err != nil {
			c.JSON(http.StatusBadGateway, gin.H{"ok": false, "error": "request build failed", "detail": err.Error()})
			return
		}
		// Forward Request-ID to worker
		if requestID := c.GetString("request_id"); requestID != "" {
			req.Header.Set("X-Request-Id", requestID)
		}
		// Forward worker auth token if configured
		if cfg.WorkerAuthToken != "" {
			req.Header.Set("Authorization", "Bearer "+cfg.WorkerAuthToken)
		}
		resp, err := httpClient.Do(req)
		if err != nil {
			c.JSON(http.StatusBadGateway, gin.H{"ok": false, "error": "worker unreachable", "detail": err.Error()})
			return
		}
		// forward content-type (application/zip) and body
		forwardResp(c, resp)
	})

	// ----------------------------- /documents -----------------------------
	// GET /documents → forward to worker /documents
	r.GET("/documents", func(c *gin.Context) {
		target := getWorkerBase() + "/documents"
		req, err := http.NewRequestWithContext(c.Request.Context(), "GET", target, nil)
		if err != nil {
			c.JSON(http.StatusBadGateway, gin.H{"ok": false, "error": "request build failed", "detail": err.Error()})
			return
		}
		// Forward Request-ID to worker
		if requestID := c.GetString("request_id"); requestID != "" {
			req.Header.Set("X-Request-Id", requestID)
		}
		resp, err := httpClient.Do(req)
		if err != nil {
			c.JSON(http.StatusBadGateway, gin.H{"ok": false, "error": "worker unreachable", "detail": err.Error()})
			return
		}
		forwardResp(c, resp)
	})

	// Add ask/search routes with config
	// addAskSearchRoutes(r, getWorkerBase(), cfg) // Commented out due to duplicate /search route

	// ----------------------------- /ask -----------------------------
	// POST /ask (protected + rate limited)
	r.POST("/ask",
		middleware.AuthMiddleware(cfg),
		rateLimiter.Wrap("ask", (&AskHandler{Config: cfg}).Post))
}
