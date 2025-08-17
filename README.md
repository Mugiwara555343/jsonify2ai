# jsonify2ai

Ingest → embed → store → retrieve. Ships with `note2json` as a module.

![CI](https://github.com/Mugiwara555343/jsonify2ai/actions/workflows/ci.yml/badge.svg)

## Description

jsonify2ai is a comprehensive AI data pipeline that processes, normalizes, embeds, and stores various types of content for intelligent retrieval and question answering. It includes the powerful `note2json` module for converting markdown and text files to structured JSON.

## Installation

```bash
pip install -e .
```

## Quickstart

### Convert markdown to JSON

Convert a markdown file to structured JSON:

```bash
jsonify2ai note2json convert demo_entries/team_collaboration.md -o out.json --pretty
```

### Index & Search

Index a text file for semantic search:

```bash
jsonify2ai index-text -i README.md
```

Search for content:

```bash
jsonify2ai search -q "installation"
```

## Features

- **note2json**: Convert markdown/text to structured JSON
- **Vector Embeddings**: Generate embeddings using BAAI/bge-small
- **Vector Storage**: Store and search using Qdrant
- **Metadata Storage**: PostgreSQL integration for structured data
- **Local LLM**: Ollama integration for question answering
- **CLI Interface**: Easy-to-use command-line tools

## Architecture

See [docs/architecture.md](docs/architecture.md) for detailed system architecture and component descriptions.

## Phase 1 – Text Pipeline

The worker service now provides a complete text processing pipeline that chunks, embeds, and stores text content in Qdrant for semantic search.

### What `/process/text` Does

The endpoint accepts text content (either raw text or file path) and:
1. **Chunks** the text using configurable size and overlap
2. **Embeds** chunks using Ollama's embedding API
3. **Stores** vectors in Qdrant with metadata
4. **Returns** processing statistics and collection info

### Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `OLLAMA_URL` | `http://host.docker.internal:11434` | Ollama service URL |
| `QDRANT_URL` | `http://host.docker.internal:6333` | Qdrant vector database URL |
| `QDRANT_COLLECTION` | `jsonify2ai_chunks` | Collection name for chunks |
| `EMBEDDINGS_MODEL` | `nomic-embed-text` | Ollama model for embeddings |
| `EMBEDDING_DIM` | `768` | Vector dimension size |
| `CHUNK_SIZE` | `800` | Maximum chunk size in characters |
| `CHUNK_OVERLAP` | `100` | Overlap between chunks |
| `EMBED_DEV_MODE` | `0` | Enable dev mode for deterministic dummy embeddings |

### Usage Examples

#### PowerShell (curl.exe)
```powershell
curl.exe -X POST "http://localhost:${PORT_WORKER:-8090}/process/text" `
  -H "Content-Type: application/json" `
  -d "{\"document_id\":\"00000000-0000-0000-0000-000000000000\",\"text\":\"hello world\"}"
```

#### Bash
```bash
curl -X POST "http://localhost:${PORT_WORKER:-8090}/process/text" \
  -H "Content-Type: application/json" \
  -d '{"document_id":"00000000-0000-0000-0000-000000000000","text":"hello world"}'
```

### Qdrant Collection Safety

The system automatically creates collections if they don't exist, but **never recreates** existing ones. If a collection exists with different dimensions than expected, the system will raise a clear error asking you to either:
- Use a different collection name, or
- Change the embedding model to match the existing collection

This prevents data loss and ensures vector compatibility.

### Dev Mode for Embeddings

Set `EMBED_DEV_MODE=1` in your `.env` file to bypass Ollama and generate deterministic dummy embeddings. This is useful for local smoke tests when Ollama isn't running.

**Example `.env` configuration:**
```bash
EMBED_DEV_MODE=1
EMBEDDING_DIM=768
DEBUG_CONFIG=1
```

**Note:** The API `/upload` endpoint now returns HTTP 502 (Bad Gateway) if the worker service fails during processing.

### Dev Mode Verification

To verify that dev mode is working correctly:

1. **Set `.env` configuration:**
   ```bash
   EMBED_DEV_MODE=1
   EMBEDDING_DIM=768
   DEBUG_CONFIG=1
   ```

2. **Rebuild & restart only the worker:**
   ```bash
   docker compose build worker
   docker compose up -d worker
   ```

3. **Verify environment variables inside the container:**
   - **Linux/mac:**
     ```bash
     docker compose exec worker env | grep EMBED
     ```
   - **PowerShell:**
     ```powershell
     docker compose exec worker cmd /c set | findstr EMBED
     ```

4. **Check the debug endpoint:**
   ```bash
   GET http://localhost:${PORT_WORKER:-8090}/debug/config
   ```
   
   Expected response with `dev_mode: "1"` and `dim: 768`:
   ```json
   {
     "model": "nomic-embed-text",
     "dim": 768,
     "dev_mode": "1",
     "qdrant_url": "http://host.docker.internal:6333",
     "ollama_url": "http://host.docker.internal:11434",
     "collection": "jsonify2ai_chunks",
     "chunk_size": 800,
     "chunk_overlap": 100,
     "debug_enabled": true
   }
   ```

### CI Status

Continuous Integration runs on both `master` and `main` branches, executing worker service tests with network calls disabled by default. Set `SERVICES_UP=1` to enable integration tests that require Ollama and Qdrant.

## Phase 1.1 – Upload → Process

The API service now provides a complete file upload and processing workflow that automatically wires uploaded text files to the worker service for chunking, embedding, and storage.

### What `/upload` Does

The endpoint accepts multipart file uploads and:
1. **Saves** files to `./data/documents/<document_id>/<filename>`
2. **Generates** unique UUID v4 document identifiers
3. **Reads** file content as UTF-8 text (5MB limit)
4. **Calls** worker service to process the text
5. **Returns** comprehensive metadata and processing results

### Usage Examples

#### PowerShell (curl.exe)
```powershell
$env:PORT_API=8082
curl.exe -F "file=@.\README.md" "http://localhost:$env:PORT_API/upload"
```

### Response Format

```json
{
  "ok": true,
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "README.md",
  "size": 1529,
  "mime": "text/markdown",
  "worker": {
    "ok": true,
    "chunks": 2,
    "embedded": 2,
    "upserted": 2,
    "collection": "jsonify2ai_chunks"
  }
}
```

### File Storage

Uploaded files are automatically organized under:
```
./data/documents/
├── <document_id_1>/
│   └── <original_filename_1>
├── <document_id_2>/
│   └── <original_filename_2>
└── ...
```

### Error Handling

- **No file**: Returns 400 with error message
- **File too large (>5MB)**: Returns 413 with error message
- **Worker service failure**: Returns 502 with error details
- **Invalid UTF-8**: Automatically coerced to valid UTF-8

