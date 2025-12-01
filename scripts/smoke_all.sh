#!/usr/bin/env bash
# INTERNAL: dev helper, not part of public demo surface
# This script is superseded by scripts/smoke_verify.sh for end users.
# Use smoke_verify.sh or python scripts/ingest_diagnose.py instead.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
"$DIR/ensure_tokens.sh"
cd "$DIR/.."
docker compose up -d --build web api worker qdrant >/dev/null
mkdir -p data/dropzone
echo "Qdrant is used for vector search." > data/dropzone/smoke_readme.md
python scripts/ingest_diagnose.py
