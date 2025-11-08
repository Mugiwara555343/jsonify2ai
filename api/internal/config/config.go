package config

import (
	"os"
	"strconv"
	"strings"
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

	// API-specific timeouts (in milliseconds)
	APIReadTimeoutMs  int
	APIWriteTimeoutMs int
	APIProxyTimeoutMs int

	// CORS configuration
	CORSOrigins string

	// Server configuration
	GinMode string

	// Authentication
	APIAuthToken    string
	WorkerAuthToken string
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

		// Default API timeouts (in milliseconds)
		APIReadTimeoutMs:  15000,
		APIWriteTimeoutMs: 15000,
		APIProxyTimeoutMs: 60000,

		// Default CORS origins
		CORSOrigins: "http://localhost:5173,http://127.0.0.1:5173",

		// Default server config
		GinMode: "release",

		// Authentication (optional)
		APIAuthToken: "",
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

	// Override API timeouts from environment
	if v := os.Getenv("API_READ_TIMEOUT_MS"); v != "" {
		if timeout, err := strconv.Atoi(v); err == nil {
			config.APIReadTimeoutMs = timeout
		}
	}

	if v := os.Getenv("API_WRITE_TIMEOUT_MS"); v != "" {
		if timeout, err := strconv.Atoi(v); err == nil {
			config.APIWriteTimeoutMs = timeout
		}
	}

	if v := os.Getenv("API_PROXY_TIMEOUT_MS"); v != "" {
		if timeout, err := strconv.Atoi(v); err == nil {
			config.APIProxyTimeoutMs = timeout
		}
	}

	if v := os.Getenv("CORS_ALLOWED_ORIGINS"); v != "" {
		config.CORSOrigins = v
	} else if v := os.Getenv("CORS_ORIGINS"); v != "" {
		config.CORSOrigins = v
	}

	if v := os.Getenv("GIN_MODE"); v != "" {
		config.GinMode = v
	}

	// Load auth token with fallback: API_AUTH_TOKEN (primary) -> AUTH_TOKEN (legacy)
	if v := getEnvAny([]string{"API_AUTH_TOKEN", "AUTH_TOKEN"}); v != "" {
		config.APIAuthToken = v
	}

	// Load worker auth token
	if v := getEnvAny([]string{"WORKER_AUTH_TOKEN"}); v != "" {
		config.WorkerAuthToken = v
	}

	return config
}

// getEnvAny returns the first non-empty environment variable value from the given keys
func getEnvAny(keys []string) string {
	for _, k := range keys {
		if v := os.Getenv(k); v != "" {
			// Trim whitespace
			if trimmed := strings.TrimSpace(v); trimmed != "" {
				return trimmed
			}
		}
	}
	return ""
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

// GetAPIReadTimeout returns the API read timeout as a time.Duration
func (c *Config) GetAPIReadTimeout() time.Duration {
	return time.Duration(c.APIReadTimeoutMs) * time.Millisecond
}

// GetAPIWriteTimeout returns the API write timeout as a time.Duration
func (c *Config) GetAPIWriteTimeout() time.Duration {
	return time.Duration(c.APIWriteTimeoutMs) * time.Millisecond
}

// GetAPIProxyTimeout returns the API proxy timeout as a time.Duration
func (c *Config) GetAPIProxyTimeout() time.Duration {
	return time.Duration(c.APIProxyTimeoutMs) * time.Millisecond
}
