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
- [Quick Start](#quick-start)
- [Use Cases](#use-cases)
- [Supported File Types](#whats-supported)
- [Dev Modes](#dev-modes)
- [Installation and Requirements](#installation-and-requirements)
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

## Quick Start

### Option 1: Docker Compose (Recommended)

```bash
# Start all services
docker compose up -d

# Or start individually
docker compose up -d qdrant    # Vector database
docker compose up -d worker    # Python processing service
docker compose up -d api       # Go API service
docker compose up -d web       # React web interface

# Access the web interface at http://localhost:5173
```

### Option 2: Manual Setup

> Works on plain CPU. Docker is used only for Qdrant.

```bash
# 1) Create & activate a virtualenv
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1

# 2) Install minimal requirements for the worker
pip install -r worker/requirements.txt

# 3) Start Qdrant (vector DB)
docker compose up -d qdrant

# 4) Prepare folders
mkdir -p data/dropzone data/exports
# Windows (PowerShell)
mkdir data\dropzone -Force; mkdir data\exports -Force

# 5) (Optional) Enable dev-modes to skip heavy deps
# macOS/Linux:
export EMBED_DEV_MODE=1; export AUDIO_DEV_MODE=1
# Windows (PowerShell):
$env:EMBED_DEV_MODE=1; $env:AUDIO_DEV_MODE=1

# 6) Drop files into data/dropzone (txt, md, csv, html, pdf, docx, wav/mp3…)

# 7) Ingest → JSONL + Qdrant (single pass)
# --once = single pass (no watch loop), not 'one file'.
python scripts/ingest_dropzone.py --dir data/dropzone --export data/exports/ingest.jsonl --once
```

### Create payload indexes (Qdrant)

Use the provided script (works on Windows PowerShell and Unix):

```powershell
# PowerShell
python scripts/qdrant_indexes.py

# Bash / Git Bash / WSL
python scripts/qdrant_indexes.py
```

This ensures document_id, kind, and path are indexed on both collections:

- QDRANT_COLLECTION (e.g., jsonify2ai_chunks_768)
- QDRANT_COLLECTION_IMAGES (e.g., jsonify2ai_images_768)

Note: The script uses the correct Qdrant route PUT /collections/{collection}/index/{field} and is safe to run multiple times.

### Windows note (make)
If `make` is not available in PowerShell, either:
- run commands directly (e.g., `docker compose up -d worker api`, `python scripts/smoke_e2e.py`), or
- use Git Bash (`make up`, `make smoke`).

### Quick Start with Docker Compose

```bash
# Start all services
docker compose up -d

# Access the web interface at http://localhost:5173
# Upload files and search through the web UI
```

## .env example

```bash
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=jsonify2ai_chunks_768
EMBEDDING_DIM=768
ASK_MODEL=qwen2.5:7b-instruct-q4_K_M   # or your preferred tag
EMBED_DEV_MODE=1
AUDIO_DEV_MODE=1

# Copy the example to your .env (Linux/macOS)
# cp .env.example .env
# Or for Windows:
# copy .env.example .env
```

## Sanity Check

```bash
# Ingest dry-run (no writes, prints plan)
python scripts/ingest_dropzone.py --debug --dry-run
# Retrieval dry-run (shows embedding dim, no search)
python examples/ask_local.py --q "smoke test" --debug --dry-run
```

Ask your data:

```bash
# Retrieval-first
python examples/ask_local.py --q "what's in README.md?" --topk 6 --show-sources
# Optional LLM mode (Ollama must be running)
# Prefer setting your default in `ASK_MODEL`; `--model` is an override.
python examples/ask_local.py --q "summarize the resume" --llm --model qwen2.5:3b-instruct-q4_K_M
# If running Ollama in Docker on a different host/port, set OLLAMA_URL=http://localhost:11434 (or your endpoint).
```

## Operations (Baseline vs Day-to-day)

**First run (bootstrap):**

```bash
# One command to populate the DB:
python scripts/ingest_dropzone.py --dir data/dropzone --export data/exports/first.jsonl --once
```

Day-to-day (when files change):

```bash
# Add/update files → re-ingest:
python scripts/ingest_dropzone.py --dir data/dropzone --replace-existing
```

<!-- Prune orphans: coming soon -->
## Deleted files → prune orphans: (coming soon)
## python scripts/ingest_dropzone.py --prune-missing

```bash
# Safety check (no writes):
python scripts/ingest_dropzone.py --debug --dry-run
```

## Qdrant Schema Contract

- Single **unnamed** vector per point
- Dimension: **768**
- Distance: **Cosine**

If your Qdrant collection was created differently (e.g., named vectors or wrong dim), ingestion fails fast. To reset:
```bash
python scripts/ingest_dropzone.py --dir data/dropzone --recreate-bad-collection --once
```

## Environment precedence

For key settings, precedence is:
1) CLI flags (e.g., `--collection`, `--model`)
2) Environment variables (e.g., `QDRANT_COLLECTION`, `ASK_MODEL`)
3) Script defaults

Tip: keep your preferred LLM tag in `ASK_MODEL` so you don’t edit code. Use `--model` for ad-hoc overrides.

---

## Use Cases

- **Index and search research papers, meeting notes, or documentation locally**
- **Build a private document Q&A bot for your team or yourself**
- **Batch process and structure messy files for downstream AI/ML tasks**
- **Rapid prototyping for local AI data pipelines**

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

## Dev Modes

- `EMBED_DEV_MODE=1` → dummy vectors (no Ollama/embeddings).
- `AUDIO_DEV_MODE=1` → quick stub transcripts (no whisper/ffmpeg).

Great for demos and testing.

---

## Repository Layout

```text
worker/   → Python parsers, services, tests
api/      → Go API service (upload/search/ask)
web/      → React web interface
scripts/  → ingest_dropzone, smoke tests, utilities
examples/ → ask_local, control_panel
data/     → dropzone, exports, smoke samples
```

## API Endpoints

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

## Web Interface

A React-based web interface is available at `http://localhost:5173` with:
- **File Upload**: Drag-and-drop file processing with progress indicators
- **Search**: Semantic search across all document types
- **Ask**: Natural language Q&A with your data
- **Status Dashboard**: Real-time processing statistics
- **Collection Hints**: Visual indicators for chunks vs images
- **Processed Toast**: Notifications when new content is processed

Start the web interface:
```bash
docker compose up web
# or for development:
cd web && npm run dev
```

---

## Installation and Requirements

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

## Troubleshooting

- **Qdrant unreachable**: Ensure `docker compose up -d qdrant` and `QDRANT_URL=http://localhost:6333`.
    ```bash
    docker compose logs -f qdrant
    ```
- **Schema mismatch / “Not existing vector name”**: Your collection likely has named or empty vectors. Use:
    ```bash
    python scripts/ingest_dropzone.py --recreate-bad-collection --once
    ```
- **No results**: Run a dry-run to confirm files are discovered and embedded:
    ```bash
    python scripts/ingest_dropzone.py --debug --dry-run
    ```
- **LLM weak/empty answers**: Verify the model tag is installed in Ollama and pass --model explicitly.
    ```bash
    ollama list   # verify your ASK_MODEL tag is actually installed
    # If running Ollama in Docker, use: docker exec -it ollama ollama list
    ```
    You can also run retrieval-only (omit --llm) and inspect --show-sources.

## License

MIT — use, hack, extend.

---

## Operational Notes

- Keep `AUDIO_DEV_MODE=1` in your `.env` for fast/dev-safe runs. Set `AUDIO_DEV_MODE=0` in your shell session when you want real STT transcription.
- Rebuild (export → drop → recreate → reinsert) the collection early with an HNSW index:
    ```bash
    python scripts/reindex_collection.py --drop-and-recreate --indexing_threshold 100
    ```
- Disable the filename/path first fast-path during testing with:
    ```bash
    python examples/ask_local.py --q "somefile.txt" --no-path-fast
    ```

### Smoke test (end-to-end)

After starting Qdrant, Worker, and API, you can validate the full loop:

```bash
# in repo root
python scripts/smoke_e2e.py
```

The test:

- checks /status via the API,
- processes one text, one PDF, and one image via the Worker,
- waits for /status counters to move,
- and runs /search (API) for each kind.

Environment overrides:

```bash
API_URL=http://localhost:8082 WORKER_URL=http://localhost:8090 python scripts/smoke_e2e.py
```

Expect a final `[ok] smoke succeeded`.

### Smoke samples (checked-in)
We ship minimal samples to exercise multiple parsers:

- `data/dropzone/smoke_golden/mini.csv`
- `data/dropzone/smoke_golden/mini.html`
- `data/dropzone/smoke_golden/mini.docx` (generated if missing via `scripts/gen_smoke_docs.py`)

> The DOCX is created deterministically using `python-docx` to avoid binary drift.

### Extended smoke
Baseline smoke:
```bash
python scripts/smoke_e2e.py
```

Extended smoke (CSV/DOCX/HTML):
```bash
python scripts/smoke_e2e.py \
  --csv  data/dropzone/smoke_golden/mini.csv  --q-csv golden \
  --docx data/dropzone/smoke_golden/mini.docx --q-docx Experience \
  --html data/dropzone/smoke_golden/mini.html --q-html title
```

The smoke asserts that the search results include the same document just processed (not just any older data).

### Dependency pins
The worker pins a few parser dependencies for reproducibility:

```
pypdf==6.1.0
python-docx==1.1.2
beautifulsoup4==4.12.3
lxml==5.2.1
```

### Windows note
If make is unavailable in PowerShell, run commands directly:

```bash
docker compose build worker
docker compose up -d worker
python scripts/smoke_e2e.py
```

## Maintenance

Dry-run a full audio re-ingest + (optional) reindex plan (no writes):
```bash
python scripts/full_pipeline_rebuild.py --dir data/dropzone --dry-run --debug
```

Execute audio re-ingest only (replace existing audio document chunks):
```bash
python scripts/full_pipeline_rebuild.py --dir data/dropzone --confirm --debug
```

Execute audio re-ingest + drop & recreate collection with custom indexing threshold:
```bash
python scripts/full_pipeline_rebuild.py --dir data/dropzone --confirm --reindex --indexing-threshold 100 --debug
```
