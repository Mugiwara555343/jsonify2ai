<p align="center">
  <img src="docs/jsonify2ai_logo.png" alt="Jsonify2AI logo" width="165"/>
</p>

<h1 align="center"></h1>

**Effortlessly turn your local files into structured JSON and searchable AI-ready vectors, entirely offline, on your own hardware.**

[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![OS](https://img.shields.io/badge/tested-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey)
![Status](https://img.shields.io/badge/status-prototype-orange)

<!-- Add more badges as needed -->
<!--   -->
<!--![Local-first](https://img.shields.io/badge/local--first-%E2%9C%94%EF%B8%8F-brightgreen)
<!-- Demo: A screenshot or GIF showing dropzone ingestion and asking a question will go here. -->
---

![Qdrant](https://img.shields.io/badge/Qdrant-1.x-blueviolet?logo=qdrant)
![Dev Modes](https://img.shields.io/badge/dev--modes-embed%20%7C%20audio-yellow)
![Last Commit](https://img.shields.io/github/last-commit/Mugiwara555343/jsonify2ai)
[![CI / test-worker](https://github.com/Mugiwara555343/jsonify2ai/actions/workflows/ci.yml/badge.svg)](https://github.com/Mugiwara555343/jsonify2ai/actions/workflows/ci.yml)
---

## Table of Contents

- [Features](#features)
- [What's Supported](#whats-supported)
- [Quick Start](#quick-start)
- [Web Interface](#web-interface)
- [API Reference](#api-reference)
- [Installation & Requirements](#installation-and-requirements)
- [Configuration](#configuration)
- [Use Cases](#use-cases)
- [Advanced Usage](#advanced-usage)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

---

## Features

- **Local-first:** No cloud required; your data stays with you.
- **CPU-friendly:** Runs on any machine, no GPU needed.
- **Plug-and-play:** Drop your files in a folder, run one command.
- **Extensible:** Easily add new file parsers and enrichers.
- **Idempotent:** Safe to re-run—no duplicate processing.

---

## What's Supported?

| Type   | Extensions           | Notes                              |
|--------|----------------------|------------------------------------|
| Text   | .txt, .md            | Always on                          |
| CSV    | .csv, .tsv           | Always on                          |
| JSON   | .json, .jsonl        | Always on                          |
| HTML   | .html, .htm          | Always on                          |
| DOCX   | .docx                | Always on (pinned)                 |
| PDF    | .pdf                 | `pip install -r worker/requirements.pdf.txt` |
| Audio  | .wav, .mp3, .m4a ... | `pip install -r worker/requirements.audio.txt` + ffmpeg |
| Images | .jpg, .png, .webp    | `pip install -r worker/requirements.images.txt` |

**Core requirements (always installed):**
```bash
pip install -r worker/requirements.txt
```

**Optional parsers:**
```bash
# PDF support
pip install -r worker/requirements.pdf.txt

# Audio transcription (requires ffmpeg)
pip install -r worker/requirements.audio.txt

# Image captioning
pip install -r worker/requirements.images.txt
```

If an optional parser isn't installed, files are **skipped gracefully**.

---

## Quick Start

### 🚀 Get Running in 2 Minutes

**Step 1: Start the system**

**Windows (PowerShell):**
```powershell
.\scripts\start_all.ps1
```

**macOS/Linux (Bash):**
```bash
./scripts/start_all.sh
```

**Or manually with Docker Compose:**
```bash
docker compose up -d
```

**Step 2: Access the web interface**
- Open http://localhost:5173 in your browser

**Step 3: Upload and search your files**
1. Drag and drop files into the upload area
2. Search for content using the search box
3. Ask questions using the "Ask" feature

That's it! Your files are now searchable and ready for AI-powered queries.

### 🔑 Tokens

API authentication tokens are **auto-generated on first run** via:
- **Windows**: `scripts\ensure_tokens.ps1`
- **macOS/Linux**: `scripts/ensure_tokens.sh`

These scripts create or update `.env` with `API_AUTH_TOKEN` and `WORKER_AUTH_TOKEN` if they don't exist.

**Where tokens are used:**
- **Client (web UI)**: Uses `VITE_API_TOKEN` or `VITE_API_AUTH_TOKEN` for API requests (upload, search, ask, export)
- **Internal API → Worker**: Uses `WORKER_AUTH_TOKEN` for service-to-service communication
- **API endpoints**: Protected endpoints require `API_AUTH_TOKEN` in the `Authorization: Bearer <token>` header

### 🔧 Alternative: Manual Setup

If you prefer to run components individually:

```bash
# 1) Install Python dependencies
pip install -r worker/requirements.txt

# 2) Start Qdrant (vector database)
docker compose up -d qdrant

# 3) Start worker service
docker compose up -d worker

# 4) Start API service
docker compose up -d api

# 5) Start web interface
docker compose up -d web

# 6) Access at http://localhost:5173
```

### 📁 Prepare Your Data

```bash
# Create data directories
mkdir -p data/dropzone data/exports

# Drop your files here (supports txt, md, csv, html, pdf, docx, images, audio)
# Files will be automatically processed when uploaded via web UI
```

### ⚙️ Optional: Enable Development Modes

For faster testing without heavy dependencies:

```bash
# macOS/Linux:
export EMBED_DEV_MODE=1; export AUDIO_DEV_MODE=1

# Windows (PowerShell):
$env:EMBED_DEV_MODE=1; $env:AUDIO_DEV_MODE=1
```

---

## What's Next?

After getting the system running:

1. **📤 Upload Files**: Use the web interface to upload documents
2. **🔍 Search Content**: Find specific information across all your files
3. **❓ Ask Questions**: Use natural language to query your data
4. **📊 Monitor Status**: Check processing status and document counts
5. **🔧 Configure**: Set up environment variables for custom models

**Need help?** Check the [Troubleshooting](#troubleshooting) section below.

---

## Web Interface

The primary way to interact with jsonify2ai is through the web interface at `http://localhost:5173`.

### 🎯 Key Features

- **📤 File Upload**: Drag-and-drop file processing with real-time progress indicators
- **🔍 Semantic Search**: Find content across all document types using natural language
- **❓ Ask Questions**: Chat with your data using AI-powered Q&A
- **📊 Status Dashboard**: Real-time processing statistics and document counts
- **🏷️ Collection Hints**: Visual indicators showing whether results are from "chunks" or "images"
- **✅ Processed Toast**: Notifications when new content is successfully processed

### 🚀 Getting Started with the Web UI

1. **Upload Files**: Drag files from your computer into the upload area
2. **Wait for Processing**: Watch the status counters increase as files are processed
3. **Search**: Use the search box to find specific content across all your documents
4. **Ask Questions**: Use the "Ask" section for natural language queries about your data

### 🛠️ Development Mode

For development or testing:
```bash
cd web && npm run dev
```

---

## API Reference

### Worker Service (Port 8090)
- `GET /health` - Health check
- `GET /status` - System status and counts
- `POST /process/{text|pdf|image|audio}` - Process files
- `GET /search` - Semantic search
- `POST /ask` - Ask questions with LLM

### API Service (Port 8082)
- `GET /health` - Basic health check
- `GET /health/full` - Full health check (includes worker)
- `GET /status` - Forwarded from worker
- `POST /upload` - File upload and processing
- `GET /search` - Forwarded search
- `POST /ask` - Forwarded ask
- `GET /documents` - List all documents with metadata

### Listing & Exporting Documents

**List all documents:**
```
GET /documents
```
Returns recent document IDs with kinds, paths, and counts.

**Export document data:**
```
GET /export?document_id=<DOC>&collection=<COLL>  # specific collection
GET /export?document_id=<DOC>                   # auto-detect collection
```

### Export ZIP

Bundle JSONL rows and the original source file (if present) into a single ZIP. The ZIP contains `manifest.json` with metadata.

**Web UI (Recent Documents panel):**
- **Copy ID**: Copies the document ID to clipboard
- **Export ZIP**: Downloads a ZIP file containing the document data and manifest.json

**API:**
```
GET /export/archive?document_id=<DOC>&collection=<COLL>
GET /export/archive?document_id=<DOC>  # auto-detects: chunks first, then images
```

Examples:

```bash
# curl (Linux/macOS/Git Bash)
DOC="<DOC>"
curl -L "http://localhost:8082/export/archive?document_id=$DOC&collection=jsonify2ai_chunks_768" \
     -o exports/export_${DOC}.zip

# auto-detect collection
curl -L "http://localhost:8082/export/archive?document_id=$DOC" \
     -o exports/export_${DOC}.zip
```

```powershell
# PowerShell (Windows)
$DOC = "<DOC>"
Invoke-WebRequest "http://localhost:8082/export/archive?document_id=$DOC&collection=jsonify2ai_chunks_768" `
  -OutFile "exports\export_$DOC.zip"

# auto-detect collection
Invoke-WebRequest "http://localhost:8082/export/archive?document_id=$DOC" `
  -OutFile "exports\export_$DOC.zip"
```

Note: the `collection` parameter is optional; auto-detection tries chunks then images. The response sets `Content-Type: application/zip` and includes header `X-Collection-Used`.

If collection is omitted, the worker will attempt both collections automatically.

**Examples:**
```bash
# List documents
curl "http://localhost:8082/documents"

# Export specific document
curl "http://localhost:8082/export?document_id=abc123&collection=chunks" -o export.jsonl

# Auto-detect collection
curl "http://localhost:8082/export?document_id=abc123" -o export.jsonl
```

### Saving exports

We recommend saving JSONL exports to a local `exports/` folder (which is .gitignored):

```powershell
# Windows PowerShell
.\scripts\export_doc.ps1 -DocId <DOCID> -Collection jsonify2ai_chunks_768
.\scripts\export_doc.ps1 -DocId <DOCID> -Collection jsonify2ai_images_768
```

```bash
# curl
curl "http://localhost:8082/export?document_id=<DOCID>&collection=<COLL>" -o exports/export_<DOCID>.jsonl
```

The JSONL rows include: `id, document_id, path, kind, idx, text, meta`.

---

## Installation & Requirements

- **Python:** 3.10+ (tested on Linux, macOS, Windows)
- **Docker:** For Qdrant vector DB and services (see `docker-compose.yml`)
- **Minimal RAM/CPU:** Designed to run on modest laptops/desktops
- **Optional:** ffmpeg, Ollama for advanced audio/LLM features

| Component        | Version(s) tested                |
|------------------|----------------------------------|
| Python           | 3.10–3.12                        |
| qdrant           | 1.x (Docker image: qdrant/qdrant:<tag>) |
| qdrant-client    | v1.9.1                           |
| Go               | 1.21+ (for API service)          |
| Node.js          | 18+ (for web interface)          |

**Core requirements (always installed):**
```bash
pip install -r worker/requirements.txt
```

**Optional parsers:**
```bash
# PDF support
pip install -r worker/requirements.pdf.txt

# Audio transcription (requires ffmpeg)
pip install -r worker/requirements.audio.txt

# Image captioning
pip install -r worker/requirements.images.txt
```

---

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# Vector Database
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=jsonify2ai_chunks_768
QDRANT_COLLECTION_IMAGES=jsonify2ai_images_768
EMBEDDING_DIM=768

# AI Models
ASK_MODEL=qwen2.5:7b-instruct-q4_K_M   # Your preferred LLM model
OLLAMA_URL=http://localhost:11434      # Ollama service URL

# Development Modes (for faster testing)
EMBED_DEV_MODE=1                       # Skip embeddings, use dummy vectors
AUDIO_DEV_MODE=1                       # Skip audio transcription

# Image Captioning (optional)
IMAGES_CAPTION=1                       # Enable BLIP-based image captions
IMAGES_CAPTION_MODEL=Salesforce/blip-image-captioning-base  # Caption model

# API Configuration
API_URL=http://localhost:8082
WORKER_URL=http://localhost:8090
```

#### Complete Environment Variables Reference

| Variable | Default | Description | Required |
|----------|---------|-------------|----------|
| **Core Services** |
| `QDRANT_URL` | `http://host.docker.internal:6333` | Qdrant vector database URL | Yes |
| `OLLAMA_URL` | `http://host.docker.internal:11434` | Ollama LLM service URL | No |
| `WORKER_URL` | `http://worker:8090` | Worker service URL (API → Worker) | No |
| **API Service** |
| `PORT_API` | `8082` | API service port | No |
| `GIN_MODE` | `release` | Gin framework mode (debug/release) | No |
| `DOCS_DIR` | `./data/documents` | Documents directory path | No |
| `POSTGRES_DSN` | - | PostgreSQL connection string (optional) | No |
| **Worker Service** |
| `QDRANT_COLLECTION` | `jsonify2ai_chunks` | Text chunks collection name | No |
| `QDRANT_COLLECTION_IMAGES` | `jsonify2ai_images_768` | Images collection name | No |
| `EMBEDDING_DIM` | `768` | Vector embedding dimension | No |
| `CHUNK_SIZE` | `800` | Text chunk size in characters | No |
| `CHUNK_OVERLAP` | `100` | Text chunk overlap in characters | No |
| **HTTP Timeouts (seconds)** |
| `HTTP_TIMEOUT_SECONDS` | `15` | General HTTP client timeout | No |
| `UPLOAD_TIMEOUT_SECONDS` | `60` | File upload timeout | No |
| `SEARCH_TIMEOUT_SECONDS` | `15` | Search request timeout | No |
| `ASK_TIMEOUT_SECONDS` | `30` | Ask/LLM request timeout | No |
| **CORS Configuration** |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Allowed CORS origins (comma-separated) | No |
| **Development Modes** |
| `EMBED_DEV_MODE` | `0` | Skip real embeddings (use dummy vectors) | No |
| `AUDIO_DEV_MODE` | `0` | Skip audio transcription | No |
| `IMAGES_CAPTION` | `0` | Enable image captioning | No |
| `IMAGES_CAPTION_MODEL` | `Salesforce/blip-image-captioning-base` | Image captioning model | No |
| **Web Interface** |
| `VITE_API_URL` | Auto-detected | API URL for web interface (optional; auto-detects from hostname) | No |

### Setup Instructions

```bash
# Copy the example file
cp .env.example .env

# Edit with your preferred settings
nano .env  # or your preferred editor
```

### Qdrant Indexes

Ensure proper indexing for optimal search performance:

```bash
# Create payload indexes (run once after setup)
python scripts/qdrant_indexes.py
```

This creates indexes on:
- `document_id` - Fast document lookups
- `kind` - Filter by content type (text, image, etc.)
- `path` - Filter by file path

---

## Use Cases

- **Index and search research papers, meeting notes, or documentation locally**
- **Build a private document Q&A bot for your team or yourself**
- **Batch process and structure messy files for downstream AI/ML tasks**
- **Rapid prototyping for local AI data pipelines**

---

### Optional: LLM Synthesis

Enable AI-powered question answering with Ollama:

1. **Set environment variable:**
   ```bash
   LLM_PROVIDER=ollama
   ```

2. **Ensure Ollama is running:**
   ```bash
   # Install and start Ollama (see https://ollama.ai)
   ollama serve
   ```

3. **Verify in web UI:**
   - The status bar will show **"LLM: on (ollama)"** chip when LLM is enabled
   - The chip appears when `ask_synth_total` telemetry is available (indicating LLM is configured)

When enabled, the "Ask" feature will synthesize answers from search results using your local Ollama model. The UI chip shows the current LLM status.

### Optional: image captions
To enable BLIP-based captions on CPU:
- Set `IMAGES_CAPTION=1` for the worker
- (Optional) pick a model via `IMAGES_CAPTION_MODEL` (default: `Salesforce/blip-image-captioning-base`)
Captions are generated lazily and cached; if captioning fails, the system falls back to `image: <path>`.

## Advanced Usage

### Command Line Interface

For advanced users who prefer CLI over the web interface:

```bash
# Upload and process files
python scripts/ingest_dropzone.py --dir data/dropzone --export data/exports/ingest.jsonl --once

# Search your data
python examples/ask_local.py --q "what's in README.md?" --topk 6 --show-sources

# Ask questions with LLM
python examples/ask_local.py --q "summarize the resume" --llm --model qwen2.5:3b-instruct-q4_K_M
```

### Development and Testing

```bash
# Dry-run to see what would be processed
python scripts/ingest_dropzone.py --debug --dry-run

# Run end-to-end smoke tests
python scripts/smoke_e2e.py

# Extended smoke tests with all file types
python scripts/smoke_e2e.py \
  --csv  data/dropzone/smoke_golden/mini.csv  --q-csv golden \
  --docx data/dropzone/smoke_golden/mini.docx --q-docx Experience \
  --html data/dropzone/smoke_golden/mini.html --q-html title
```

### Maintenance Operations

```bash
# Rebuild collection with better indexing
python scripts/reindex_collection.py --drop-and-recreate --indexing_threshold 100

# Full pipeline rebuild (audio re-ingest + reindex)
python scripts/full_pipeline_rebuild.py --dir data/dropzone --confirm --reindex --debug
```

---

## Troubleshooting

### Common Issues

**🔴 Qdrant unreachable**
```bash
# Check if Qdrant is running
docker compose logs -f qdrant

# Restart if needed
docker compose up -d qdrant
```

**🔴 Schema mismatch / "Not existing vector name"**
```bash
# Your collection has wrong schema - recreate it
python scripts/ingest_dropzone.py --dir data/dropzone --recreate-bad-collection --once
```

**🔴 No search results**
```bash
# Check if files are being processed
python scripts/ingest_dropzone.py --debug --dry-run

# Verify Qdrant indexes exist
python scripts/qdrant_indexes.py
```

**🔴 LLM gives weak/empty answers**
```bash
# Check if your model is installed
ollama list

# Verify model name in .env file
grep ASK_MODEL .env
```

**🔴 Web interface not loading**
```bash
# Check if all services are running
docker compose ps

# Restart web service
docker compose up -d web
```

### Getting Help

- Check the logs: `docker compose logs -f [service-name]`
- Run smoke tests: `python scripts/smoke_e2e.py`
- Verify configuration: Check your `.env` file
- Open an issue on GitHub with your error logs

---

## Development

### Repository Layout

```text
worker/   → Python parsers, services, tests
api/      → Go API service (upload/search/ask)
web/      → React web interface
scripts/  → ingest_dropzone, smoke tests, utilities
examples/ → ask_local, control_panel
data/     → dropzone, exports, smoke samples
```

### Development Modes

For faster development and testing:

```bash
# Skip heavy dependencies
export EMBED_DEV_MODE=1    # Use dummy vectors instead of real embeddings
export AUDIO_DEV_MODE=1    # Skip audio transcription
```

### Smoke Tests

We ship minimal test samples:
- `data/dropzone/smoke_golden/mini.csv`
- `data/dropzone/smoke_golden/mini.html`
- `data/dropzone/smoke_golden/mini.docx` (auto-generated)

Run tests:
```bash
# Basic smoke test
python scripts/smoke_e2e.py

# Extended test with all file types
python scripts/smoke_e2e.py --csv data/dropzone/smoke_golden/mini.csv --docx data/dropzone/smoke_golden/mini.docx --html data/dropzone/smoke_golden/mini.html
```

### Smoke Verify

End-to-end verification script that checks API health, worker status, upload, search, ask, and export functionality.

**Run smoke verify:**
```powershell
# Windows (PowerShell)
.\scripts\smoke_verify.ps1
```

```bash
# macOS/Linux (Bash)
./scripts/smoke_verify.sh
```

**Expected output (JSON):**
```json
{
  "api_health_ok": true,
  "worker_status_ok": true,
  "api_upload_ok": true,
  "search_hits_all": true,
  "ask_answers": 3,
  "ask_final_present": false,
  "export_manifest_ok": true,
  "qdrant_points": 6,
  "inferred_issue": "ok",
  "diag": {}
}
```

**Auto-seeding:** If no search hits are found (empty database), the script automatically:
1. Creates `data/dropzone/export_seed.md` with a unique token
2. Uploads it via API
3. Waits for processing
4. Re-runs search queries
5. Uses the first hit for export verification

This ensures `export_manifest_ok=true` even with an empty database.

### Dependency Management

Core dependencies (always installed):
```bash
pip install -r worker/requirements.txt
```

Optional parsers:
```bash
pip install -r worker/requirements.pdf.txt    # PDF support
pip install -r worker/requirements.audio.txt  # Audio transcription
pip install -r worker/requirements.images.txt # Image captioning
```

Pinned versions for reproducibility:
- `pypdf==6.1.0`
- `python-docx==1.1.2`
- `beautifulsoup4==4.12.3`
- `lxml==5.2.1`

---

## Roadmap

- [x] Image captioning → embed ✅
- [x] Web UI for drop‑zone + previews ✅
- [x] Unified API service (Go + FastAPI) ✅
- [ ] Auto‑watch mode (real‑time ingest)
- [ ] Document preview in web UI
- [ ] Advanced search filters
- [ ] Batch processing interface
- [ ] More enrichers (tags, summaries, OCR)
- [ ] Benchmarks and sample results
- [ ] Real-time file watching

*Check the [issues](https://github.com/Mugiwara555343/jsonify2ai/issues) and project board for progress.*

---

## Contributing

Contributions, issues, and feature requests are welcome!
See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines, or just open an issue/PR.

---

### Upload via Web UI (API-backed)
- The web app uploads files to the API (`POST /upload`).
- The API saves the file and triggers the correct worker pipeline based on extension:
  - `.pdf` → `/process/pdf`
  - image types (`.png`, `.jpg`, …) → `/process/image`
  - common audio (`.mp3`, `.wav`, …) → `/process/audio`
  - everything else → `/process/text` (auto-detected downstream)
- After a successful upload, the UI polls `/status` and shows **Processed ✓** when `counts.total` increases.

The `/upload` endpoint responds with the worker processing summary:
```json
{
  "ok": true,
  "document_id": "...",
  "chunks": 6,
  "upserted": 6,
  "collection": "jsonify2ai_chunks_768"
}
```
The web UI shows "Processed ✓" after `/status.total` increases and offers a "Download JSON" link for the last upload.

## License

MIT — use, hack, extend.
