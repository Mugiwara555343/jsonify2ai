package qdrant

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

// Client represents a Qdrant search client
type Client struct {
	baseURL    string
	collection string
	client     *http.Client
}

// SearchRequest represents the request to Qdrant search API
type SearchRequest struct {
	Vector       []float64 `json:"vector"`
	Limit        int       `json:"limit"`
	WithPayload  bool      `json:"with_payload"`
	WithVector   bool      `json:"with_vector"`
}

// SearchResponse represents the response from Qdrant search API
type SearchResponse struct {
	Result []SearchResult `json:"result"`
}

// SearchResult represents a single search result from Qdrant
type SearchResult struct {
	ID      string                 `json:"id"`
	Score   float64                `json:"score"`
	Payload map[string]interface{} `json:"payload"`
}

// NewClient creates a new Qdrant search client
func NewClient(baseURL, collection string) *Client {
	return &Client{
		baseURL:    baseURL,
		collection: collection,
		client: &http.Client{
			Timeout: 15 * time.Second,
		},
	}
}

// SearchPoints searches for similar vectors in the collection
func (c *Client) SearchPoints(vector []float64, limit int) ([]SearchResult, error) {
	reqBody := SearchRequest{
		Vector:      vector,
		Limit:       limit,
		WithPayload: true,
		WithVector:  false,
	}
	
	jsonData, err := json.Marshal(reqBody)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}
	
	url := fmt.Sprintf("%s/collections/%s/points/search", c.baseURL, c.collection)
	req, err := http.NewRequest("POST", url, bytes.NewBuffer(jsonData))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}
	
	req.Header.Set("Content-Type", "application/json")
	
	resp, err := c.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to make request: %w", err)
	}
	defer resp.Body.Close()
	
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("Qdrant API returned status %d", resp.StatusCode)
	}
	
	var searchResp SearchResponse
	if err := json.NewDecoder(resp.Body).Decode(&searchResp); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}
	
	return searchResp.Result, nil
}
