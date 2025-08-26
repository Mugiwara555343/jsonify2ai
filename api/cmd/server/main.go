package main

import (
	"database/sql"
	"fmt"
	"log"

	"github.com/gin-gonic/gin"

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

	// simple request log (tiny)
	r.Use(func(c *gin.Context) {
		c.Next()
		status := c.Writer.Status()
		log.Printf("%s %s -> %d", c.Request.Method, c.Request.URL.Path, status)
	})

	// Register all routes
	routes.RegisterRoutes(r, dbConn, cfg.DocsDir)

	addr := fmt.Sprintf(":%s", cfg.Port)
	log.Printf("[api] starting on %s (PG=%s Qdrant=%s Ollama=%s DocsDir=%s)",
		addr, nz(cfg.PostgresDSN), nz(cfg.QdrantURL), nz(cfg.OllamaURL), nz(cfg.DocsDir))

	if err := r.Run(addr); err != nil {
		log.Fatal(err)
	}
}

func nz(s string) string {
	if s == "" {
		return "-"
	}
	return s
}
