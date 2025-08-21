#!/usr/bin/env bash
set -euo pipefail
mkdir -p data/dropzone data/exports
export EMBED_DEV_MODE=1 PYTHONPATH=worker
printf "name,dept,salary\nalice,eng,140000\nbob,ops,90000\n" > data/dropzone/pay.csv
python scripts/ingest_dropzone.py --dir data/dropzone --export data/exports/csv.jsonl
python examples/ask_local.py --q "Summarize departments and salaries present." --k 6 --show-sources
