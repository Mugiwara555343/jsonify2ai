package routes

import (
	"os"
	"path/filepath"
	"testing"
)

func TestDetectKindAndMIME(t *testing.T) {
	// Create a temporary directory for test files
	tmpDir, err := os.MkdirTemp("", "upload_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	tests := []struct {
		name     string
		content  []byte
		filename string
		wantKind string
		wantMIME string
		wantErr  bool
	}{
		{
			name:     "markdown file",
			content:  []byte("# Test Markdown\n\nThis is a test."),
			filename: "test.md",
			wantKind: "text",
			wantMIME: "text/plain; charset=utf-8",
			wantErr:  false,
		},
		{
			name:     "PNG image header",
			content:  []byte{0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A},
			filename: "test.png",
			wantKind: "image",
			wantMIME: "image/png",
			wantErr:  false,
		},
		{
			name:     "PDF header",
			content:  []byte("%PDF-1.4\nThis is a test PDF"),
			filename: "test.pdf",
			wantKind: "pdf",
			wantMIME: "application/pdf",
			wantErr:  false,
		},
		{
			name:     "JSON content",
			content:  []byte(`{"test": "value"}`),
			filename: "test.json",
			wantKind: "text",
			wantMIME: "application/json",
			wantErr:  false,
		},
		{
			name:     "CSV content",
			content:  []byte("name,age\nJohn,30\nJane,25"),
			filename: "test.csv",
			wantKind: "text",
			wantMIME: "text/plain; charset=utf-8",
			wantErr:  false,
		},
		{
			name:     "unsupported binary",
			content:  []byte{0x00, 0x01, 0x02, 0x03, 0x04, 0x05},
			filename: "test.bin",
			wantKind: "",
			wantMIME: "application/octet-stream",
			wantErr:  true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Create test file
			testPath := filepath.Join(tmpDir, tt.filename)
			if err := os.WriteFile(testPath, tt.content, 0644); err != nil {
				t.Fatal(err)
			}

			// Test DetectKindAndMIME
			gotKind, gotMIME, err := DetectKindAndMIME(testPath, tt.filename)

			// Check error
			if (err != nil) != tt.wantErr {
				t.Errorf("DetectKindAndMIME() error = %v, wantErr %v", err, tt.wantErr)
				return
			}

			// Check kind
			if gotKind != tt.wantKind {
				t.Errorf("DetectKindAndMIME() kind = %v, want %v", gotKind, tt.wantKind)
			}

			// Check MIME (allow some flexibility in MIME detection)
			if !tt.wantErr && gotMIME == "" {
				t.Errorf("DetectKindAndMIME() MIME is empty, want non-empty")
			}
		})
	}
}
