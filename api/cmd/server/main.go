package main

import (
	"log"

	"github.com/Mugiwara555343/jsonify2ai/api/internal/config"
	"github.com/Mugiwara555343/jsonify2ai/api/internal/http"
)

func main() {
	// Load configuration
	cfg := config.Load()

	log.Printf("Starting API server with:")
	log.Printf("  POSTGRES_DSN: %s", cfg.PostgresDSN)
	log.Printf("  QDRANT_URL: %s", cfg.QdrantURL)
	log.Printf("  OLLAMA_URL: %s", cfg.OllamaURL)
	log.Printf("  WORKER_BASE: %s", cfg.WorkerBase)
	log.Printf("  QDRANT_COLLECTION: %s", cfg.QdrantCollection)
	log.Printf("  EMBEDDINGS_MODEL: %s", cfg.EmbeddingsModel)
	log.Printf("  SEARCH_TOPK: %d", cfg.SearchTopK)

	// Setup router
	r := http.SetupRouter(cfg)

	// Start server
	if err := r.Run(":8082"); err != nil {
		log.Fatal(err)
	}
}
