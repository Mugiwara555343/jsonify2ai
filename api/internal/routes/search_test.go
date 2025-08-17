package routes

import (
	"testing"

	"github.com/Mugiwara555343/jsonify2ai/api/internal/clients/qdrant"
)

func TestMapQdrantResult(t *testing.T) {
	tests := []struct {
		name     string
		input    qdrant.SearchResult
		expected *SearchResult
	}{
		{
			name: "complete payload",
			input: qdrant.SearchResult{
				ID:    "test-id",
				Score: 0.85,
				Payload: map[string]interface{}{
					"text":        "sample text content",
					"document_id": "doc-123",
					"caption":     "sample caption",
					"path":        "/path/to/file.txt",
				},
			},
			expected: &SearchResult{
				Kind:        "text",
				Score:       0.85,
				Text:        "sample text content",
				Caption:     "sample caption",
				DocumentID:  "doc-123",
				SourcePath:  "/path/to/file.txt",
			},
		},
		{
			name: "minimal payload",
			input: qdrant.SearchResult{
				ID:    "test-id-2",
				Score: 0.75,
				Payload: map[string]interface{}{
					"text":        "another text",
					"document_id": "doc-456",
				},
			},
			expected: &SearchResult{
				Kind:       "text",
				Score:      0.75,
				Text:       "another text",
				DocumentID: "doc-456",
			},
		},
		{
			name: "missing text",
			input: qdrant.SearchResult{
				ID:    "test-id-3",
				Score: 0.65,
				Payload: map[string]interface{}{
					"document_id": "doc-789",
				},
			},
			expected: nil, // Should return nil when text is missing
		},
		{
			name: "missing document_id",
			input: qdrant.SearchResult{
				ID:    "test-id-4",
				Score: 0.55,
				Payload: map[string]interface{}{
					"text": "some text",
				},
			},
			expected: nil, // Should return nil when document_id is missing
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := mapQdrantResult(tt.input)
			
			if tt.expected == nil {
				if result != nil {
					t.Errorf("Expected nil result, got %+v", result)
				}
				return
			}
			
			if result == nil {
				t.Errorf("Expected result %+v, got nil", tt.expected)
				return
			}
			
			if result.Kind != tt.expected.Kind {
				t.Errorf("Kind mismatch: expected %s, got %s", tt.expected.Kind, result.Kind)
			}
			
			if result.Score != tt.expected.Score {
				t.Errorf("Score mismatch: expected %f, got %f", tt.expected.Score, result.Score)
			}
			
			if result.Text != tt.expected.Text {
				t.Errorf("Text mismatch: expected %s, got %s", tt.expected.Text, result.Text)
			}
			
			if result.DocumentID != tt.expected.DocumentID {
				t.Errorf("DocumentID mismatch: expected %s, got %s", tt.expected.DocumentID, result.DocumentID)
			}
			
			if result.Caption != tt.expected.Caption {
				t.Errorf("Caption mismatch: expected %s, got %s", tt.expected.Caption, result.Caption)
			}
			
			if result.SourcePath != tt.expected.SourcePath {
				t.Errorf("SourcePath mismatch: expected %s, got %s", tt.expected.SourcePath, result.SourcePath)
			}
		})
	}
}
