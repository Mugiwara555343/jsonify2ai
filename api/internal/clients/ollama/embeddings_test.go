package ollama

import (
	"encoding/json"
	"reflect"
	"testing"
)

func TestEmbedResp_Vector(t *testing.T) {
	tests := []struct {
		name     string
		jsonData string
		expected []float64
	}{
		{
			name:     "embedding field",
			jsonData: `{"embedding":[1,2,3]}`,
			expected: []float64{1, 2, 3},
		},
		{
			name:     "embeddings field",
			jsonData: `{"embeddings":[4,5]}`,
			expected: []float64{4, 5},
		},
		{
			name:     "both fields, embedding takes precedence",
			jsonData: `{"embedding":[1,2,3],"embeddings":[4,5]}`,
			expected: []float64{1, 2, 3},
		},
		{
			name:     "neither field",
			jsonData: `{"num_tokens":10}`,
			expected: nil,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var resp embedResp
			err := json.Unmarshal([]byte(tt.jsonData), &resp)
			if err != nil {
				t.Fatalf("Failed to unmarshal JSON: %v", err)
			}

			result := resp.Vector()
			if !reflect.DeepEqual(result, tt.expected) {
				t.Errorf("Vector() = %v, want %v", result, tt.expected)
			}
		})
	}
}
