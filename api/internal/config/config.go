package config

import (
	"os"
)

type Config struct {
	Port        string
	PostgresDSN string
	QdrantURL   string
	OllamaURL   string
	WorkerBase  string
	DocsDir     string
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func Load() *Config {
	return &Config{
		Port:        getenv("PORT_API", "8082"),
		PostgresDSN: getenv("POSTGRES_DSN", ""),
		QdrantURL:   getenv("QDRANT_URL", ""),
		OllamaURL:   getenv("OLLAMA_URL", ""),
		WorkerBase:  getenv("WORKER_BASE", ""),
		DocsDir:     getenv("DOCS_DIR", "./data/documents"),
	}
}
