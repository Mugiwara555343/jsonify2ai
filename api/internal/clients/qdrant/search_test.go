package qdrant

import (
	"encoding/json"
	"testing"
)

func TestSearchRequest_Marshal(t *testing.T) {
	vector := []float64{0.1, 0.2, 0.3}
	limit := 5

	req := SearchRequest{
		Vector:      vector,
		Limit:       limit,
		WithPayload: true,
		WithVector:  false,
	}

	jsonData, err := json.Marshal(req)
	if err != nil {
		t.Fatalf("Failed to marshal SearchRequest: %v", err)
	}

	// Verify the JSON structure
	var unmarshaled map[string]interface{}
	if err := json.Unmarshal(jsonData, &unmarshaled); err != nil {
		t.Fatalf("Failed to unmarshal JSON: %v", err)
	}

	// Check required fields
	if unmarshaled["vector"] == nil {
		t.Error("vector field missing from JSON")
	}

	if unmarshaled["limit"] == nil {
		t.Error("limit field missing from JSON")
	}

	if unmarshaled["with_payload"] != true {
		t.Error("with_payload should be true")
	}

	if unmarshaled["with_vector"] != false {
		t.Error("with_vector should be false")
	}
}
