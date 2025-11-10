# Data Model

## Unified JSON Chunk Schema

All processed documents are stored as JSONL rows with the following schema:

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Qdrant point ID (UUID string) |
| `document_id` | string | Deterministic UUID5 based on document hash |
| `kind` | string | Content type: `text`, `pdf`, `image`, `audio`, `csv`, `html`, `docx` |
| `path` | string | Original file path (relative to repo root) |
| `idx` | integer | Chunk index within document (0-based) |
| `text` | string | Chunk text content (or image caption) |
| `meta` | object | Metadata object (see below) |

### Meta Object

```json
{
  "ext": ".pdf",
  "size": 12345,
  "sha256": "abc123..."
}
```

- `ext`: File extension
- `size`: File size in bytes
- `sha256`: SHA-256 hash of original file bytes

### Deterministic IDs

- `document_id` is generated using UUID5 with a namespace seed
- Same file content always produces the same `document_id`
- Enables idempotent processing (safe to re-run)

### Example JSONL Row

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "document_id": "3fddcff6-90bb-5160-8eae-28200792d6a8",
  "kind": "text",
  "path": "data/documents/3fddcff6-90bb-5160-8eae-28200792d6a8/example.md",
  "idx": 0,
  "text": "This is the first chunk of text from the document...",
  "meta": {
    "ext": ".md",
    "size": 2048,
    "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  }
}
```

## Collections

### jsonify2ai_chunks_768
- Text chunks from: `.txt`, `.md`, `.pdf`, `.docx`, `.csv`, `.html`, `.json`, audio transcripts
- Vector dimension: 768
- Distance metric: Cosine

### jsonify2ai_images_768
- Image embeddings from: `.jpg`, `.png`, `.webp`
- Vector dimension: 768
- Distance metric: Cosine
- Text field contains image caption (if `IMAGES_CAPTION=1`)

## Export Formats

### JSONL Export
- One JSON object per line
- All chunks for a given `document_id`
- Fields match schema above

### ZIP Archive
Contains:
- `export_<document_id>.jsonl` - All chunks
- `manifest.json` - Document metadata:
  ```json
  {
    "document_id": "uuid",
    "collection": "jsonify2ai_chunks_768",
    "chunks_count": 6,
    "images_count": 0,
    "exported_at": "2024-01-01T00:00:00Z"
  }
  ```
- Original source file (if available under `data/`)
