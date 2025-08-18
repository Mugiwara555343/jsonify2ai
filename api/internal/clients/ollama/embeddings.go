package ollama

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// Client represents an Ollama embeddings client
type Client struct {
	baseURL string
	model   string
	client  *http.Client
}

// EmbeddingRequest represents the request to Ollama embeddings API
type EmbeddingRequest struct {
	Model  string `json:"model"`
	Prompt string `json:"prompt"`
}

// embedResp represents the response from Ollama embeddings API
// Ollama can return either "embedding" or "embeddings" field
type embedResp struct {
	Embedding  []float64 `json:"embedding"`
	Embeddings []float64 `json:"embeddings"`
	NumTokens  int       `json:"num_tokens,omitempty"`
}

// Vector returns the embedding vector, preferring "embedding" over "embeddings"
func (er embedResp) Vector() []float64 {
	if len(er.Embedding) > 0 {
		return er.Embedding
	}
	if len(er.Embeddings) > 0 {
		return er.Embeddings
	}
	return nil
}

// NewClient creates a new Ollama embeddings client
func NewClient(baseURL, model string) *Client {
	return &Client{
		baseURL: baseURL,
		model:   model,
		client: &http.Client{
			Timeout: 15 * time.Second,
		},
	}
}

// EmbedText embeds a single text prompt and returns the embedding vector
func (c *Client) EmbedText(prompt string) ([]float64, error) {
	reqBody := EmbeddingRequest{
		Model:  c.model,
		Prompt: prompt,
	}

	jsonData, err := json.Marshal(reqBody)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	url := fmt.Sprintf("%s/api/embeddings", c.baseURL)
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
		body, err := io.ReadAll(resp.Body)
		if err != nil {
			return nil, fmt.Errorf("ollama embeddings: status %d: failed to read response body", resp.StatusCode)
		}
		return nil, fmt.Errorf("ollama embeddings: status %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}

	var embeddingResp embedResp
	if err := json.NewDecoder(resp.Body).Decode(&embeddingResp); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	vector := embeddingResp.Vector()
	if len(vector) == 0 {
		return nil, fmt.Errorf("no embeddings returned from Ollama")
	}

	return vector, nil
}
