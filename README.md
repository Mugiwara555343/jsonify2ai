<p align="center">
  <img src="docs/jsonify2ai_logo.png" alt="Jsonify2AI logo" width="165"/>
</p>

**Effortlessly turn your local files into structured JSON + searchable vectors — on your own hardware.**

**Status:** Demo-ready (local single-user stack)

---

[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![OS](https://img.shields.io/badge/tested-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey)

---

## The point

jsonify2ai ingests local files (text, PDFs, images, audio, chat exports), normalizes them into a unified JSON chunk schema, embeds them into vectors, stores them in Qdrant, and lets you **search / ask / export** from a web UI.

**Local-first means:**
- your data never leaves your machine
- no cloud APIs required
- full control over models, storage, and provenance

---

## What you get

- 🧩 **Multi-format ingestion** — TXT/MD, CSV/TSV, JSON/JSONL, HTML, DOCX, PDF (optional), audio (optional), images (optional), chat exports/transcripts
- 🔍 **Vector search** — Qdrant-backed semantic retrieval
- 🧠 **Ask (optional LLM)** — “retrieve only” always works; “synthesize” uses a local LLM via Ollama when enabled
- 🧪 **Smoke + health checks** — quick scripts to validate API, worker, and Qdrant state
- 🧾 **Export** — JSONL + manifest (and optionally source file) as JSON or ZIP

---

## Architecture (the spine)

This project is **three primary components** working together (plus optional model runtime):

1) **Web UI (React/Vite)** — your control panel (upload, search, ask, export)
2) **API (Go)** — stable HTTP surface (auth, upload proxying, search/export endpoints)
3) **Worker (Python/FastAPI)** — parsing, chunking, embedding, Qdrant I/O, and “Ask” logic

Supporting services:
- **Qdrant** — vector database (required)
- **Ollama** — local LLM runtime (optional; only needed for synthesis)

**Important:** For the **full experience**, you should run the stack with **Docker Compose** so the services can talk to each other consistently.

---

## Quickstart (recommended): Docker Compose

### Prereqs
- Docker Desktop (Windows/macOS) or Docker Engine + Compose (Linux)
- Git

### Start the stack
```bash
git clone https://github.com/Mugiwara555343/jsonify2ai.git
cd jsonify2ai
```

**Windows**
```powershell
.\scripts\start_all.ps1
```

**macOS / Linux**
```bash
./scripts/start_all.sh
```

### Open the UI
- Web UI: http://localhost:5173

### Stop
**Windows**
```powershell
.\scripts\stop_all.ps1
```

**macOS / Linux**
```bash
./scripts/stop_all.sh
```

---

## Optional: Local LLM (Ollama) for “Ask → Synthesize”

You can run jsonify2ai perfectly fine without an LLM (search + export still work).
LLM is only used when you enable **synthesis**.

1) Install Ollama (from their official installer)
2) Pull a model:
```bash
ollama pull qwen2.5:3b-instruct-q4_K_M
```

3) Configure env (in `.env` or your shell):
```bash
LLM_PROVIDER=ollama
OLLAMA_HOST=http://host.docker.internal:11434
OLLAMA_MODEL=qwen2.5:3b-instruct-q4_K_M
```

Then restart worker:
```bash
docker compose restart worker
```

**UI chip states**
- **LLM: off** — not configured (normal)
- **LLM: offline** — configured but unreachable
- **LLM: on (ollama)** — reachable and ready

---

## Ingestion model

Files go into `data/dropzone/` and are:
1) detected by type
2) parsed/extracted
3) chunked
4) embedded (768-dim)
5) upserted into Qdrant with deterministic IDs

**Idempotent:** same content → same `document_id` → safe to re-ingest without duplicates.

### Supported types

| Type   | Extensions           | Notes |
|--------|----------------------|------|
| Text   | `.txt`, `.md`        | always on |
| CSV    | `.csv`, `.tsv`       | always on |
| JSON   | `.json`, `.jsonl`    | always on |
| HTML   | `.html`, `.htm`      | always on |
| DOCX   | `.docx`              | always on |
| PDF    | `.pdf`               | optional |
| Audio  | `.wav`, `.mp3`, `.m4a`… | optional + ffmpeg |
| Images | `.jpg`, `.png`, `.webp` | optional |

Optional parser deps:
```bash
pip install -r worker/requirements.pdf.txt
pip install -r worker/requirements.audio.txt
pip install -r worker/requirements.images.txt
```

---

## Chat ingestion

### ChatGPT exports
Upload `conversations.json` from a ChatGPT export. Each conversation becomes a document with metadata and chat-aware chunking.

### Generic transcripts
Upload `.txt` / `.md` with common chat patterns (e.g. `User:` / `Assistant:`).
These are detected with a confidence threshold and processed as chat when detected.

Example:
```text
User: How do I create a Python virtual environment?
Assistant: Use python -m venv .venv
User: Thanks!
```

---

## Search vs Ask

### Search
Semantic vector search across all documents (global) or one document (focused).
Returns top chunks with scores + provenance.

### Ask
Two modes:
- **Retrieve** — returns best sources with citations (always works)
- **Synthesize** — generates an answer from retrieved sources via LLM (requires Ollama)

All answers include citations (chunk/document IDs + paths) for traceability.

---

## Export

- **Export JSON** — downloads `chunks.jsonl` (or `images.jsonl`)
- **Export ZIP** — `manifest.json` + JSONL + (when available) source file

---

## Troubleshooting

### “Ask” fails in Docker but works on host
Most commonly: hostnames don’t resolve the same inside containers. Prefer:
- `OLLAMA_HOST=http://host.docker.internal:11434` (Docker Desktop)
- or run Ollama as a container and use `http://ollama:11434`

### Verify the stack quickly
Smoke verify scripts:

**Windows**
```powershell
.\scripts\smoke_verify.ps1
```

**macOS/Linux**
```bash
./scripts/smoke_verify.sh
```

Expected:
```json
{
  "api_health_ok": true,
  "worker_status_ok": true,
  "api_upload_ok": true,
  "search_hits_all": true,
  "inferred_issue": "ok"
}
```

### Useful logs
```bash
docker compose logs -f worker
docker compose logs -f api
docker compose logs -f qdrant
```

---

## Developer utilities

Canonical dev scripts live under:
- `scripts/dev/tools/`

Example:
```bash
python scripts/dev/tools/ingest_dropzone.py --help
python scripts/dev/tools/ingest_diagnose.py --help
python scripts/dev/tools/smoke_precommit.py
```

---

## Configuration

For the demo, tokens can be auto-generated on first run.

For advanced usage, create `.env` from `.env.example` and set:

| Variable | Description | Required |
|----------|-------------|----------|
| `API_AUTH_TOKEN` | API auth token | auto |
| `WORKER_AUTH_TOKEN` | Worker token | auto |
| `AUTH_MODE` | `local` (default) or `strict` | no |
| `LLM_PROVIDER` | `ollama` to enable synthesis | no |
| `OLLAMA_HOST` | Ollama URL (default `http://localhost:11434`) | no |
| `OLLAMA_MODEL` | Model name | no |
| `EMBED_DEV_MODE` | `1` → deterministic dummy vectors | no |
| `AUDIO_DEV_MODE` | `1` → skip transcription | no |
| `IMAGES_CAPTION` | `1` → enable image captioning | no |

**⚠️ Tip:** Don’t set `VITE_API_URL` unless you’re deploying behind a proxy. In local dev, the UI auto-detects.

---

## Documentation

- **[API Reference](docs/API.md)**
- **[Architecture](docs/ARCHITECTURE.md)**
- **[Data Model](docs/DATA_MODEL.md)**
- **[Deployment](docs/DEPLOY.md)**

---

## License

MIT — use, hack, extend.
