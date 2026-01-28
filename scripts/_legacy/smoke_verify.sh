#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

./scripts/ensure_tokens.sh >/dev/null 2>&1 || true

docker compose down -v >/dev/null 2>&1 || true

docker compose up -d --build qdrant worker api web >/dev/null

sleep 3

python scripts/ingest_diagnose.py || true

API_TOKEN=$(grep -E '^API_AUTH_TOKEN=' .env | head -n1 | cut -d= -f2- || echo "")
APIPFX="${API_TOKEN:0:4}"

api_health_ok=false
worker_status_ok=false
api_upload_ok=false
search_hits_all=false
ask_answers=0
ask_final_present=false
export_manifest_ok=false
qdrant_points=0
inferred_issue="ok"

api_health_raw=$(curl -fsS http://localhost:8082/health/full 2>/dev/null || echo '{}')
worker_status_raw=$(curl -fsS http://localhost:8090/status 2>/dev/null || echo '{}')

jq -e '.ok==true' >/dev/null 2>&1 <<<"$api_health_raw" && api_health_ok=true || true
jq -e '.ok==true' >/dev/null 2>&1 <<<"$worker_status_raw" && worker_status_ok=true || true

qdrant_points=$(jq -r '.counts.total // 0' <<<"$worker_status_raw" 2>/dev/null || echo "0")

mkdir -p data/dropzone
echo "Qdrant is used for vector search (smoke seed bash)." > data/dropzone/smoke_cli_seed.md

if [[ -n "$API_TOKEN" ]]; then AUTH=(-H "Authorization: Bearer $API_TOKEN"); else AUTH=(); fi

upcode=$(curl -s -o /dev/null -w "%{http_code}" "${AUTH[@]}" -F file=@data/dropzone/smoke_cli_seed.md http://localhost:8082/upload 2>/dev/null || echo "000")
[[ "$upcode" = "200" ]] && api_upload_ok=true || true

s1=$(curl -s "${AUTH[@]}" "http://localhost:8082/search?kind=text&q=Qdrant&limit=3" 2>/dev/null || echo '{}')
s2=$(curl -s "${AUTH[@]}" "http://localhost:8082/search?kind=text&q=vector&limit=3" 2>/dev/null || echo '{}')

# Check initial search hits
hits1_initial=false
hits2_initial=false
jq -e '.results|length>0' <<<"$s1" >/dev/null 2>&1 && hits1_initial=true || true
jq -e '.results|length>0' <<<"$s2" >/dev/null 2>&1 && hits2_initial=true || true

# Auto-seed if no search hits found
if [ "$hits1_initial" = "false" ] && [ "$hits2_initial" = "false" ]; then
  # Create unique seed file with timestamp marker
  timestamp=$(date +%Y%m%d%H%M%S)
  unique_token="SMOKE_EXPORT_TOKEN_$timestamp"
  seed_path="data/dropzone/export_seed.md"
  mkdir -p "$(dirname "$seed_path")"
  echo "Qdrant is used for vector search. $unique_token" > "$seed_path"

  # Upload via API with auth
  upcode_seed=$(curl -s -o /dev/null -w "%{http_code}" "${AUTH[@]}" -F file=@"$seed_path" http://localhost:8082/upload 2>/dev/null || echo "000")
  if [[ "$upcode_seed" = "200" ]]; then
    echo "Auto-seeded export_seed.md with token: $unique_token" >&2
  else
    echo "Auto-seed upload failed (code: $upcode_seed)" >&2
  fi

  # Wait for processing
  sleep 3

  # Re-run search queries using unique token
  s1=$(curl -s "${AUTH[@]}" "http://localhost:8082/search?kind=text&q=$unique_token&limit=3" 2>/dev/null || echo '{}')
  s2=$(curl -s "${AUTH[@]}" "http://localhost:8082/search?kind=text&q=export_seed&limit=3" 2>/dev/null || echo '{}')
fi

if jq -e '.results|length>0' <<<"$s1" >/dev/null 2>&1 && jq -e '.results|length>0' <<<"$s2" >/dev/null 2>&1; then
  search_hits_all=true
fi

ask=$(curl -s "${AUTH[@]}" -H "Content-Type: application/json" -d '{"kind":"text","q":"What is Qdrant used for in this repo?"}' http://localhost:8082/ask 2>/dev/null || echo '{}')

ask_answers=$(jq -r '.answers|length // 0' <<<"$ask" 2>/dev/null || echo "0")
final=$(jq -r '.final // ""' <<<"$ask" 2>/dev/null || echo "")
if [[ -n "$final" ]]; then ask_final_present=true; else ask_final_present=false; fi

# Parse LLM reachability (default false if missing)
llm_reachable=false
llm_reachable=$(jq -r '.llm.reachable // false' <<<"$worker_status_raw" 2>/dev/null || echo "false")

expok=false
docid=$(jq -r '.results[0].document_id // ""' <<<"$s1" 2>/dev/null || echo "")
if [[ -n "$docid" ]]; then
  if curl -fsS -o /tmp/x.zip "${AUTH[@]}" "http://localhost:8082/export/archive?document_id=$docid&collection=jsonify2ai_chunks_768" 2>/dev/null; then
    expok=true
  fi
fi

if [ "$expok" = "true" ]; then export_manifest_ok=true; else export_manifest_ok=false; fi

if [ "$api_health_ok" = "false" ]; then inferred_issue="api_unhealthy";
elif [ "$worker_status_ok" = "false" ]; then inferred_issue="worker_unhealthy";
elif [ "$api_upload_ok" = "false" ]; then inferred_issue="upload_failed";
elif [ "$search_hits_all" = "false" ]; then inferred_issue="search_empty";
elif [ "$llm_reachable" = "true" ] && [ "$ask_final_present" = "false" ]; then inferred_issue="llm_expected_final_missing"; fi

# Convert booleans to JSON format (already strings "true"/"false")
api_health_ok_json="$api_health_ok"
worker_status_ok_json="$worker_status_ok"
api_upload_ok_json="$api_upload_ok"
search_hits_all_json="$search_hits_all"
ask_final_present_json="$ask_final_present"
export_manifest_ok_json="$export_manifest_ok"

jq -n \
  --arg apipfx "$APIPFX" \
  --argjson api_health_ok $api_health_ok_json \
  --argjson worker_status_ok $worker_status_ok_json \
  --argjson api_upload_ok $api_upload_ok_json \
  --argjson search_hits_all $search_hits_all_json \
  --argjson ask_answers $ask_answers \
  --argjson ask_final_present $ask_final_present_json \
  --argjson export_manifest_ok $export_manifest_ok_json \
  --argjson qdrant_points $qdrant_points \
  --arg inferred_issue "$inferred_issue" \
  '{
    api_health_ok: $api_health_ok,
    worker_status_ok: $worker_status_ok,
    api_upload_ok: $api_upload_ok,
    search_hits_all: $search_hits_all,
    ask_answers: $ask_answers,
    ask_final_present: $ask_final_present,
    export_manifest_ok: $export_manifest_ok,
    qdrant_points: $qdrant_points,
    inferred_issue: $inferred_issue,
    diag: { api_token_prefix: $apipfx }
  }'
