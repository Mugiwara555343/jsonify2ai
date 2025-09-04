# jsonify2ai

Local‑first pipeline: **drop files → extract → chunk → embed → Qdrant → search/ask**.

No cloud, no heavy frameworks — just a simple way to turn messy files into structured JSON + searchable vectors.

---

## Why jsonify2ai?

- **Local‑first:** works fully offline.
- **CPU‑friendly:** dev stubs, tiny models — no GPU required.
- **Drop‑zone ingest:** put files in a folder, run one command.
- **Extensible:** add new parsers easily.
- **Idempotent:** safe to re‑run; files are skipped, not duplicated.

---

## Quick Start (5 minutes)

> Works on plain CPU. No Docker needed for the demo.

```bash
# 1. create a venv & activate
python -m venv .venv && source .venv/bin/activate

# 2. install worker requirements (minimal)
pip install -r worker/requirements.txt

# 3. start Qdrant (vector DB)
docker compose up -d qdrant

# 4. prepare folders
mkdir -p data/dropzone data/exports

# 5. dev‑modes (skip heavy deps)
export EMBED_DEV_MODE=1
export AUDIO_DEV_MODE=1

# 6. drop files into data/dropzone (txt, md, csv, pdf, docx, wav/mp3…)

# 7. ingest → JSONL + Qdrant
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

## Repo Layout

```
worker/   → parsers, services, tests
scripts/  → ingest_dropzone, watch_dropzone
examples/ → ask_local, control_panel
api/      → Go (upload/search/ask) [WIP]
web/      → React interface [WIP]
data/     → dropzone, exports, docs
```

---

## Roadmap

- Image captioning → embed
- Web UI for drop‑zone + previews
- Auto‑watch mode (real‑time ingest)
- Unified API service (Go + FastAPI)
- More enrichers (tags, summaries, OCR)

---

## License

MIT — use, hack, extend.
