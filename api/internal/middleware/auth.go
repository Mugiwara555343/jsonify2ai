package middleware

import (
	"log"
	"strings"

	"jsonify2ai/api/internal/config"

	"github.com/gin-gonic/gin"
)

// AuthMiddleware creates a middleware that checks for bearer token authentication
func AuthMiddleware(cfg *config.Config) gin.HandlerFunc {
	return func(c *gin.Context) {
		// Local mode: bypass all auth checks
		if cfg.AuthMode == "local" {
			log.Printf("[jsonify2ai-debug] auth bypass: local mode for %s %s", c.Request.Method, c.Request.URL.Path)
			c.Next()
			return
		}

		// Strict mode: require authentication even if token is not configured
		// (this indicates a misconfiguration - strict mode needs a token)
		if cfg.AuthMode == "strict" {
			if cfg.APIAuthToken == "" {
				log.Printf("[jsonify2ai] ERROR: AUTH_MODE=strict but APIAuthToken is not configured")
				c.JSON(500, gin.H{"ok": false, "error": "auth_misconfigured", "detail": "AUTH_MODE=strict requires APIAuthToken to be set"})
				c.Abort()
				return
			}
			// Continue to bearer token validation below
		} else {
			// Backward compatibility: if no auth token is configured, skip authentication
			if cfg.APIAuthToken == "" {
				c.Next()
				return
			}
		}

		// Get the Authorization header
		authHeader := c.GetHeader("Authorization")

		if authHeader == "" {
			c.JSON(401, gin.H{"ok": false, "error": "missing_bearer"})
			c.Abort()
			return
		}

		// Check if it's a Bearer token
		parts := strings.SplitN(authHeader, " ", 2)
		if len(parts) != 2 || parts[0] != "Bearer" {
			c.JSON(401, gin.H{"ok": false, "error": "missing_bearer"})
			c.Abort()
			return
		}

		// Validate the token
		if parts[1] != cfg.APIAuthToken {
			c.JSON(401, gin.H{"ok": false, "error": "invalid_token"})
			c.Abort()
			return
		}

		// Token is valid, continue
		c.Next()
	}
}
