# jsonify2ai

**Effortlessly turn your local files into structured JSON and searchable AI-ready vectors—entirely offline, on your own hardware.**

[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Local-first](https://img.shields.io/badge/local--first-%E2%9C%94%EF%B8%8F-brightgreen)
<!-- Add more badges as needed -->

---

> **Demo:**
> _A screenshot or GIF showing dropzone ingestion and asking a question will go here._

---

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start-5-minutes)
- [Use Cases](#use-cases)
- [Supported File Types](#whats-supported)
- [Dev Modes](#dev-modes)
- [Repository Layout](#repo-layout)
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

## Quick Start (5 minutes)

> Works on plain CPU. No Docker needed for the demo.

```bash
# 1. Create and activate a virtual environment
python -m venv .venv && source .venv/bin/activate

# 2. Install minimal requirements for the worker
pip install -r worker/requirements.txt

# 3. Start Qdrant (vector DB)
docker compose up -d qdrant

# 4. Prepare folders
mkdir -p data/dropzone data/exports

# 5. Enable dev-modes (skip heavy deps)
export EMBED_DEV_MODE=1
export AUDIO_DEV_MODE=1

# 6. Drop files into data/dropzone (txt, md, csv, pdf, docx, wav/mp3…)

# 7. Ingest → JSONL + Qdrant
PYTHONPATH=worker python scripts/ingest_dropzone.py   --dir data/dropzone --export data/exports/ingest.jsonl
```

Ask your data:

```bash
python examples/ask_local.py --q "what's in the pdf?" --k 6 --show-sources
```

Optional LLM mode (requires Ollama):

```bash
python examples/ask_local.py --q "summarize the resume" --llm --model qwen2.5:3b-instruct-q4_K_M
```

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

---

## Dev Modes

- `EMBED_DEV_MODE=1` → dummy vectors (no Ollama/embeddings).
- `AUDIO_DEV_MODE=1` → quick stub transcripts (no whisper/ffmpeg).

Great for demos and testing.

---

## Repository Layout

```
worker/   → parsers, services, tests
scripts/  → ingest_dropzone, watch_dropzone
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

## License

MIT — use, hack, extend.
