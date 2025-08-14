package main

import (
	"log"
	"os"

	"github.com/gin-gonic/gin"
)

func main() {
	// Read environment variables
	postgresDSN := os.Getenv("POSTGRES_DSN")
	qdrantURL := os.Getenv("QDRANT_URL")
	ollamaURL := os.Getenv("OLLAMA_URL")

	log.Printf("Starting API server with:")
	log.Printf("  POSTGRES_DSN: %s", postgresDSN)
	log.Printf("  QDRANT_URL: %s", qdrantURL)
	log.Printf("  OLLAMA_URL: %s", ollamaURL)

	r := gin.Default()

	// Health endpoint
	r.GET("/health", func(c *gin.Context) {
		c.JSON(200, gin.H{
			"ok": true,
		})
	})

	// Start server
	if err := r.Run(":8080"); err != nil {
		log.Fatal(err)
	}
}
