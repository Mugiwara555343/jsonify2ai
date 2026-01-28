#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR/.."

WIPE=false
if [[ "${1:-}" == "--wipe" ]]; then
  WIPE=true
fi

echo "== jsonify2ai :: stop_all"

if [ "$WIPE" = true ]; then
  echo "Stopping services and removing volumes..."
  docker compose down -v
else
  docker compose down
fi

echo "== STOPPED"
