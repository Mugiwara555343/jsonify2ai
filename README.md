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

---

## Why Local-First?

- **Privacy**: Your data never leaves your machine—no cloud uploads, no third-party APIs
- **Control**: Full ownership of your documents, embeddings, and search indices
- **Cost**: Zero API fees—runs entirely on your hardware
- **Speed**: No network latency—instant search and processing
- **Compliance**: Perfect for sensitive data, research, or enterprise environments

---

## Quick Start (Local Demo)

1. **Clone and enter the repo:**
   ```bash
   git clone https://github.com/Mugiwara555343/jsonify2ai.git
   cd jsonify2ai
   ```

2. **Start everything:**
   ```powershell
   # Windows (PowerShell)
   scripts/start_all.ps1
   ```
   ```bash
   # macOS / Linux
   ./scripts/start_all.sh
   ```

3. **Open the web UI:**
   - http://localhost:5173

**💡 Quick demo:** Click **"Load demo data"** in the web UI to instantly load 3 example documents, or follow the step-by-step guide in [DEMO_SCRIPT.md](DEMO_SCRIPT.md).

4. **Upload a file:**
   - Click **Browse…** and pick a file
   - ✅ Markdown / text (.md, .txt)
   - ✅ PDFs (parsed into text chunks)
   - ✅ CSV / JSON (treated as text)
   - ⚠️ Other binary formats may be skipped or stored without embeddings
   - Wait for **Uploading…** → **Ingested** chip increments → **Text Chunks** updates

5. **Ask your data:**
   - Scroll down to the **Ask** section
   - Click one of the example questions or type your own
   - Press **Ask** or Enter to search
   - View results:
     - **Answer** block (if LLM synthesis is enabled) - shows a synthesized answer with an "local (ollama)" badge
     - **Sources** section - always shows matching snippets with filenames, document IDs, and scores
   - In `AUTH_MODE=local`, Ask works without any API token
   - **Note**: The "Answer" block appears only if `LLM_PROVIDER=ollama` and Ollama is reachable. Otherwise, Ask still returns sources/snippets, which is the baseline behavior.

6. **Explore and export:**
   - Use **Search** to query text from your file
   - In **Documents**, use:
     - **Export JSON** → downloads `chunks.jsonl` or `images.jsonl`
     - **Export ZIP** → downloads ZIP with `manifest.json` + JSONL (and sources when available)

### Supported file types (demo)

- `.md`, `.txt`
- `.pdf`
- `.csv` (basic text rows)
- Images & audio if already supported by the pipeline (see [Support Matrix](#support-matrix) below)

### To stop services

```powershell
# Windows
scripts/stop_all.ps1
```

```bash
# macOS / Linux
./scripts/stop_all.sh
```

---

---

## Auth Modes

- **`AUTH_MODE=local`** (default)
  - No auth required
  - Best for local experiments and demos

- **`AUTH_MODE=strict`**
  - All protected API endpoints require `Authorization: Bearer <API_AUTH_TOKEN>`
  - The API uses `WORKER_AUTH_TOKEN` for internal calls to the worker
  - Intended for multi-user / production setups

See [docs/DEPLOY.md](docs/DEPLOY.md) for more details on deployment modes.

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

For the local demo, no configuration is required. Tokens are auto-generated on first run.

For advanced usage, create `.env` from `.env.example` and set:

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

---

## Documentation

- **[API Reference](docs/API.md)** - Endpoint documentation with examples
- **[Architecture](docs/ARCHITECTURE.md)** - System design and component overview
- **[Data Model](docs/DATA_MODEL.md)** - JSON chunk schema and structure

---

## License

MIT — use, hack, extend.
