#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
"$DIR/ensure_tokens.sh"
cd "$DIR/.."
docker compose up -d
