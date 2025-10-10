package config

import (
	"os"
	"strconv"
	"time"
)

type Config struct {
	Port        string
	PostgresDSN string
	QdrantURL   string
	OllamaURL   string
	WorkerBase  string
	DocsDir     string

	// HTTP timeouts (in seconds)
	HTTPTimeoutSeconds   int
	UploadTimeoutSeconds int
	SearchTimeoutSeconds int
	AskTimeoutSeconds    int

	// CORS configuration
	CORSOrigins string

	// Server configuration
	GinMode string
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func Load() *Config {
	config := &Config{
		Port:        getenv("PORT_API", "8082"),
		PostgresDSN: getenv("POSTGRES_DSN", ""),
		QdrantURL:   getenv("QDRANT_URL", ""),
		OllamaURL:   getenv("OLLAMA_URL", ""),
		WorkerBase:  getenv("WORKER_BASE", ""),
		DocsDir:     getenv("DOCS_DIR", "./data/documents"),

		// Default timeouts (in seconds)
		HTTPTimeoutSeconds:   15,
		UploadTimeoutSeconds: 60,
		SearchTimeoutSeconds: 15,
		AskTimeoutSeconds:    30,

		// Default CORS origins
		CORSOrigins: "http://localhost:5173,http://127.0.0.1:5173",

		// Default server config
		GinMode: "release",
	}

	// Override with environment variables if present
	if v := os.Getenv("HTTP_TIMEOUT_SECONDS"); v != "" {
		if timeout, err := strconv.Atoi(v); err == nil {
			config.HTTPTimeoutSeconds = timeout
		}
	}

	if v := os.Getenv("UPLOAD_TIMEOUT_SECONDS"); v != "" {
		if timeout, err := strconv.Atoi(v); err == nil {
			config.UploadTimeoutSeconds = timeout
		}
	}

	if v := os.Getenv("SEARCH_TIMEOUT_SECONDS"); v != "" {
		if timeout, err := strconv.Atoi(v); err == nil {
			config.SearchTimeoutSeconds = timeout
		}
	}

	if v := os.Getenv("ASK_TIMEOUT_SECONDS"); v != "" {
		if timeout, err := strconv.Atoi(v); err == nil {
			config.AskTimeoutSeconds = timeout
		}
	}

	if v := os.Getenv("CORS_ORIGINS"); v != "" {
		config.CORSOrigins = v
	}

	if v := os.Getenv("GIN_MODE"); v != "" {
		config.GinMode = v
	}

	return config
}

// GetHTTPTimeout returns the HTTP timeout as a time.Duration
func (c *Config) GetHTTPTimeout() time.Duration {
	return time.Duration(c.HTTPTimeoutSeconds) * time.Second
}

// GetUploadTimeout returns the upload timeout as a time.Duration
func (c *Config) GetUploadTimeout() time.Duration {
	return time.Duration(c.UploadTimeoutSeconds) * time.Second
}

// GetSearchTimeout returns the search timeout as a time.Duration
func (c *Config) GetSearchTimeout() time.Duration {
	return time.Duration(c.SearchTimeoutSeconds) * time.Second
}

// GetAskTimeout returns the ask timeout as a time.Duration
func (c *Config) GetAskTimeout() time.Duration {
	return time.Duration(c.AskTimeoutSeconds) * time.Second
}
