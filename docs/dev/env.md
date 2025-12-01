# Environment Variables

This document describes all environment variables used by jsonify2ai components.

## API Server (Go)

### Server Configuration
- `PORT_API`: API server port (default: `8082`)
- `GIN_MODE`: Gin framework mode (default: `release`)

### Database
- `POSTGRES_DSN`: PostgreSQL connection string (optional)

### Service URLs
- `QDRANT_URL`: Qdrant vector database URL (optional)
- `OLLAMA_HOST`: Ollama LLM service URL (optional, legacy: `OLLAMA_URL` is deprecated)
- `WORKER_BASE`: Worker service base URL (optional)
- `WORKER_URL`: Worker service URL (takes precedence over WORKER_BASE)
- `DOCS_DIR`: Documents directory path (default: `./data/documents`)

### Timeouts (in seconds)
- `HTTP_TIMEOUT_SECONDS`: General HTTP timeout (default: `15`)
- `UPLOAD_TIMEOUT_SECONDS`: Upload timeout (default: `60`)
- `SEARCH_TIMEOUT_SECONDS`: Search timeout (default: `15`)
- `ASK_TIMEOUT_SECONDS`: Ask/LLM timeout (default: `30`)

### API-specific Timeouts (in milliseconds)
- `API_READ_TIMEOUT_MS`: API read timeout (default: `15000`)
- `API_WRITE_TIMEOUT_MS`: API write timeout (default: `15000`)
- `API_PROXY_TIMEOUT_MS`: API proxy timeout (default: `60000`)

### CORS
- `CORS_ALLOWED_ORIGINS`: Comma-separated list of allowed origins (default: `http://localhost:5173,http://127.0.0.1:5173`)
- `CORS_ORIGINS`: Legacy CORS origins setting (fallback)

### Rate Limiting
- `RATE_UPLOAD_PER_MIN`: Maximum upload requests per minute per token/IP (default: `10`)
- `RATE_ASK_PER_MIN`: Maximum ask requests per minute per token/IP (default: `30`)

## Worker Service (Python/FastAPI)

### Server Configuration
- `PORT_WORKER`: Worker service port (default: `8090`)

### Service URLs
- `QDRANT_URL`: Qdrant vector database URL (default: `http://host.docker.internal:6333`)
- `OLLAMA_HOST`: Ollama LLM service URL (default: `http://host.docker.internal:11434`, legacy: `OLLAMA_URL` is deprecated)

### Collections
- `QDRANT_COLLECTION`: Text chunks collection name (default: `jsonify2ai_chunks`)
- `QDRANT_COLLECTION_IMAGES`: Images collection name (default: `jsonify2ai_images_768`)

### Embeddings
- `EMBEDDINGS_MODEL`: Embeddings model name (default: `nomic-embed-text`)
- `EMBEDDING_DIM`: Embedding dimensions (default: `768`)
- `EMBED_BATCH_SIZE`: Embedding batch size (default: `64`)
- `QDRANT_UPSERT_BATCH_SIZE`: Qdrant upsert batch size (default: `128`)

### Chunking
- `CHUNK_SIZE`: Chunk size in tokens (default: `800`)
- `CHUNK_OVERLAP`: Chunk overlap in tokens (default: `100`)
- `NORMALIZE_WHITESPACE`: Normalize whitespace before chunking (default: `1`)

### Hashing & IDs
- `NAMESPACE_SEED`: UUID namespace seed for document IDs (default: `2b00c5a8-0ec2-4f1f-9c7e-3f7b7c0f8a77`)
- `USE_DOC_HASH_FROM_BYTES`: Use file bytes for document hash (default: `1`)

### Development Modes
- `EMBED_DEV_MODE`: Bypass real embeddings in dev (default: `0`)
- `AUDIO_DEV_MODE`: Use stub transcript in dev (default: `0`)
- `IMAGES_CAPTION`: Enable image captioning (default: `0`)
- `IMAGES_CAPTION_MODEL`: Image captioning model (default: `Salesforce/blip-image-captioning-base`)
- `STT_MODEL`: Speech-to-text model (default: `tiny`)
- `DEBUG_CONFIG`: Debug configuration (default: `0`)
- `QDRANT_RECREATE_BAD`: Auto-recreate bad collections (default: `0`)

### Directories
- `DROPZONE_DIR`: Dropzone directory (default: `data/dropzone`)
- `EXPORT_JSONL`: Export JSONL file (default: `data/exports/ingest.jsonl`)

### Pipeline Versioning
- `PIPELINE_VERSION`: Pipeline version (default: `2025-08-31`)
- `PARSER_REGISTRY_VERSION`: Parser registry version (default: `2025-08-31`)
- `CHUNKER_NAME`: Chunker name (default: `standard_fixed`)
- `CHUNKER_VERSION`: Chunker version (default: `1.0`)

### Ask/LLM
- `ASK_MODE`: Ask mode - search or llm (default: `search`)
- `ASK_MODEL`: LLM model name (default: `qwen2.5:3b-instruct-q4_K_M`)
- `ASK_MAX_TOKENS`: Max tokens for LLM (default: `512`)
- `ASK_TEMP`: LLM temperature (default: `0.3`)
- `ASK_TOP_P`: LLM top-p (default: `0.9`)

### LLM Synthesis (Optional)
- `LLM_PROVIDER`: LLM provider for answer synthesis - none or ollama (default: `none`)
- `OLLAMA_HOST`: Ollama service URL (default: `http://localhost:11434`)
- `OLLAMA_MODEL`: Ollama model for synthesis (default: `llama3.1:8b`)
- `LLM_TEMPERATURE`: Generation temperature (default: `0.2`)
- `LLM_TOP_P`: Top-p sampling parameter (default: `0.9`)
- `LLM_REPEAT_PENALTY`: Repeat penalty to reduce repetition (default: `1.1`)
- `LLM_MAX_TOKENS`: Maximum tokens to generate (default: `256`)
- `LLM_NUM_CTX`: Context window size (default: `4096`)

To enable answer synthesis with Ollama:
1. Start Ollama: `ollama serve`
2. Pull a model: `ollama pull llama3.1:8b`
3. Set environment: `export LLM_PROVIDER=ollama`
4. Restart worker: `docker compose up -d worker`

**Note:** If worker runs in Docker and Ollama is in another container, set:
```bash
export OLLAMA_HOST=http://ollama:11434
```

### Timeouts & Limits (in milliseconds)
- `HTTP_TIMEOUT_MS`: HTTP timeout (default: `15000`)
- `PARSER_TIMEOUT_MS`: Parser timeout (default: `120000`)
- `MAX_FILE_BYTES`: Max file size in bytes (default: `134217728` = 128MB)

### Filters
- `IGNORE_GLOBS`: Ignore file patterns (default: `*.tmp,*.part,~$*,.DS_Store,__pycache__`)

### CORS
- `WORKER_CORS_ALLOWED_ORIGINS`: Worker CORS origins (comma-separated, supports `*`)
- `CORS_ORIGINS`: Legacy CORS origins setting (fallback)

## File Watcher

### Monitoring Configuration
- `WATCH_STABLE_PASSES`: Number of stable size checks before triggering (default: `2`)
- `WATCH_STRIP_PREFIX`: Path prefix to strip before sending to worker (default: empty)
- `WATCH_REQUIRE_PREFIX`: Required prefix for processed paths (default: `data/`)
- `WATCH_LOG_MAX_MB`: Max log file size in MB before rotation (legacy, default: `10`)

## Telemetry

### Worker Telemetry
- `WORKER_LOG_MAX_MB`: Max log file size in MB before rotation (legacy, default: `20`)

## Log Rotation

### Log File Size Limits
- `MAX_LOG_MB`: Max log file size in MB before rotation for worker.jsonl and watcher.jsonl (default: `16`)
  - When a log file exceeds this size, it rotates with 2-deep rollover (.1, .2)
  - Falls back to `WORKER_LOG_MAX_MB` for worker.jsonl if `MAX_LOG_MB` is not set
  - Falls back to `WATCH_LOG_MAX_MB` for watcher.jsonl if `MAX_LOG_MB` is not set

## Web UI

### Configuration
- `VITE_API_URL`: API base URL (default: `http://localhost:8082`)

### Export ZIP Manifest

When exporting via `/export/archive`, the ZIP now includes a `manifest.json` with:

- `request_id`: Correlates the export request in logs
- `timestamp`: UTC ISO-8601 with `Z`
- `collection`: Resolved Qdrant collection used for the JSONL
- `document_id`: Document identifier
- `counts`: `{ "chunks": N, "images": M }` across both collections
- `files`: Array of objects with `{ path, sha256, bytes }` for each emitted file

Checksums use SHA-256 computed over the content added to the archive. The JSONL entry is named `chunks.jsonl` or `images.jsonl` depending on the selected collection. If the original source file exists under `data/`, it is included under `source/<basename>`.

If no points exist for a `document_id` (across both collections), the API returns HTTP 404 with a JSON body:

```json
{ "detail": "no points for document_id" }
```

### Diagnosis

Use the host-side script to diagnose ingest and search end-to-end:

```bash
python scripts/ingest_diagnose.py
```

It will:

- Create a tiny test file under `data/dropzone/`
- Try API `/upload` (multipart) with `API_AUTH_TOKEN`
- Try worker `/process/text` as fallback with `WORKER_AUTH_TOKEN`
- Poll worker `/status` and run API `/search` checks
- Print a single JSON summary with inferred issues (e.g., `missing_api_token`, `qdrant_empty`, `ok`)

## Examples

### Development Setup
```bash
# API server with custom timeouts
export API_READ_TIMEOUT_MS=30000
export API_WRITE_TIMEOUT_MS=30000
export CORS_ALLOWED_ORIGINS="http://localhost:5173,http://localhost:3000"

# Worker with development modes
export EMBED_DEV_MODE=1
export AUDIO_DEV_MODE=1
export WORKER_CORS_ALLOWED_ORIGINS="*"

# Qdrant and Ollama URLs for local development
export QDRANT_URL="http://localhost:6333"
export OLLAMA_HOST="http://localhost:11434"
```

### Production Setup
```bash
# Secure CORS origins
export CORS_ALLOWED_ORIGINS="https://yourdomain.com"
export WORKER_CORS_ALLOWED_ORIGINS="https://yourdomain.com"

# Production timeouts
export API_READ_TIMEOUT_MS=10000
export API_WRITE_TIMEOUT_MS=10000
export API_PROXY_TIMEOUT_MS=30000

# Database configuration
export POSTGRES_DSN="postgres://user:pass@localhost:5432/jsonify2ai"
export QDRANT_URL="http://qdrant:6333"
export OLLAMA_HOST="http://ollama:11434"
```

### Docker Compose
```yaml
environment:
  - CORS_ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000
  - WORKER_CORS_ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000
  - API_READ_TIMEOUT_MS=15000
  - API_WRITE_TIMEOUT_MS=15000
  - API_PROXY_TIMEOUT_MS=60000
```

## Backup & Evaluation Scripts

### Backup Snapshot
- `QDRANT_URL`: Qdrant URL for backup metadata (default: `http://localhost:6333`)
- `QDRANT_COLLECTION`: Collection name for backup info (default: `jsonify2ai_chunks_768`)

### Ask Evaluation
- `API_BASE`: API base URL for evaluation (default: `http://localhost:8082`)
- `API_AUTH_TOKEN`: Optional auth token for API requests
- `ASK_KIND`: Ask kind for evaluation (default: `text`)
- `QA_FILE`: Path to QA test file (default: `eval/qa.example.jsonl`)

### Usage
```bash
# Create backup snapshot
./scripts/backup_now.sh

# Run ask evaluation
API_AUTH_TOKEN=<your_token_if_set> python scripts/ask_eval.py
```

## Build Performance

### Worker Build Speed

Worker Docker builds use optimized layer caching for faster rebuilds:

- **Dependencies layer**: Copied first and cached separately from source code
- **BuildKit cache mount**: Pip packages cached between builds (`/root/.cache/pip`)
- **Smaller context**: `.dockerignore` excludes `__pycache__/`, `data/`, `.venv/`, etc.

**Impact:**
- First build: 2-5 minutes (initial dependency download)
- Subsequent builds: Seconds, unless `worker/requirements.txt` changes
- Source-only changes: Only the final layer rebuilds (very fast)

To enable BuildKit caching:
```bash
# PowerShell
$env:DOCKER_BUILDKIT=1
docker compose build worker
```

## API Authentication Token

### Auto-Creation

The `scripts/start_all.ps1` script automatically ensures `API_AUTH_TOKEN` exists in `.env`:

- If missing or empty, generates a 32-byte hex token
- Saves to `.env` file
- Web UI picks it up via `VITE_API_TOKEN=${API_AUTH_TOKEN}` in docker-compose.yml

**Usage:**
```bash
# Run start script (auto-creates token if needed)
.\scripts\start_all.ps1

# Or manually ensure token exists
.\scripts\ensure_tokens.ps1
```

The API server reads `API_AUTH_TOKEN` from `.env` and requires it for protected endpoints (`/upload`, `/search`, `/ask`, `/export`).
