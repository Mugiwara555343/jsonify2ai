<p align="center">
  <img src="docs/jsonify2ai_logo.png" alt="Jsonify2AI logo" width="165"/>
</p>

**Effortlessly turn your local files into structured JSON and searchable AI-ready vectors, entirely offline, on your own hardware.**

**Status: Demo-ready** (local mode, single user)

---

[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![OS](https://img.shields.io/badge/tested-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey)

---

## What it does

jsonify2ai transforms your local files (text, PDFs, images, audio, chat transcripts) into searchable vector embeddings. Everything runs on your machine—no cloud APIs, no data leaving your hardware.

**Key features:**
- 🧩 **Multi-format ingestion** – TXT, MD, PDF, CSV, HTML, DOCX, images, audio, chat transcripts → normalized JSONL
- 🔍 **Vector search** – Qdrant-backed semantic retrieval with optional LLM "Ask" via Ollama
- 🖥️ **Fully offline** – Runs entirely on your hardware, no cloud APIs or external services
- 🧪 **Built-in verification** – Health endpoints + smoke scripts validate API, worker, and vector points

**Why local-first?**
- **Privacy**: Your data never leaves your machine
- **Control**: Full ownership of documents, embeddings, and search indices
- **Cost**: Zero API fees
- **Speed**: No network latency
- **Compliance**: Perfect for sensitive data

---

## Quickstart

**Works without an LLM (search + export).** LLM synthesis is optional and only enhances the "Ask" feature.

1. **Clone and start:**
   ```bash
   git clone https://github.com/Mugiwara555343/jsonify2ai.git
   cd jsonify2ai
   ```
   ```powershell
   # Windows
   scripts/start_all.ps1
   ```
   ```bash
   # macOS / Linux
   ./scripts/start_all.sh
   ```

2. **Open the web UI:** http://localhost:5173

3. **Get started:** Click **"Start here"** button (loads demo data automatically) or manually click **"Load demo data"**

4. **Try it out:**
   - **Preview JSON** – Click any document → "Preview JSON" to see normalized chunks
   - **Search** – Use the search bar to find content across documents
   - **Ask** – Scroll to Ask section, type a question, get answers with citations
   - **Export** – Use "Export JSON" or "Export ZIP" to download chunks + manifest

**To stop:** `scripts/stop_all.ps1` (Windows) or `./scripts/stop_all.sh` (macOS/Linux)

### Optional: Local LLM

To enable LLM synthesis for the "Ask" feature:

1. **Install Ollama:** Download from [ollama.com](https://ollama.com)

2. **Pull a model:**
   ```bash
   ollama pull qwen2.5:3b-instruct-q4_K_M
   ```

3. **Set environment variables** (or add to `.env`):
   ```bash
   export LLM_PROVIDER=ollama
   export OLLAMA_HOST=http://host.docker.internal:11434
   export OLLAMA_MODEL=qwen2.5:3b-instruct-q4_K_M
   ```
   Then restart: `docker compose restart worker`

**UI chip states:**
- **LLM: off** (gray) - No LLM configured (normal, search-only mode)
- **LLM: offline** (yellow) - Ollama configured but unreachable
- **LLM: on (ollama)** (blue) - Ollama reachable, synthesis enabled

---

## How ingestion works

Files are uploaded to `data/dropzone/`, automatically detected by type, parsed, chunked, embedded, and stored in Qdrant.

**Supported file types:**

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

**Processing pipeline:**
1. File uploaded → stored in `data/dropzone/`
2. Type detection → parser selected (text, PDF, image, etc.)
3. Content extraction → text extracted from file
4. Chunking → text split into overlapping chunks
5. Embedding → chunks converted to vectors (768-dim)
6. Storage → vectors + metadata stored in Qdrant

**Idempotent processing:** Same file content always produces the same `document_id`. Safe to re-upload without duplicates.

---

## Chat exports

jsonify2ai supports two types of chat ingestion:

### ChatGPT Exports

Upload `conversations.json` from ChatGPT export. Each conversation becomes a separate document with:
- `kind="chat"`
- `meta.source_system="chatgpt"`
- `meta.detected_as="chatgpt"`
- Conversation metadata (title, timestamps, etc.)

### Generic Transcripts

Upload `.txt` or `.md` files with chat transcript patterns:
- `User:` / `Assistant:` / `System:` prefixes
- `[YYYY-MM-DD ...] user:` / `assistant:` formats
- `role: user` / `role: assistant` blocks

**Detection:**
- Automatically detected with confidence scoring (threshold: 0.85)
- If detected, processed as chat with `kind="chat"` and `meta.source_system="transcript"`
- If not detected, processed as regular text

**Example transcript format:**
```
User: How do I create a Python virtual environment?

Assistant: You can create a Python virtual environment using the venv module.

User: Thanks!
```

Both chat types use chat-aware chunking (by message boundaries) and are stored with `kind="chat"` for consistent retrieval.

---

## Search/Ask

### Search

Semantic vector search across all documents:
- **Scope**: "All documents" (global) or "This document" (focused)
- **Results**: Top matching chunks with similarity scores, excerpts, and provenance metadata

### Ask

Q&A with optional LLM synthesis:

**Answer modes:**
- **Retrieve** – Returns top matching sources with citations (chunk IDs, excerpts, provenance). No LLM synthesis. Always works.
- **Synthesize** – Uses LLM to generate an answer from retrieved sources (if confidence is high enough), plus all source citations. Requires `LLM_PROVIDER=ollama` and Ollama to be reachable.

**Workflow:**
1. **Find documents** – Use Global (Retrieve) mode to search across all documents
2. **Activate document** – Click "Use this doc" in search results to switch to document scope
3. **Ask questions** – In "This document" mode, ask specific questions about the active document
4. **Quick Actions** – Document-scoped actions (summarize, extract, etc.) available in "This document" mode

**All responses include source citations** for traceability (chunk IDs, document IDs, paths, provenance metadata).

---

## Export

Export documents in two formats:

**Export JSON:**
- Downloads `chunks.jsonl` or `images.jsonl`
- One JSON object per line (JSONL format)
- Contains all chunks for the document with full metadata

**Export ZIP:**
- Downloads ZIP archive containing:
  - `manifest.json` – Document metadata (paths, counts, kinds, timestamps)
  - `chunks.jsonl` or `images.jsonl` – All chunks
  - Source file (when available)

Use the **Documents** section → select document → "Export JSON" or "Export ZIP".

---

## Troubleshooting

### LLM Chip States

- **LLM: on (ollama)** (blue) - ✅ Working correctly
- **LLM: offline** (yellow) - Configured but unreachable
  - Verify `LLM_PROVIDER=ollama` in `.env`
  - Check `OLLAMA_HOST` (default: `http://localhost:11434`)
  - Ensure Ollama is running: `ollama serve`
  - For Docker: Use `host.docker.internal:11434`
  - Check logs: `docker compose logs worker | grep -i ollama`
- **LLM: off** (gray) - Not configured (normal if `LLM_PROVIDER` not set)

### Export ZIP Failure

1. Use **Copy ID** button to get correct document ID
2. Check collection type:
   - Images → `jsonify2ai_images_768`
   - Text/PDF/Audio/Chat → `jsonify2ai_chunks_768`
3. Verify document exists: `docker compose logs worker | tail -80`
4. Check API token matches web UI token

### Verify Installation

Run the smoke verify script:

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
  "inferred_issue": "ok"
}
```

### Getting Help

- Logs: `docker compose logs -f [service-name]`
- Smoke verify: `./scripts/smoke_verify.sh` or `.\scripts\smoke_verify.ps1`
- Check `.env` configuration
- See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for system overview
- See [docs/DATA_MODEL.md](docs/DATA_MODEL.md) for data schema

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

**⚠️ Important:** Do not set `VITE_API_URL` unless deploying behind a reverse proxy. The web UI auto-detects the API URL from the hostname by default.

See [docs/API.md](docs/API.md) for full API documentation.

---

## Documentation

- **[API Reference](docs/API.md)** - Endpoint documentation with examples
- **[Architecture](docs/ARCHITECTURE.md)** - System design and component overview
- **[Data Model](docs/DATA_MODEL.md)** - JSON chunk schema and structure
- **[Deployment](docs/DEPLOY.md)** - Deployment modes and production setup

---

## License

MIT — use, hack, extend.
