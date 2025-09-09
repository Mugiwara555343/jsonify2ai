<p align="center">
  <img src="docs/jsonify2ai_logo.png" alt="Jsonify2AI logo" width="165"/>
</p>

<h1 align="center"></h1>

**Effortlessly turn your local files into structured JSON and searchable AI-ready vectors, entirely offline, on your own hardware.**

[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Local-first](https://img.shields.io/badge/local--first-%E2%9C%94%EF%B8%8F-brightgreen)
![OS](https://img.shields.io/badge/tested-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey)

<!-- Add more badges as needed -->

<!-- Demo: A screenshot or GIF showing dropzone ingestion and asking a question will go here. -->
---

![Qdrant](https://img.shields.io/badge/Qdrant-1.x-blueviolet?logo=qdrant)
![Dev Modes](https://img.shields.io/badge/dev--modes-embed%20%7C%20audio-yellow)
![Status](https://img.shields.io/badge/status-prototype-orange)
![Last Commit](https://img.shields.io/github/last-commit/Mugiwara555343/jsonify2ai)

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

# 6) Drop files into data/dropzone (txt, md, csv, pdf, docx, wav/mp3…)

# 7) Ingest → JSONL + Qdrant (single pass)
# --once = single pass (no watch loop), not 'one file'.
python scripts/ingest_dropzone.py --dir data/dropzone --export data/exports/ingest.jsonl --once
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
# Deleted files → prune orphans: (coming soon)
# python scripts/ingest_dropzone.py --prune-missing

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

## What’s Supported?

| Type   | Extensions           | Notes                              |
|--------|----------------------|------------------------------------|
| Text   | .txt, .md            | Always on                          |
| CSV    | .csv, .tsv           | Always on                          |
| JSON   | .json, .jsonl        | Always on                          |
| DOCX   | .docx                | `pip install -r worker/requirements.docx.txt` |
| PDF    | .pdf                 | `pip install -r worker/requirements.pdf.txt` |
| Audio  | .wav, .mp3, .m4a ... | `pip install -r worker/requirements.audio.txt` + ffmpeg |
| Images | .jpg, .png, .webp    | Optional, via BLIP captioning      |

If an optional parser isn’t installed, files are **skipped gracefully**.
Install optional parsers via the corresponding worker/requirements.*.txt file (e.g., pip install -r worker/requirements.pdf.txt).

---

## Dev Modes

- `EMBED_DEV_MODE=1` → dummy vectors (no Ollama/embeddings).
- `AUDIO_DEV_MODE=1` → quick stub transcripts (no whisper/ffmpeg).

Great for demos and testing.

---

## Repository Layout

```text
worker/   → parsers, services, tests
scripts/  → ingest_dropzone, watch_dropzone (WIP)
examples/ → ask_local, control_panel
api/      → Go (upload/search/ask) [WIP]
web/      → React interface [WIP]
data/     → dropzone, exports, docs
```

---

## Installation and Requirements

- **Python:** 3.10+ (tested on Linux, macOS, Windows)
- **Docker:** For Qdrant vector DB (see `docker-compose.yml`)
- **Minimal RAM/CPU:** Designed to run on modest laptops/desktops
- **Optional:** ffmpeg, Ollama for advanced audio/LLM features

| Component        | Version(s) tested                |
|------------------|----------------------------------|
| Python           | 3.10–3.12                        |
| qdrant           | 1.x (Docker image: qdrant/qdrant:<tag>) |
| qdrant-client    | v1.9.1                           |

*See [worker/requirements.txt](worker/requirements.txt) and [worker/requirements.\*.txt](worker/) for optional parsers.*

---

## Roadmap

- [ ] Image captioning → embed
- [ ] Web UI for drop‑zone + previews
- [ ] Auto‑watch mode (real‑time ingest)
- [ ] Unified API service (Go + FastAPI)
- [ ] More enrichers (tags, summaries, OCR)
- [ ] Benchmarks and sample results

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
