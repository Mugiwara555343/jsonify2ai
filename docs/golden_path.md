# Golden Path Runbook

Validated via `scripts/smoke_verify.ps1` (Windows) and `scripts/smoke_verify.sh` (Linux).
Run these commands from the **repo root**.

### 1. Build and Start Services
Ensures all services are running and up-to-date.
```bash
docker compose up -d --build qdrant worker api web
```
**Expected Signal:** All containers running (`docker compose ps`).

### 2. Verify API Health
Checks if API is reachable and can talk to Worker.
```bash
curl -fsS http://localhost:8082/health/full
```
**Expected Signal:** `{"ok":true,"api":true,"worker":true}`
**If Fails:** Check `docker logs jsonify2ai-main-api-1`.

### 3. Verify Worker Health
Checks if Worker is reachable and can talk to Qdrant/Ollama.
```bash
curl -fsS http://localhost:8090/status
```
**Expected Signal:** `{"ok":true,"chunks":true,"images":true,"llm":{"reachable":true,...}}`
**If Fails:** Check `docker logs jsonify2ai-main-worker-1`.

### 4. Create Sample File
Prepare a small file for ingestion.
```bash
# Bash
mkdir -p data/dropzone && echo "This is a golden path test file for verification." > data/dropzone/golden.md

# PowerShell
New-Item -ItemType Directory -Force data/dropzone; "This is a golden path test file for verification." | Set-Content data/dropzone/golden.md
```

### 5. Ingest File
Upload via API (proxies to Worker).
```bash
curl -F "file=@data/dropzone/golden.md" http://localhost:8082/upload
```
**Expected Signal:** `HTTP 200` + JSON with `"ok":true`.
**If Fails:** Ensure `data/dropzone` is mounted correctly in `docker-compose.yml`.

### 6. Search
Verify content is indexed and retrievable.
```bash
curl -fsS "http://localhost:8082/search?q=golden&kind=text"
```
**Expected Signal:** JSON with `results` array containing the file snippet.
**If Fails:** Check if embeddings (`OLLAMA_URL`) are working in Worker logs.

### 7. Ask (RAG)
Verify End-to-End RAG flow (Retrieval + LLM Synthesis).
```bash
curl -fsS -X POST http://localhost:8082/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"What is the golden path file?"}'
```
**Expected Signal:** JSON with `"answer": "..."` and `"mode": "synthesize"`.

### 8. Export Data
Verify export functionality for the ingested document.
*Replace `<DOC_ID>` with the UUID from the search result in Step 6.*
```bash
curl -fsS -O -J "http://localhost:8082/export/archive?document_id=<DOC_ID>"
```
**Expected Signal:** Downloads a `.zip` file.
**If Fails:** Check `worker` logs for Qdrant scroll errors.

### 9. Delete Document
Clean up the test artifact.
*Replace `<DOC_ID>` with value from Step 6.*
```bash
curl -X DELETE "http://localhost:8082/documents/<DOC_ID>"
```
**Expected Signal:** `HTTP 200`.

### 10. Tear Down
Stop containers and clean up.
```bash
docker compose down
```
**Expected Signal:** Containers stopped and removed.
