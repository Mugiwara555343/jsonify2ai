# API Reference

## Overview

jsonify2ai exposes two main services:
- **API Service** (Port 8082) - Public-facing Go API with authentication
- **Worker Service** (Port 8090) - Internal FastAPI service for processing

All protected endpoints require `Authorization: Bearer <API_AUTH_TOKEN>` header.

---

## API Service (Port 8082)

### Health & Status

**GET /health**
- Basic API health check
- No authentication required
- Returns: `{"ok": true}`

**GET /health/full**
- Full health check (includes worker reachability)
- No authentication required
- Returns: `{"ok": true, "api": true, "worker": true, "worker_url": "..."}`

**GET /status**
- Forwarded from worker service
- No authentication required
- Returns worker status with counts, telemetry, and LLM status

### File Operations

**POST /upload**
- Upload and process a file
- **Auth required**: Yes
- **Content-Type**: `multipart/form-data`
- **Body**: `file` field with file data
- **Response**:
  ```json
  {
    "ok": true,
    "document_id": "uuid",
    "chunks": 6,
    "upserted": 6,
    "collection": "jsonify2ai_chunks_768"
  }
  ```

### Search

**GET /search**
- Semantic vector search
- **Auth required**: Yes
- **Query params**:
  - `q` (required) - Search query
  - `kind` (optional) - Filter by type: `text`, `pdf`, `image`, `audio`
  - `k` (optional) - Number of results (default: 5)
  - `document_id` (optional) - Filter by document
  - `path` (optional) - Filter by file path
- **Response**:
  ```json
  {
    "ok": true,
    "results": [
      {
        "id": "point_id",
        "score": 0.85,
        "text": "chunk content",
        "path": "data/documents/...",
        "document_id": "uuid",
        "kind": "text",
        "idx": 0
      }
    ]
  }
  ```

### Ask (Q&A)

**POST /ask**
- Ask questions with optional LLM synthesis
- **Auth required**: Yes
- **Content-Type**: `application/json`
- **Body**:
  ```json
  {
    "query": "What is this document about?",
    "kind": "text",
    "limit": 6
  }
  ```
- **Response**:
  ```json
  {
    "ok": true,
    "mode": "llm",
    "model": "llama3.1:8b",
    "final": "Synthesized answer...",
    "sources": [...],
    "answers": [...]
  }
  ```

### Documents

**GET /documents**
- List all documents with metadata
- **Auth required**: No
- **Response**:
  ```json
  [
    {
      "document_id": "uuid",
      "kinds": ["text"],
      "paths": ["data/documents/..."],
      "counts": {"chunks": 6}
    }
  ]
  ```

### Export

**GET /export**
- Export document as JSONL
- **Auth required**: Yes
- **Query params**:
  - `document_id` (required) - Document UUID
  - `collection` (optional) - `jsonify2ai_chunks_768` or `jsonify2ai_images_768` (auto-detects if omitted)
- **Response**: JSONL text stream
- **Headers**: `Content-Disposition: attachment; filename="export_<id>.jsonl"`

**GET /export/archive**
- Export document as ZIP archive
- **Auth required**: Yes
- **Query params**: Same as `/export`
- **Response**: ZIP file containing:
  - `export_<document_id>.jsonl` - All chunks
  - `manifest.json` - Document metadata
  - Original source file (if available)
- **Headers**: `Content-Type: application/zip`, `X-Collection-Used: <collection>`

---

## Worker Service (Port 8090)

**Note**: Worker endpoints are typically accessed via the API service. Direct access requires `WORKER_AUTH_TOKEN`.

**GET /health** - Health check
**GET /status** - System status with LLM reachability
**POST /process/{text\|pdf\|image\|audio}** - Process files
**GET /search** - Semantic search
**POST /ask** - Ask questions with LLM

---

## Examples

### Upload File

```bash
# curl
curl -X POST http://localhost:8082/upload \
  -H "Authorization: Bearer $API_AUTH_TOKEN" \
  -F "file=@document.pdf"
```

```powershell
# PowerShell
$headers = @{ Authorization = "Bearer $env:API_AUTH_TOKEN" }
Invoke-RestMethod -Uri "http://localhost:8082/upload" `
  -Method Post -Headers $headers -Form @{ file = Get-Item "document.pdf" }
```

### Search

```bash
curl "http://localhost:8082/search?q=vector%20search&kind=text&k=5" \
  -H "Authorization: Bearer $API_AUTH_TOKEN"
```

### Export ZIP

```bash
DOC="<document_id>"
curl -L "http://localhost:8082/export/archive?document_id=$DOC&collection=jsonify2ai_chunks_768" \
  -H "Authorization: Bearer $API_AUTH_TOKEN" \
  -o "export_$DOC.zip"
```

```powershell
$DOC = "<document_id>"
$headers = @{ Authorization = "Bearer $env:API_AUTH_TOKEN" }
Invoke-WebRequest -Uri "http://localhost:8082/export/archive?document_id=$DOC&collection=jsonify2ai_chunks_768" `
  -Headers $headers -OutFile "export_$DOC.zip"
```

---

## Authentication

Tokens are auto-generated on first run via:
- **Windows**: `scripts\ensure_tokens.ps1`
- **macOS/Linux**: `scripts/ensure_tokens.sh`

These create `.env` with `API_AUTH_TOKEN` and `WORKER_AUTH_TOKEN`.

For web UI, set `VITE_API_TOKEN` or `VITE_API_AUTH_TOKEN` (optional; auto-detects API URL).
