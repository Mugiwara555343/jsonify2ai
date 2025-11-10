#!/usr/bin/env bash
set -euo pipefail
ENV_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.env"
[[ -f "$ENV_PATH" ]] || [[ -f "$ENV_PATH.example" ]] && cp -n "$ENV_PATH.example" "$ENV_PATH" 2>/dev/null || true
touch "$ENV_PATH"
# load
declare -A map
while IFS='=' read -r k v; do
  [[ -z "${k// /}" || "$k" =~ ^# ]] && continue
  map["$k"]="$v"
done < "$ENV_PATH"
gen(){ od -An -N16 -tx1 /dev/urandom | tr -d ' \n'; }
[[ -n "${map[API_AUTH_TOKEN]:-}" ]] || map[API_AUTH_TOKEN]="$(gen)"
[[ -n "${map[WORKER_AUTH_TOKEN]:-}" ]] || map[WORKER_AUTH_TOKEN]="$(gen)"
# Ensure VITE_API_TOKEN matches API_AUTH_TOKEN for web bundle
[[ -n "${map[API_AUTH_TOKEN]:-}" ]] && map[VITE_API_TOKEN]="${map[API_AUTH_TOKEN]}"
# write back
{
  for key in "${!map[@]}"; do echo "$key=${map[$key]}"; done
} > "$ENV_PATH"
echo "Tokens ensured in .env"
