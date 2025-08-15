package main

import (
	"log"
	"os"

	"github.com/Mugiwara555343/jsonify2ai/api/internal/http"
)

func main() {
	// Read environment variables
	postgresDSN := os.Getenv("POSTGRES_DSN")
	qdrantURL := os.Getenv("QDRANT_URL")
	ollamaURL := os.Getenv("OLLAMA_URL")
	workerBase := os.Getenv("WORKER_BASE")
	if workerBase == "" {
		workerBase = "http://worker:8090"
	}

	log.Printf("Starting API server with:")
	log.Printf("  POSTGRES_DSN: %s", postgresDSN)
	log.Printf("  QDRANT_URL: %s", qdrantURL)
	log.Printf("  OLLAMA_URL: %s", ollamaURL)
	log.Printf("  WORKER_BASE: %s", workerBase)

	// Setup router
	r := http.SetupRouter()

	// Start server
	if err := r.Run(":8082"); err != nil {
		log.Fatal(err)
	}
}
