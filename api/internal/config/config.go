package config

import (
	"os"
	"strconv"
)

// Config holds all configuration values
type Config struct {
	PostgresDSN       string
	QdrantURL         string
	OllamaURL         string
	WorkerBase        string
	QdrantCollection  string
	EmbeddingsModel   string
	SearchTopK        int
}

// Load loads configuration from environment variables
func Load() *Config {
	topK, _ := strconv.Atoi(getEnv("SEARCH_TOPK", "5"))
	
	return &Config{
		PostgresDSN:      getEnv("POSTGRES_DSN", ""),
		QdrantURL:        getEnv("QDRANT_URL", "http://host.docker.internal:6333"),
		OllamaURL:        getEnv("OLLAMA_URL", "http://host.docker.internal:11434"),
		WorkerBase:       getEnv("WORKER_BASE", "http://worker:8090"),
		QdrantCollection: getEnv("QDRANT_COLLECTION", "jsonify2ai_chunks"),
		EmbeddingsModel:  getEnv("EMBEDDINGS_MODEL", "nomic-embed-text"),
		SearchTopK:       topK,
	}
}

// getEnv gets an environment variable with a default value
func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}
