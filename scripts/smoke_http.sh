#!/bin/bash

# Simple HTTP smoke tests for jsonify2ai API
# Tests basic endpoints without requiring complex setup

API_BASE=${API_BASE:-"http://localhost:8082"}

echo "Testing API endpoints at $API_BASE..."

# Test /status endpoint
echo "Testing /status..."
STATUS_RESPONSE=$(curl -s -w "%{http_code}" -o /tmp/status_response.json "$API_BASE/status")
STATUS_CODE="${STATUS_RESPONSE: -3}"

if [ "$STATUS_CODE" = "200" ]; then
    echo "✓ /status returned 200"
    # Check if response has expected structure
    if grep -q '"ok"' /tmp/status_response.json; then
        echo "✓ /status response has 'ok' field"
    else
        echo "⚠ /status response missing 'ok' field"
    fi
else
    echo "✗ /status returned $STATUS_CODE"
fi

# Test /health/full endpoint
echo "Testing /health/full..."
HEALTH_RESPONSE=$(curl -s -w "%{http_code}" -o /tmp/health_response.json "$API_BASE/health/full")
HEALTH_CODE="${HEALTH_RESPONSE: -3}"

if [ "$HEALTH_CODE" = "200" ]; then
    echo "✓ /health/full returned 200"
    if grep -q '"api"' /tmp/health_response.json && grep -q '"worker"' /tmp/health_response.json; then
        echo "✓ /health/full response has expected fields"
    else
        echo "⚠ /health/full response missing expected fields"
    fi
else
    echo "✗ /health/full returned $HEALTH_CODE"
fi

# Test /export/archive endpoint (should return 400 for missing document_id)
echo "Testing /export/archive..."
EXPORT_RESPONSE=$(curl -s -w "%{http_code}" -o /tmp/export_response.json "$API_BASE/export/archive")
EXPORT_CODE="${EXPORT_RESPONSE: -3}"

if [ "$EXPORT_CODE" = "400" ] || [ "$EXPORT_CODE" = "404" ]; then
    echo "✓ /export/archive returned expected error code $EXPORT_CODE"
else
    echo "⚠ /export/archive returned unexpected code $EXPORT_CODE"
fi

# Test CORS headers
echo "Testing CORS headers..."
CORS_RESPONSE=$(curl -s -H "Origin: http://localhost:5173" -I "$API_BASE/status" | grep -i "access-control-allow-origin")
if [ -n "$CORS_RESPONSE" ]; then
    echo "✓ CORS headers present"
else
    echo "⚠ CORS headers missing"
fi

# Cleanup
rm -f /tmp/status_response.json /tmp/health_response.json /tmp/export_response.json

echo "Smoke tests completed."
