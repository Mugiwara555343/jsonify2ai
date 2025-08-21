# jsonify2ai

[![CI / test-worker](https://github.com/Mugiwara555343/jsonify2ai/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Mugiwara555343/jsonify2ai/actions/workflows/ci.yml)

Local-first “throw anything at it” memory pipeline: **drop files → extract text → chunk → embed → Qdrant → search/ask.**  
_Local‑first "throw‑anything‑at‑it" memory pipeline._

**Problem:** Private, offline capture of messy files (txt/md/pdf/docx/csv/audio) into **structured JSON + searchable embeddings** without heavy frameworks.

**Solution:** Drop files → extract → chunk → embed → Qdrant → search/ask. CPU‑friendly defaults; heavy bits optional.

### Why jsonify2ai (30s)
- **Local‑first:** no cloud calls; works offline.
- **CPU‑friendly:** dev stubs + tiny models.
- **Simple ingest:** a drop‑zone and one command.
- **Small surface area:** no chains/agents to learn.
- **Extensible:** add parsers; keep the pipeline.

> Need orchestration frameworks? Use LangChain/LlamaIndex.  
> Want files → JSON + vectors today? Use **jsonify2ai**.

## Quick Start (5-minute local demo)

> Works on plain CPU. No Docker required for the demo.
> Want concrete examples? See **Demo Recipes** near the bottom.

### 1) Setup
```bash
# 1) create/activate venv
python -m venv .venv && source .venv/Scripts/activate || source .venv/bin/activate

# 2) install jsonify2ai in editable mode + worker extras
pip install -e . -r worker/requirements.all.txt
```

### 2) Point to Qdrant
**Use an existing Qdrant (fastest):**
```bash
export QDRANT_URL=http://localhost:6333  # or your external Qdrant
```

**Or run via Docker:**
```bash
docker compose up -d qdrant
```

### 3) Dev modes (no Ollama required)
```bash
export EMBED_DEV_MODE=1    # deterministic dummy embeddings
export AUDIO_DEV_MODE=1    # faster-whisper stub
```

### 4) Ingest a folder (drop-zone)
```bash
# Drop files into data/dropzone/ then:
PYTHONPATH=worker python scripts/ingest_dropzone.py \
  --dir data/dropzone --export data/exports/ingest.jsonl
```

### 5) Ask your data (two modes)

**Retrieval-only (no LLM):**
```bash
python examples/ask_local.py --q "what's in the pdf?" --k 6 --show-sources
```

**LLM-mode (optional, needs Ollama):**
```bash
python examples/ask_local.py --q "summarize the resume" --llm --model llama3.1 --k 6 --show-sources
```

### 6) Guided "Control Panel"
If you prefer an interactive guide that sets env, ingests, and queries:
```bash
python examples/control_panel.py --help
```

---

## What’s in this repo

- **Drop‑Zone ingest**: batch a folder of mixed files into JSONL + Qdrant.
- **Parsers** (all CPU; heavy ones are optional):
  - Built-in: **Text/Markdown**, **CSV/TSV**, **JSON**, **JSONL**
  - Optional: **DOCX** (`python-docx`), **PDF** (`pypdf`), **Audio** via faster‑whisper (CPU)
- **Dev-mode toggles** to avoid heavy installs while developing.
- **Worker tests** with lean CI; optional features auto‑skip if deps are missing.

### Monorepo layout

```
api/          # Go (upload/search/ask) - WIP
worker/       # FastAPI worker + services/parsers + tests
web/          # React (upload/search/ask) - WIP
scripts/      # Utilities (ingest_dropzone.py)
data/         # Local data (dropzone, exports, documents)
docs/         # Docs & runbooks (optional)
```

---

## Quickstart (2 minutes)

```bash
# 0) create & activate a venv (Windows Git Bash shown; use your favorite shell)
python -m venv .venv && source .venv/Scripts/activate

# 1) minimal deps (tiny install)
pip install -r worker/requirements.txt

# 2) start Qdrant locally
docker compose up -d qdrant

# 3) prep folders
mkdir -p data/dropzone data/exports

# 4) dev-modes so no heavy models are needed
export EMBED_DEV_MODE=1
export AUDIO_DEV_MODE=1

# 5) drop files into data/dropzone (txt, md, csv, json, jsonl, docx, pdf, wav/mp3…)
# 6) ingest → Qdrant + JSONL
PYTHONPATH=worker python scripts/ingest_dropzone.py \
  --dir data/dropzone --export data/exports/ingest.jsonl
```

**Windows PowerShell**

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r worker\requirements.txt
docker compose up -d qdrant
mkdir data\dropzone, data\exports
$env:EMBED_DEV_MODE="1"; $env:AUDIO_DEV_MODE="1"
$env:PYTHONPATH="worker"; python scripts\ingest_dropzone.py --dir data\dropzone --export data\exports\ingest.jsonl
```

### One‑stop “Control Panel”

Run common tasks without remembering flags:

```bash
python examples/control_panel.py ingest --dir data/dropzone --export data/exports/ingest.jsonl
python examples/control_panel.py ask --q "what's in the pdf?" --k 6 --show-sources
python examples/control_panel.py ask --q "summarize the resume" --llm --model llama3.1 --k 6 --show-sources
python examples/control_panel.py peek
python examples/control_panel.py reset --rename
```

---

## What gets parsed?

| Type     | Extensions                                  | Extra install (optional)                                  | If missing…           |
|----------|---------------------------------------------|------------------------------------------------------------|-----------------------|
| Text     | `.txt`, `.md`                               | —                                                          | read as UTF‑8 text    |
| CSV/TSV  | `.csv`, `.tsv`                              | —                                                          | parsed via `csv`      |
| JSON     | `.json`                                     | —                                                          | flattened key paths   |
| JSONL    | `.jsonl`                                    | —                                                          | per-line flattened    |
| DOCX     | `.docx`                                     | `pip install -r worker/requirements.docx.txt`              | skipped with message  |
| PDF      | `.pdf`                                      | `pip install -r worker/requirements.pdf.txt`               | skipped with message  |
| Audio    | `.wav`, `.mp3`, `.m4a`, `.flac`, `.ogg`     | `pip install -r worker/requirements.audio.txt` + ffmpeg    | dev‑mode stub or CPU STT |

> Images are ignored in batch ingest (captioning will come later).

All optional parsers are **lazy‑imported**. If an optional dependency isn’t installed, ingest **won’t crash**: the file is skipped with a clear note unless you pass `--strict`.

---

## Dev‑mode toggles (no heavy installs required)

- `EMBED_DEV_MODE=1` → deterministic stub vectors (no Ollama/embeddings).  
- `AUDIO_DEV_MODE=1` → quick “\[DEV] transcript of file.ext” (no faster‑whisper/ffmpeg).

These make the pipeline fully offline and fast for demos/tests.

---

## Configuration

`worker/app/config.py` loads `.env` from repo root. Defaults are safe for local dev:

```env
# Qdrant and Embeddings
OLLAMA_URL=http://host.docker.internal:11434
QDRANT_URL=http://host.docker.internal:6333
QDRANT_COLLECTION=jsonify2ai_chunks
EMBEDDINGS_MODEL=nomic-embed-text
EMBEDDING_DIM=768
CHUNK_SIZE=800
CHUNK_OVERLAP=100

# Dev toggles
EMBED_DEV_MODE=0
AUDIO_DEV_MODE=0
STT_MODEL=tiny

# Drop-zone defaults
DROPZONE_DIR=data/dropzone
EXPORT_JSONL=data/exports/ingest.jsonl
```

---

## Drop‑Zone ingest usage

```bash
# Standard run
PYTHONPATH=worker python scripts/ingest_dropzone.py \
  --dir data/dropzone --export data/exports/ingest.jsonl

# Fail on missing optional deps
PYTHONPATH=worker python scripts/ingest_dropzone.py --strict
```

### JSONL export format

Each chunk is one line in the export file:

```json
{
  "id": "document_uuid:idx",
  "document_id": "document_uuid",
  "path": "data/dropzone/file.ext",
  "idx": 0,
  "text": "chunk text …",
  "meta": { "source_ext": ".pdf" }
}
```

---

## Tests & CI

```bash
PYTHONPATH=worker python -m pytest --rootdir=./ -q worker/tests
```

CI runs the worker tests with a minimal dependency set, and optional parsers automatically skip if not installed. The build badge reflects the status of `main`.

---

## (Legacy) Text processing endpoints

The worker previously shipped an HTTP pipeline (`/process/text`) to chunk, embed, and upsert text; that still exists for integration with the API service. The drop‑zone CLI uses the same internal chunking/embedding logic under the hood.

---

## Optional installs (one‑liners)

```bash
# base only (minimal)
pip install -r worker/requirements.txt

# enable PDF
pip install -r worker/requirements.pdf.txt

# enable DOCX
pip install -r worker/requirements.docx.txt

# enable Audio (CPU)
pip install -r worker/requirements.audio.txt

# everything (pdf + docx + audio)
pip install -r worker/requirements.all.txt
```

> For real audio transcription, also install **ffmpeg**:  
> Windows (Chocolatey): `choco install ffmpeg` • macOS (Homebrew): `brew install ffmpeg` • Debian/Ubuntu: `sudo apt-get install -y ffmpeg`

---

## One‑liner smoke test

```bash
mkdir -p data/dropzone data/exports
printf "name,age\nalice,30\n" > data/dropzone/sample.csv
echo "hello from jsonify2ai" > data/dropzone/sample.txt
export EMBED_DEV_MODE=1 AUDIO_DEV_MODE=1 PYTHONPATH=worker
python scripts/ingest_dropzone.py --dir data/dropzone --export data/exports/ingest.jsonl
```

---

## Demo Recipes (quick copy-paste)

### Resume Q&A (txt/pdf/docx)
```bash
mkdir -p data/dropzone data/exports
# drop resume.pdf into data/dropzone first
export EMBED_DEV_MODE=1 AUDIO_DEV_MODE=1 PYTHONPATH=worker
python scripts/ingest_dropzone.py --dir data/dropzone --export data/exports/resume.jsonl
python examples/ask_local.py --q "What roles does this resume target?" --k 6 --show-sources
```

### CSV snapshot (structured)
```bash
mkdir -p data/dropzone data/exports
printf "name,dept,salary\nalice,eng,140000\nbob,ops,90000\n" > data/dropzone/pay.csv
export EMBED_DEV_MODE=1 PYTHONPATH=worker
python scripts/ingest_dropzone.py --dir data/dropzone --export data/exports/csv.jsonl
python examples/ask_local.py --q "Which departments and salaries are present?" --k 6 --show-sources
```

**Linux/macOS:** `chmod +x examples/demo_*.sh && ./examples/demo_resume.sh`  
**Windows:** `.\examples\demo_resume.ps1`

---

## Roadmap

- Image captioning (BLIP/CLIP) → text → chunk/embed
- Web UI for drop‑zone status & preview
- Watch mode (auto‑ingest on file changes)
- API/upload wiring to reuse the same `extract_text_auto` path
