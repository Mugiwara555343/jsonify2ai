<p align="center">
  <img src="docs/jsonify2ai_logo.png" alt="Jsonify2AI logo" width="165"/>
</p>

**Effortlessly turn your local files into structured JSON and searchable AI-ready vectors, entirely offline, on your own hardware.**

---

### At a Glance

- 🧩 **Multi-format ingestion** – TXT, MD, PDF, CSV, HTML, DOCX, images, audio → normalized JSONL
- 🔍 **Vector search** – Qdrant-backed semantic retrieval with optional LLM “Ask” via Ollama
- 🖥️ **Fully offline** – Runs entirely on your hardware, no cloud APIs or external services
- 🧪 **Built-in verification** – Health endpoints + smoke scripts validate API, worker, and vector points

---

[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![OS](https://img.shields.io/badge/tested-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey)
[![CI / test-worker](https://github.com/Mugiwara555343/jsonify2ai/actions/workflows/ci.yml/badge.svg)](https://github.com/Mugiwara555343/jsonify2ai/actions/workflows/ci.yml)

---

## Why Local-First?

- **Privacy**: Your data never leaves your machine—no cloud uploads, no third-party APIs
- **Control**: Full ownership of your documents, embeddings, and search indices
- **Cost**: Zero API fees—runs entirely on your hardware
- **Speed**: No network latency—instant search and processing
- **Compliance**: Perfect for sensitive data, research, or enterprise environments

---

## Quick Start

### Windows (PowerShell)
```powershell
.\scripts\start_all.ps1
```

### macOS/Linux (Bash)
```bash
./scripts/start_all.sh
```

### Verify Installation
Run the smoke verify script to confirm everything works:

**Windows:**
```powershell
.\scripts\smoke_verify.ps1
```

**macOS/Linux:**
```bash
./scripts/smoke_verify.sh
```

**Expected output:**
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

Open http://localhost:5173 in your browser.

---

## 3-Minute Eval Path

### 1. Upload
- Drag and drop any file (`.txt`, `.md`, `.pdf`, `.docx`, `.csv`, images, audio) into the web UI
- Wait for "Processed ✓" notification

### 2. Search
- Type a query in the search box
- Results show matching chunks with scores and source paths

### 3. Ask (Optional)
- If `LLM_PROVIDER=ollama` is set and Ollama is running, use the "Ask" feature
- The UI chip shows **LLM: on (ollama)** when reachable, **LLM: offline** if configured but unreachable

### 4. Export ZIP
- In the **Recent Documents** panel:
  - Click **Copy ID** to copy the document ID to clipboard
  - Click **Export ZIP** to download a ZIP containing:
    - `export_<document_id>.jsonl` - All chunks/rows
    - `manifest.json` - Document metadata
    - Original source file (if available)

---

## Features

- **Multi-format parsing**: Text, PDF, DOCX, CSV, HTML, images, audio
- **Semantic search**: Vector similarity search across all documents
- **LLM synthesis**: Optional Ollama integration for Q&A
- **Idempotent processing**: Safe to re-run, no duplicates
- **Export formats**: JSONL and ZIP archives with manifests

---

## Support Matrix

| Type   | Extensions           | Status      |
|--------|----------------------|-------------|
| Text   | .txt, .md            | ✅ Always on |
| CSV    | .csv, .tsv           | ✅ Always on |
| JSON   | .json, .jsonl        | ✅ Always on |
| HTML   | .html, .htm          | ✅ Always on |
| DOCX   | .docx                | ✅ Always on |
| PDF    | .pdf                 | ⚙️ Optional |
| Audio  | .wav, .mp3, .m4a ... | ⚙️ Optional + ffmpeg |
| Images | .jpg, .png, .webp    | ⚙️ Optional |

Optional parsers require additional dependencies:
```bash
pip install -r worker/requirements.pdf.txt    # PDF
pip install -r worker/requirements.audio.txt # Audio
pip install -r worker/requirements.images.txt # Images
```

---

## Configuration

Create `.env` from `.env.example` and set:

| Variable | Description | Required |
|----------|-------------|----------|
| `API_AUTH_TOKEN` | API authentication token (auto-generated) | Auto |
| `WORKER_AUTH_TOKEN` | Worker service token (auto-generated) | Auto |
| `AUTH_MODE` | Authentication mode: `local` (default) or `strict` | No |
| `LLM_PROVIDER` | Set to `ollama` to enable LLM synthesis | No |
| `OLLAMA_HOST` | Ollama service URL (default: `http://localhost:11434`) | No |
| `OLLAMA_MODEL` | Ollama model name (default: `llama3.1:8b`) | No |
| `EMBED_DEV_MODE` | Set to `1` to skip embeddings (use dummy vectors) | No |
| `AUDIO_DEV_MODE` | Set to `1` to skip audio transcription | No |
| `IMAGES_CAPTION` | Set to `1` to enable image captioning | No |
| `CORS_ORIGINS` | Comma-separated allowed origins | No |

**⚠️ Important:** Do not set `VITE_API_URL` unless deploying behind a reverse proxy. The web UI auto-detects the API URL from the hostname by default.

## Auth Modes

- **`AUTH_MODE=local`** (default): No bearer authentication is enforced by the API. Browser uploads and UI actions work with zero configuration. Perfect for local demos, recruiters, and single-user setups. You can still set tokens, but they're not required in this mode. This is what you get by default when running `scripts/start_all.ps1` or `scripts/start_all.sh`.

- **`AUTH_MODE=strict`**: All protected endpoints (upload, search, ask) require a valid `Authorization: Bearer <API_AUTH_TOKEN>` header. Use this for production deployments, multi-user setups, or when you need strict access control.

See [docs/API.md](docs/API.md) for full API documentation.

---

## Troubleshooting

### LLM Chip States

- **LLM: on (ollama)** (blue) - ✅ Working correctly
- **LLM: offline** (yellow) - Configured but unreachable
  - Verify `LLM_PROVIDER=ollama` in `.env`
  - Check `OLLAMA_HOST` (default: `http://localhost:11434`)
  - Ensure Ollama is running: `ollama serve`
  - For Docker: Use `host.docker.internal:11434` or service name
  - Check logs: `docker compose logs worker | grep -i ollama`
- **LLM: off** (gray) - Not configured (normal if `LLM_PROVIDER` not set)

### Export ZIP Failure

1. Use **Copy ID** button to get correct document ID
2. Check collection type:
   - Images → `jsonify2ai_images_768`
   - Text/PDF/Audio → `jsonify2ai_chunks_768`
3. Verify document exists: `docker compose logs worker | tail -80`
4. Check API token matches web UI token

### Getting Help

- Logs: `docker compose logs -f [service-name]`
- Smoke verify: `./scripts/smoke_verify.sh` or `.\scripts\smoke_verify.ps1`
- Check `.env` configuration
- See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for system overview
- See [docs/DATA_MODEL.md](docs/DATA_MODEL.md) for data schema

---

## Documentation

- **[API Reference](docs/API.md)** - Endpoint documentation with examples
- **[Architecture](docs/ARCHITECTURE.md)** - System design and component overview
- **[Data Model](docs/DATA_MODEL.md)** - JSON chunk schema and structure

---

## License

MIT — use, hack, extend.
