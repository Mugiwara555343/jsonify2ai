package middleware

import (
	"log"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
)

// RateLimiter implements in-memory token bucket rate limiting per key.
type RateLimiter struct {
	uploadPerMin int
	askPerMin    int
	buckets      map[string]*bucketState
	mu           sync.RWMutex
}

type bucketState struct {
	tokens     int
	lastRefill time.Time
	mu         sync.Mutex
}

// NewRateLimiter creates a new rate limiter with the given limits per minute.
func NewRateLimiter(uploadPerMin, askPerMin int) *RateLimiter {
	rl := &RateLimiter{
		uploadPerMin: uploadPerMin,
		askPerMin:    askPerMin,
		buckets:      make(map[string]*bucketState),
	}
	// Cleanup old buckets periodically
	go rl.cleanup()
	return rl
}

// Wrap returns a Gin middleware that rate limits based on route name.
func (rl *RateLimiter) Wrap(route string, next gin.HandlerFunc) gin.HandlerFunc {
	return func(c *gin.Context) {
		// Determine limit based on route
		var limitPerMin int
		switch route {
		case "upload":
			limitPerMin = rl.uploadPerMin
		case "ask":
			limitPerMin = rl.askPerMin
		default:
			// Unknown route, allow through
			next(c)
			return
		}

		// Extract key: bearer token (without "Bearer " prefix) or remote IP
		key := rl.getKey(c)

		// Check rate limit
		if !rl.allow(key, limitPerMin) {
			requestID := c.GetString("request_id")
			log.Printf("[ratelimit] rate limit exceeded: route=%s key=%s request_id=%s", route, key, requestID)
			c.JSON(http.StatusTooManyRequests, gin.H{"ok": false, "error": "rate_limited"})
			c.Header("X-Request-Id", requestID)
			c.Abort()
			return
		}

		// Allow request through
		next(c)
	}
}

// getKey extracts the rate limit key from the request.
// Uses bearer token (without "Bearer " prefix) if present, otherwise remote IP.
func (rl *RateLimiter) getKey(c *gin.Context) string {
	authHeader := c.GetHeader("Authorization")
	if authHeader != "" {
		parts := strings.SplitN(authHeader, " ", 2)
		if len(parts) == 2 && parts[0] == "Bearer" {
			return parts[1]
		}
	}
	// Fallback to IP
	return c.ClientIP()
}

// allow checks if a request is allowed based on token bucket algorithm.
func (rl *RateLimiter) allow(key string, limitPerMin int) bool {
	rl.mu.RLock()
	bucket, exists := rl.buckets[key]
	rl.mu.RUnlock()

	if !exists {
		rl.mu.Lock()
		// Double-check after acquiring write lock
		if bucket, exists = rl.buckets[key]; !exists {
			bucket = &bucketState{
				tokens:     limitPerMin,
				lastRefill: time.Now(),
			}
			rl.buckets[key] = bucket
		}
		rl.mu.Unlock()
	}

	bucket.mu.Lock()
	defer bucket.mu.Unlock()

	// Refill tokens based on elapsed time
	now := time.Now()
	elapsed := now.Sub(bucket.lastRefill)
	if elapsed > 0 {
		// Calculate tokens to add (proportional to elapsed time)
		// Add tokens per second, but don't exceed limit
		tokensToAdd := int(elapsed.Seconds() * float64(limitPerMin) / 60.0)
		if tokensToAdd > 0 {
			bucket.tokens += tokensToAdd
			if bucket.tokens > limitPerMin {
				bucket.tokens = limitPerMin
			}
			bucket.lastRefill = now
		}
	}

	// Check if we have tokens available
	if bucket.tokens > 0 {
		bucket.tokens--
		return true
	}

	return false
}

// cleanup periodically removes old bucket entries to prevent memory leaks.
func (rl *RateLimiter) cleanup() {
	ticker := time.NewTicker(5 * time.Minute)
	defer ticker.Stop()

	for range ticker.C {
		rl.mu.Lock()
		now := time.Now()
		for key, bucket := range rl.buckets {
			bucket.mu.Lock()
			// Remove buckets that haven't been used in 10 minutes and are at full capacity
			// Use max of upload/ask limits as a reasonable check
			maxLimit := rl.uploadPerMin
			if rl.askPerMin > maxLimit {
				maxLimit = rl.askPerMin
			}
			if now.Sub(bucket.lastRefill) > 10*time.Minute && bucket.tokens >= maxLimit {
				delete(rl.buckets, key)
			}
			bucket.mu.Unlock()
		}
		rl.mu.Unlock()
	}
}
