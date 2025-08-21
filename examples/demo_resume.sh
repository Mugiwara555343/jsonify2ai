#!/usr/bin/env bash
set -euo pipefail
mkdir -p data/dropzone data/exports
export EMBED_DEV_MODE=1 AUDIO_DEV_MODE=1 PYTHONPATH=worker
echo "Place your resume (pdf/docx/txt) into data/dropzone and press Enter"; read
python scripts/ingest_dropzone.py --dir data/dropzone --export data/exports/resume.jsonl
python examples/ask_local.py --q "What roles does this resume target?" --k 6 --show-sources
