package http

import (
	"github.com/gin-gonic/gin"
	"github.com/Mugiwara555343/jsonify2ai/api/internal/http/handlers"
	"github.com/Mugiwara555343/jsonify2ai/api/internal/routes"
	"github.com/Mugiwara555343/jsonify2ai/api/internal/config"
	"github.com/Mugiwara555343/jsonify2ai/api/internal/clients/ollama"
	"github.com/Mugiwara555343/jsonify2ai/api/internal/clients/qdrant"
)

func SetupRouter(cfg *config.Config) *gin.Engine {
	r := gin.Default()

	// Initialize clients
	ollamaClient := ollama.NewClient(cfg.OllamaURL, cfg.EmbeddingsModel)
	qdrantClient := qdrant.NewClient(cfg.QdrantURL, cfg.QdrantCollection)

	// Health endpoint
	r.GET("/health", func(c *gin.Context) {
		c.JSON(200, gin.H{
			"ok": true,
		})
	})

	// Upload endpoint
	r.POST("/upload", handlers.UploadHandler)

	// Search endpoint
	r.GET("/search", routes.SearchHandler(cfg, ollamaClient, qdrantClient))

	return r
}
