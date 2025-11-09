#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
"$DIR/ensure_tokens.sh"
cd "$DIR/.."
docker compose up -d --build web api worker qdrant >/dev/null
mkdir -p data/dropzone
echo "Qdrant is used for vector search." > data/dropzone/smoke_readme.md
python scripts/ingest_diagnose.py
