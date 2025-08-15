package http

import (
	"github.com/gin-gonic/gin"
	"github.com/Mugiwara555343/jsonify2ai/api/internal/http/handlers"
)

func SetupRouter() *gin.Engine {
	r := gin.Default()

	// Health endpoint
	r.GET("/health", func(c *gin.Context) {
		c.JSON(200, gin.H{
			"ok": true,
		})
	})

	// Upload endpoint
	r.POST("/upload", handlers.UploadHandler)

	return r
}
