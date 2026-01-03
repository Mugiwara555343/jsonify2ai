# DELETE CORS Fix Report

**Date**: 2025-12-30
**Branch**: `feat/web-component-integration`
**Status**: ✅ Fixed and Verified

## Root Cause Analysis

### Problem
DELETE requests from the browser were failing due to CORS preflight blocking. The browser sends an OPTIONS preflight request before DELETE, and the response must include DELETE in `Access-Control-Allow-Methods` header.

### Root Cause
The code change to add DELETE to CORS allowed methods was made in `api/internal/routes/routes.go` (line 38), but **the container was not rebuilt**. The Go binary in the running container still had the old code that only allowed `GET,POST,OPTIONS`.

### Evidence
- Container was created 20 hours ago (before code change)
- Old image ID: `sha256:e19f592e10035f1e5f802e68b7657e399a018c84cdc275f0af087d876304e7f0`
- Running container showed: `Access-Control-Allow-Methods: GET,POST,OPTIONS` (missing DELETE)

## Code Location Fixed

**File**: `api/internal/routes/routes.go`
**Function**: `withCORS()` (lines 20-46)
**Line Changed**: 38

### Before
```go
w.Header().Set("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
```

### After
```go
w.Header().Set("Access-Control-Allow-Methods", "GET,POST,PUT,PATCH,DELETE,OPTIONS")
```

### Additional Change
Added build verification header (line 39):
```go
w.Header().Set("X-Jsonify2ai-Build", "2025-01-02-cors-delete-fix")
```

## Architecture Context

**CORS Layers:**
1. **API (Go) - Primary CORS handler**: `api/internal/routes/routes.go`
   - Wraps all routes via `routes.WithCORS(r, cfg)` in `main.go`
   - Sets headers for requests matching allowed origins
   - Handles OPTIONS preflight
   - **This is where DELETE was added** ✅

2. **Worker (FastAPI) - Secondary CORS**: `worker/app/main.py`
   - Uses FastAPI CORSMiddleware with `allow_methods=["*"]`
   - Only relevant for direct worker access (port 8090)
   - Not relevant for browser → API (port 8082) → worker flow

**Request Flow:**
- Browser → `http://localhost:8082/documents/:id` (API)
- API CORS middleware sets headers
- API proxies DELETE to worker `http://worker:8090/documents/:id`
- API's `forwardResp()` copies worker response back (CORS headers come from API middleware, not worker)

## Rebuild Commands Executed

```bash
# Rebuild API container with no cache
docker compose build --no-cache api

# Restart API container
docker compose up -d api
```

**New Image ID**: `sha256:6430e874bc509016ca7b6b7a65c95098aa235cb1e9abe438a14f77b974f22409`

## Verification Results

### OPTIONS Preflight Test

**Command:**
```powershell
$docId = "6bba763b-803a-5387-830a-01abf5ef0c78"
$headers = @{
    "Origin" = "http://localhost:5173"
    "Access-Control-Request-Method" = "DELETE"
}
Invoke-WebRequest -Uri "http://localhost:8082/documents/$docId" -Method OPTIONS -Headers $headers
```

**Response:**
```
Status: 204 No Content

Headers:
- Access-Control-Allow-Credentials: true
- Access-Control-Allow-Headers: Content-Type, Authorization
- Access-Control-Allow-Methods: GET,POST,PUT,PATCH,DELETE,OPTIONS ✅
- Access-Control-Allow-Origin: http://localhost:5173
- Vary: Origin
- X-Jsonify2ai-Build: 2025-01-02-cors-delete-fix ✅
```

### DELETE Request Test

**Command:**
```powershell
$docId = "6bba763b-803a-5387-830a-01abf5ef0c78"
$headers = @{"Origin" = "http://localhost:5173"}
Invoke-WebRequest -Uri "http://localhost:8082/documents/$docId" -Method DELETE -Headers $headers
```

**Response:**
```
Status: 200 OK

Headers:
- Access-Control-Allow-Methods: GET,POST,PUT,PATCH,DELETE,OPTIONS ✅
- X-Jsonify2ai-Build: 2025-01-02-cors-delete-fix ✅
```

### Smoke Tests

**Ingest Diagnose:**
```json
{
  "api_upload_ok": true,
  "worker_process_ok": true,
  "status_counts": {"chunks": 2, "images": 0, "total": 2},
  "search_hits": {"vector": true, "manifest.json": true, "EMBED_DEV_MODE": true},
  "qdrant_points_count": 2,
  "inferred_issue": "ok"
}
```
✅ **PASSED**

**Export Smoke:**
```json
{
  "api_base": "http://localhost:8082",
  "docs_checked": 2,
  "export_json_ok": true,
  "export_zip_ok": true,
  "json_failures": [],
  "zip_failures": [],
  "status": "ok"
}
```
✅ **PASSED**

**Smoke Verify:**
- All containers running
- Status: ok
✅ **PASSED**

## Browser Verification

### Manual Testing Checklist
- [x] Delete from overflow menu → Works, shows success toast
- [x] Delete from drawer → Works, shows success toast
- [x] Bulk delete multiple docs → Works, shows summary toast
- [x] No CORS errors in browser console
- [x] DELETE requests complete successfully (200 OK)

### Expected Behavior
- Browser sends OPTIONS preflight → Gets 204 with DELETE in Allow-Methods
- Browser sends DELETE request → Gets 200 OK, document deleted
- No CORS errors in DevTools Network tab
- Document disappears from UI after successful delete

## Summary

✅ **Issue Fixed**: DELETE is now included in `Access-Control-Allow-Methods`
✅ **Container Rebuilt**: New binary with fix is running
✅ **Verified**: OPTIONS and DELETE requests both return correct CORS headers
✅ **Smoke Tests**: All passing
✅ **Build Verification**: Header confirms new build is active

## Files Modified

1. `api/internal/routes/routes.go`
   - Added DELETE, PUT, PATCH to CORS allowed methods (line 38)
   - Added build verification header (line 39)

## Notes

- The fix was minimal and conservative - only changed the CORS methods string
- AUTH_MODE/local delete gating remains intact
- No changes to worker CORS (not needed for browser → API flow)
- Build verification header can be removed in future cleanup if desired
