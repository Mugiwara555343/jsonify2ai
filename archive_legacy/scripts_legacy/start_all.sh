#!/usr/bin/env bash
set -eu
DIR="$(cd "$(dirname "$0")" && pwd)"

# Optionally ensure tokens (non-blocking - don't fail if tokens aren't needed in local mode)
"$DIR/ensure_tokens.sh" || echo "Note: Token generation skipped (not required for local mode)"

cd "$DIR/.."
set -euo pipefail
docker compose up -d qdrant worker api web

echo ""
echo "== READY"
echo "API: http://localhost:8082"
echo "Web: http://localhost:5173"
echo "Mode: AUTH_MODE=local (no auth required)"
echo ""
echo "Open http://localhost:5173 in your browser to get started."
