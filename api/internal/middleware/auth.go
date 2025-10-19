package middleware

import (
	"strings"

	"jsonify2ai/api/internal/config"

	"github.com/gin-gonic/gin"
)

// AuthMiddleware creates a middleware that checks for bearer token authentication
func AuthMiddleware(cfg *config.Config) gin.HandlerFunc {
	return func(c *gin.Context) {
		// If no auth token is configured, skip authentication
		if cfg.APIAuthToken == "" {
			c.Next()
			return
		}

		// Get the Authorization header
		authHeader := c.GetHeader("Authorization")
		if authHeader == "" {
			c.JSON(401, gin.H{"ok": false, "error": "unauthorized"})
			c.Abort()
			return
		}

		// Check if it's a Bearer token
		parts := strings.SplitN(authHeader, " ", 2)
		if len(parts) != 2 || parts[0] != "Bearer" {
			c.JSON(401, gin.H{"ok": false, "error": "unauthorized"})
			c.Abort()
			return
		}

		// Validate the token
		if parts[1] != cfg.APIAuthToken {
			c.JSON(401, gin.H{"ok": false, "error": "unauthorized"})
			c.Abort()
			return
		}

		// Token is valid, continue
		c.Next()
	}
}
