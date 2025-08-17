package routes

import (
	"fmt"
	"log"
	"net/http"
	"strings"

	"github.com/Mugiwara555343/jsonify2ai/api/internal/clients/ollama"
	"github.com/Mugiwara555343/jsonify2ai/api/internal/clients/qdrant"
	"github.com/Mugiwara555343/jsonify2ai/api/internal/config"
	"github.com/gin-gonic/gin"
)

// SearchResult represents a search result in the API response
type SearchResult struct {
	Kind       string  `json:"kind"`
	Score      float64 `json:"score"`
	Text       string  `json:"text"`
	Caption    string  `json:"caption,omitempty"`
	DocumentID string  `json:"document_id"`
	SourcePath string  `json:"source_path,omitempty"`
}

// SearchResponse represents the search API response
type SearchResponse struct {
	OK         bool           `json:"ok"`
	Results    []SearchResult `json:"results"`
	Collection string         `json:"collection"`
	Count      int            `json:"count"`
}

// SearchHandler handles the GET /search endpoint
func SearchHandler(cfg *config.Config, ollamaClient *ollama.Client, qdrantClient *qdrant.Client) gin.HandlerFunc {
	return func(c *gin.Context) {
		query := strings.TrimSpace(c.Query("q"))
		if query == "" {
			log.Printf("Search request missing query parameter")
			c.JSON(http.StatusBadRequest, gin.H{
				"ok":    false,
				"error": "Missing required query parameter 'q'",
			})
			return
		}

		log.Printf("Processing search request for query: %s", query)

		// Step 1: Embed the query using Ollama
		embedding, err := ollamaClient.EmbedText(query)
		if err != nil {
			log.Printf("Failed to embed query: %v", err)
			c.JSON(http.StatusBadGateway, gin.H{
				"ok":    false,
				"error": fmt.Sprintf("Failed to process query embedding: %v", err),
			})
			return
		}

		// Step 2: Search Qdrant for similar vectors
		results, err := qdrantClient.SearchPoints(embedding, cfg.SearchTopK)
		if err != nil {
			log.Printf("Failed to search Qdrant: %v", err)
			c.JSON(http.StatusBadGateway, gin.H{
				"ok":    false,
				"error": "Failed to search vector database",
			})
			return
		}

		// Step 3: Map Qdrant results to API response format
		searchResults := make([]SearchResult, 0, len(results))
		for _, result := range results {
			searchResult := mapQdrantResult(result)
			if searchResult != nil {
				searchResults = append(searchResults, *searchResult)
			}
		}

		// Step 4: Return response
		response := SearchResponse{
			OK:         true,
			Results:    searchResults,
			Collection: cfg.QdrantCollection,
			Count:      len(searchResults),
		}

		c.JSON(http.StatusOK, response)
	}
}

// mapQdrantResult maps a Qdrant search result to the API response format
func mapQdrantResult(result qdrant.SearchResult) *SearchResult {
	// Extract required fields from payload
	text, ok := result.Payload["text"].(string)
	if !ok || text == "" {
		return nil // Skip results without text
	}

	documentID, ok := result.Payload["document_id"].(string)
	if !ok || documentID == "" {
		return nil // Skip results without document_id
	}

	searchResult := &SearchResult{
		Kind:       "text",
		Score:      result.Score,
		Text:       text,
		DocumentID: documentID,
	}

	// Extract optional fields
	if caption, ok := result.Payload["caption"].(string); ok && caption != "" {
		searchResult.Caption = caption
	}

	if path, ok := result.Payload["path"].(string); ok && path != "" {
		searchResult.SourcePath = path
	}

	return searchResult
}
