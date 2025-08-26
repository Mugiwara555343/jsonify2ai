package routes

import (
	"database/sql"
	"log"

	"github.com/gin-gonic/gin"
)

// RegisterRoutes registers all routes with the given gin engine
func RegisterRoutes(r *gin.Engine, db *sql.DB, docsDir string) {
	// Health endpoint
	RegisterHealth(r)

	// Upload endpoint
	uploadHandler := &UploadHandler{
		DB:      db,
		DocsDir: docsDir,
	}
	r.POST("/upload", uploadHandler.Post)

	log.Printf("[routes] registered upload endpoint with docsDir=%s", docsDir)
}
