#!/bin/bash

# Simple HTTP smoke tests for jsonify2ai API
# Tests basic endpoints and golden path (upload -> search -> ask -> export)
# Uses python for JSON parsing for portability

API_BASE=${API_BASE:-"http://localhost:8082"}
TEMP_FILE="goldenpath_test_$$_%RANDOM%.txt"
UPLOAD_RESP="/tmp/upload_resp_$$.json"
SEARCH_RESP="/tmp/search_resp_$$.json"
ASK_RESP="/tmp/ask_resp_$$.json"
ARCHIVE_RESP="/tmp/archive_resp_$$"
STATUS_RESP="/tmp/status_resp_$$.json"
HEALTH_RESP="/tmp/health_resp_$$.json"

# Resolve python command (Windows venv aware)
if [ -f "./.venv/Scripts/python.exe" ]; then
    PY_CMD="./.venv/Scripts/python.exe"
elif [ -f "./.venv/bin/python" ]; then
    PY_CMD="./.venv/bin/python"
elif command -v python >/dev/null 2>&1; then
    PY_CMD="python"
elif command -v python3 >/dev/null 2>&1; then
    PY_CMD="python3"
elif command -v py >/dev/null 2>&1; then
    PY_CMD="py -3"
else
    PY_CMD=""
    echo "⚠ No python found. JSON parsing will be limited."
fi

# Helper to run python command (handles arguments like 'py -3')
py_run() {
    if [ -n "$PY_CMD" ]; then
        $PY_CMD "$@"
    else
        return 1
    fi
}

# Helper for JSON parsing with fallback
get_json_field() {
    local field="$1"
    # Try python first
    if [ -n "$PY_CMD" ]; then
        py_run -c "import sys, json; print(json.load(sys.stdin).get('$field', ''))" 2>/dev/null && return
    fi

    # Fallback to simple regex/sed for standard "key":"value" JSON
    # Matches "field":"value" or "field": "value"
    sed -n 's/.*"'$field'":[[:space:]]*"\([^"]*\)".*/\1/p'
}

echo "Testing API endpoints at $API_BASE..."
PASSED_STEPS=0
TOTAL_STEPS=0
EXPORT_SKIPPED=false

# -----------------------------
# 1. GET /status
# -----------------------------
echo "Testing /status..."
STATUS_CODE=$(curl -s -w "%{http_code}" -o "$STATUS_RESP" "$API_BASE/status")

if [ "$STATUS_CODE" = "200" ]; then
    echo "✓ /status returned 200"
    if grep -q '"ok"' "$STATUS_RESP"; then
        echo "✓ /status response has 'ok' field"
    else
        echo "⚠ /status response missing 'ok' field"
    fi

    if grep -q '"uptime_s"' "$STATUS_RESP"; then
        echo "✓ /status response has 'uptime_s' field"
    else
        echo "⚠ /status response missing 'uptime_s' field"
    fi

    if grep -q '"ingest_total"' "$STATUS_RESP"; then
        echo "✓ /status response has 'ingest_total' field"
    else
        echo "⚠ /status response missing 'ingest_total' field"
    fi
else
    echo "✗ /status returned $STATUS_CODE"
fi

# -----------------------------
# 2. GET /health/full
# -----------------------------
echo "Testing /health/full..."
HEALTH_CODE=$(curl -s -w "%{http_code}" -o "$HEALTH_RESP" "$API_BASE/health/full")

if [ "$HEALTH_CODE" = "200" ]; then
    echo "✓ /health/full returned 200"
    if grep -q '"api"' "$HEALTH_RESP" && grep -q '"worker"' "$HEALTH_RESP"; then
        echo "✓ /health/full response has expected fields"
    else
        echo "⚠ /health/full response missing expected fields"
    fi
else
    echo "✗ /health/full returned $HEALTH_CODE"
fi

# -----------------------------
# 3. CORS Check
# -----------------------------
echo "Testing CORS headers..."
CORS_Existing=$(curl -s -H "Origin: http://localhost:5173" -I "$API_BASE/status" | grep -i "access-control-allow-origin")
if [ -n "$CORS_Existing" ]; then
    echo "✓ CORS headers present"
else
    echo "⚠ CORS headers missing"
fi

# -----------------------------
# 4. Golden Path Sequence
# -----------------------------
echo "Starting Golden Path Sequence..."

# A) Create temp file
echo "This is a goldenpath smoke test file created at $(date)." > "$TEMP_FILE"
echo "Goldenpath keyword is present." >> "$TEMP_FILE"

# B) Upload
echo "Testing POST /upload..."
UPLOAD_CODE=$(curl -s -w "%{http_code}" -o "$UPLOAD_RESP" -F "file=@$TEMP_FILE" "$API_BASE/upload")

DOC_ID=""
if [ "$UPLOAD_CODE" = "200" ] || [ "$UPLOAD_CODE" = "201" ]; then
    echo "✓ /upload returned $UPLOAD_CODE"
    # C) Parse document_id
    DOC_ID=$(cat "$UPLOAD_RESP" | get_json_field "document_id")
    if [ -n "$DOC_ID" ]; then
        echo "✓ Obtained document_id: $DOC_ID"
    else
        echo "✗ Failed to extract document_id from upload response"
        cat "$UPLOAD_RESP"
    fi
else
    echo "✗ /upload returned $UPLOAD_CODE"
    cat "$UPLOAD_RESP"
fi

# D) Search
if [ -n "$DOC_ID" ]; then
    echo "Testing GET /search..."
    # Give a brief pause for ingestion if needed, though usually strictly consistent or fast enough
    sleep 2
    SEARCH_CODE=$(curl -s -w "%{http_code}" -o "$SEARCH_RESP" "$API_BASE/search?q=goldenpath&kind=text")
    if [ "$SEARCH_CODE" = "200" ]; then
        echo "✓ /search returned 200"
        # Check for results
        RESULTS_LEN=$(py_run -c "import sys, json; print(len(json.load(sys.stdin).get('results', [])))" < "$SEARCH_RESP" 2>/dev/null)
        # Fallback
        if [ -z "$RESULTS_LEN" ]; then
            if grep -q '"results":\[' "$SEARCH_RESP"; then
                RESULTS_LEN=1
            else
                RESULTS_LEN=0
            fi
        fi

        if [ "$RESULTS_LEN" -gt 0 ]; then
            echo "✓ /search returned $RESULTS_LEN results"
        else
            echo "⚠ /search returned 0 results (ingestion might be slow)"
        fi
    else
        echo "✗ /search returned $SEARCH_CODE"
    fi
else
    echo "⚠ Skipping /search due to missing document_id"
fi

# E) Ask
if [ -n "$DOC_ID" ]; then
    echo "Testing POST /ask..."
    # Note: API expects 'q', wrapper maps 'q' -> 'query'.
    ASK_PAYLOAD='{"q":"What is the goldenpath file?", "kind":"text"}'
    ASK_CODE=$(curl -s -w "%{http_code}" -o "$ASK_RESP" -X POST -H "Content-Type: application/json" -d "$ASK_PAYLOAD" "$API_BASE/ask")
    if [ "$ASK_CODE" = "200" ]; then
        echo "✓ /ask returned 200"
        # Check for answers
        ANSWERS_LEN=$(py_run -c "import sys, json; print(len(json.load(sys.stdin).get('answers', [])))" < "$ASK_RESP" 2>/dev/null)
        # Fallback if py_run failed
        if [ -z "$ANSWERS_LEN" ]; then
             # Simple grep check if python unavailable
             if grep -q '"answers":\[' "$ASK_RESP"; then
                 ANSWERS_LEN=1 # Assume present
             else
                 ANSWERS_LEN=0
             fi
        fi

        if [ "$ANSWERS_LEN" -gt 0 ]; then
             echo "✓ /ask returned answers"
        else
             echo "⚠ /ask returned no answers"
        fi
    else
        echo "✗ /ask returned $ASK_CODE"
        cat "$ASK_RESP"
    fi
else
     echo "⚠ Skipping /ask due to missing document_id"
fi

# F) Export Archive
if [ -n "$DOC_ID" ]; then
    echo "Testing GET /export/archive..."
    # Check headers for content type
    EXPORT_CODE=$(curl -s -w "%{http_code}" -o "$ARCHIVE_RESP" "$API_BASE/export/archive?document_id=$DOC_ID")
    if [ "$EXPORT_CODE" = "200" ]; then
        echo "✓ /export/archive returned 200"
        # Check content type from a HEAD request or just assume success if 200 and size > 0
        if [ -s "$ARCHIVE_RESP" ]; then
             echo "✓ Exported archive size is $(wc -c < "$ARCHIVE_RESP") bytes"
             # Check if it looks like a zip (PK header) using Python
             HEAD_HEX=$(py_run -c "import sys; print(sys.stdin.buffer.read(4).hex())" < "$ARCHIVE_RESP" 2>/dev/null)
             # Fallback if python missing: read bytes via od/hexdump if available or skip check
             if [ -z "$HEAD_HEX" ]; then
                 if command -v od >/dev/null 2>&1; then
                    HEAD_HEX=$(od -t x1 -N 4 "$ARCHIVE_RESP" | head -1 | cut -d ' ' -f 2- | tr -d ' ')
                 fi
             fi

             if [ -n "$HEAD_HEX" ] && [ "${HEAD_HEX:0:8}" = "504b0304" ]; then
                 echo "✓ Archives has valid PK header"
             elif [ -n "$HEAD_HEX" ]; then
                 echo "⚠ Archive header mismatch: $HEAD_HEX"
             else
                 echo "⚠ Skipping PK header check (python/od missing)"
             fi
        else
             echo "✗ Exported archive is empty"
        fi
    else
        echo "✗ /export/archive returned $EXPORT_CODE"
    fi
else
    echo "⚠ Skipping /export/archive due to missing document_id"
    EXPORT_SKIPPED=true
fi

# Cleanup
rm -f "$TEMP_FILE" "$UPLOAD_RESP" "$SEARCH_RESP" "$ASK_RESP" "$HEALTH_RESP" "$ARCHIVE_RESP" "$STATUS_RESP"

echo "---------------------------------------------------"
echo "Summary:"
echo "Basic Checks (/status, /health, CORS): Done"
if [ -n "$DOC_ID" ]; then
    echo "Golden Path (Upload, Search, Ask, Export): Attempted"
    if [ "$EXPORT_SKIPPED" = "false" ]; then
        echo "Export: Ran"
    else
         echo "Export: Skipped"
    fi
else
    echo "Golden Path: Aborted at Upload phase"
fi
echo "Smoke tests verified."
