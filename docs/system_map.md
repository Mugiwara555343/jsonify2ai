# System Map

## Overview
```ascii
[ Browser ] -> [ Web (5173) ]
       |
       v
  [ API (8082) ] <--> [ Postgres (Optional, 5432) ]
       |
       +--> [ Worker (8090) ] <--> [ Ollama (External:11434) ]
                   |      ^
                   v      |
              [ Qdrant (6333) ]
```

## Services

| Service | Build / Image | Entrypoint | Ports | Env Vars | Dependencies | Healthcheck |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **web** | `./web` | `web/src/main.tsx` (via Vite) | `5173:5173` | `.env` | `api` | `wget` / `curl` to root |
| **api** | `./api` | `api/cmd/server/main.go` | `8082:8082` | `PORT_API`, `DOCS_DIR`, `GIN_MODE`, `AUTH_MODE`, `.env` | `worker`, `qdrant` | `/health/full` |
| **worker** | `./worker` (Image: `jsonify2ai-worker`) | `worker/app/main.py` (via uvicorn) | `8090:8090` | `QDRANT_URL`, `OLLAMA_URL`, `EMBEDDINGS_MODEL`, `ASK_MODEL`, `.env`, `PYTHONPATH` | `qdrant` | `/status` |
| **qdrant** | `qdrant/qdrant:latest` | N/A (Image default) | `6333:6333` | N/A | N/A | `/readyz` |
| **watcher** | `python:3.11-slim` | `scripts/filewatcher.py` | N/A | `WATCH_DIR`, `WORKER_BASE`, `WATCH_INTERVAL_SEC` | `worker` | N/A |

**Evidence:**
- `docker-compose.yml`: Services definitions (lines 1-103).
- `api/cmd/server/main.go`: API entrypoint (lines 1-81).
- `worker/Dockerfile`: Worker entrypoint `CMD ["uvicorn", "worker.app.main:app", ...]` (line 31).

## Entrypoints

### API
- **Main File:** `api/cmd/server/main.go`
- **Router Setup:** `api/internal/routes/routes.go`
  - Registers endpoints: `/health/full`, `/status`, `/upload`, `/search`, `/ask`, `/export`, `/documents`.
  - Usage: `routes.RegisterRoutes(r, dbConn, cfg.DocsDir, cfg.WorkerBase, cfg)` (line 66).

### Worker
- **Main File:** `worker/app/main.py`
  - App definition: `app = FastAPI(title="jsonify2ai-worker")` (line 17).
- **Routers:**
  - `worker/app/routers/ask.py` (`/ask`)
  - `worker/app/routers/search.py` (`/search`)
  - `worker/app/routers/upload.py` (`/upload`)
  - `worker/app/routers/process.py` (`/process`)
  - `worker/app/routers/export.py` (`/export`)

### Web
- **Entrypoint:** `web/index.html` -> `web/src/main.tsx`.
- **API Configuration:** `web/src/api.ts`
  - Base URL detection: `import.meta.env.VITE_API_URL` or `http://localhost:8082` (lines 4-14).
  - API Client: `export async function apiRequest(...)` (line 31).

## Flows (Observed)

### Upload Flow
**Path:** `Web` -> `API` -> `Worker (FS)` -> `API` -> `Worker (Ingest)` -> `Qdrant`

1.  **Web**: POST `/upload` with file (`web/src/api.ts:124`).
2.  **API**: `POST /upload` (`api/internal/routes/routes.go:94`) -> `UploadHandler.Post` (`api/internal/routes/upload.go`).
    - Forwards multipart to `Worker POST /upload` (`upload.go:125`).
3.  **Worker**: `POST /upload` (`worker/app/routers/upload.py:12`).
    - Saves file to `data/dropzone` (disk).
    - Returns `{"ok": True, "path": "..."}`.
4.  **API**: Receives path, determines kind, sends `POST /process/<kind>` to Worker (`api/internal/routes/upload.go:201`).
    - Payload: `{"path": wu.Path}`.
5.  **Worker**: `POST /process/text` (or pdf/etc) (`worker/app/routers/process.py:370`).
    - Reads file from disk, chunks, embeds (Ollama), upserts to `Qdrant` (`process.py:624`).

### Search Flow
**Path:** `Web` -> `API` -> `Worker` -> `Qdrant`

1.  **Web**: GET/POST `/search` (`web/src/api.ts:194`).
2.  **API**: `GET /search` (`api/internal/routes/routes.go:176`).
    - Proxies request to `Worker GET /search` (`route.go:206`).
3.  **Worker**: `GET /search` (`worker/app/routers/search.py:141`).
    - Embeds query using Ollama (`search.py:152`).
    - Queries `Qdrant` (`search.py:123` via `_search`).

### Ask Flow
**Path:** `Web` -> `API` -> `Worker` -> `Qdrant` -> `Ollama`

1.  **Web**: POST `/ask` (`web/src/api.ts:247`).
2.  **API**: `POST /ask` (`api/internal/routes/routes.go:328`) -> `AskHandler.Post`.
    - Proxies body to `Worker POST /ask` (`api/internal/routes/ask_search.go:80`).
3.  **Worker**: `POST /ask` (`worker/app/routers/ask.py:205`).
    - Performs search in `Qdrant` (`ask.py:207`).
    - If synthesis enabled: calls `_ollama_generate` (`ask.py:181`) -> `POST {OLLAMA_URL}/api/generate`.

### Export Flow
**Path:** `Web` -> `API` -> `Worker` -> `Qdrant` + `Filesystem`

1.  **Web**: GET `/export` or `/export/archive` (`web/src/api.ts:314, 332`).
2.  **API**: Proxies to `Worker` endpoints (`api/internal/routes/routes.go:226, 252`).
3.  **Worker**: `GET /export` (`worker/app/routers/export.py:83`) or `/export/archive` (`export.py:163`).
    - Reads points from `Qdrant` (`export.py:25`).
    - For archive, checks `data/` for source file (`export.py:258`) and creates ZIP.

## Contracts

### JSON Shapes

**GET /search** (Worker `search.py:142`, `web/src/api.ts:179`)
- **Params:** `q` (string), `kind` (string, default "text"), `k` (int), `path` (optional), `document_id` (optional), `ingested_after` (iso), `ingested_before` (iso).
- **Response:**
  ```json
  {
    "ok": true,
    "kind": "text",
    "q": "query",
    "results": [
      { "id": "uuid", "score": 0.9, "text": "...", "meta": {...} }
    ]
  }
  ```

**POST /ask** (Worker `ask.py:16`, `web/src/api.ts:236`)
- **Request:**
  ```json
  {
    "query": "string",
    "k": 6,
    "mode": "search | retrieval",
    "document_id": "optional-uuid",
    "answer_mode": "retrieve | synthesize",
    "ingested_after": "optional-iso",
    "ingested_before": "optional-iso"
  }
  ```
- **Response:**
  ```json
  {
    "ok": true,
    "mode": "synthesize",
    "model": "model-name",
    "answer": "The answer is...",
    "sources": [...]
  }
  ```

### Storage (Qdrant)
**Source:** `worker/app/config.py` and `worker/app/qdrant_init.py`

| Component | Value | Default | Evidence |
| :--- | :--- | :--- | :--- |
| **Collection (Chunks)** | `QDRANT_COLLECTION` | `jsonify2ai_chunks` | `config.py:37` |
| **Collection (Images)** | `QDRANT_COLLECTION_IMAGES` | `jsonify2ai_images_768` | `config.py:38` |
| **Vector Size** | `EMBEDDING_DIM` | `768` | `config.py:42` |
| **Payload Keys** | `document_id`, `path`, `kind`, `idx`, `text`, `meta` | | `worker/app/routers/ask.py:79-87` |

## Known Unknowns
- **Watcher logic**: `scripts/filewatcher.py` exists but its internal logic was not inspected deep-dive (assumed to trigger worker API).
- **Exact Vector Model**: Depends on `EMBEDDINGS_MODEL` env var (default `nomic-embed-text`), actual model file not verified.

## Verification
1.  **Check Services**: `docker compose ps`
2.  **Verify API-Worker Link**: `curl http://localhost:8082/health/full` (Expects `{"ok":true,"api":true,"worker":true}`)
3.  **Verify Worker-Qdrant**: `curl http://localhost:8090/status`
4.  **Inspect Env**: `cat .env` (to see active configuration overrides)
5.  **Check Qdrant Collections**: `curl http://localhost:6333/collections`
