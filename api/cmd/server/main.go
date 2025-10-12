package main

import (
	"database/sql"
	"fmt"
	"log"
	"net/http"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"

	"jsonify2ai/api/internal/config"
	"jsonify2ai/api/internal/db"
	"jsonify2ai/api/internal/routes"
)

func main() {
	cfg := config.Load()

	// Initialize database connection
	var dbConn *sql.DB
	if cfg.PostgresDSN != "" {
		var err error
		dbConn, err = db.Open(cfg.PostgresDSN)
		if err != nil {
			log.Printf("[api] warning: failed to connect to database: %v", err)
			log.Printf("[api] continuing without database connection")
		} else {
			defer dbConn.Close()
			log.Printf("[api] connected to database successfully")
		}
	} else {
		log.Printf("[api] no database connection configured")
	}

	r := gin.New()
	r.Use(gin.Recovery())

	// Do not trust any upstream proxies by default.
	// This silences the "You trusted all proxies" warning and is safer for dev.
	if err := r.SetTrustedProxies(nil); err != nil {
		log.Printf("trusted proxies config error: %v", err)
	}

	// Request-ID middleware
	r.Use(func(c *gin.Context) {
		// Generate or use existing Request-ID
		requestID := c.GetHeader("X-Request-Id")
		if requestID == "" {
			requestID = uuid.New().String()
		}
		c.Header("X-Request-Id", requestID)
		c.Set("request_id", requestID)
		c.Next()
	})

	// simple request log (tiny)
	r.Use(func(c *gin.Context) {
		c.Next()
		status := c.Writer.Status()
		requestID := c.GetString("request_id")
		log.Printf("[api] %s %s -> %d (req-id: %s)", c.Request.Method, c.Request.URL.Path, status, requestID)
	})

	// Register all routes
	routes.RegisterRoutes(r, dbConn, cfg.DocsDir, cfg.WorkerBase, cfg)

	addr := fmt.Sprintf(":%s", cfg.Port)
	log.Printf("[api] starting on %s (PG=%s Qdrant=%s Ollama=%s DocsDir=%s Worker=%s)",
		addr, nz(cfg.PostgresDSN), nz(cfg.QdrantURL), nz(cfg.OllamaURL), nz(cfg.DocsDir), nz(cfg.WorkerBase))

	// Configure server with timeouts
	server := &http.Server{
		Addr:         addr,
		Handler:      routes.WithCORS(r, cfg),
		ReadTimeout:  cfg.GetAPIReadTimeout(),
		WriteTimeout: cfg.GetAPIWriteTimeout(),
	}

	log.Fatal(server.ListenAndServe())
}

func nz(s string) string {
	if s == "" {
		return "-"
	}
	return s
}
