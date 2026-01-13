# System Invariants

## 1. Vector Compatibility
**Invariant:** All vectors must be **768-dimensional** and use **Cosine** distance.
**Evidence:** `worker/app/config.py:42` (`EMBEDDING_DIM = 768`) and `worker/app/services/qdrant_client.py:86`.
**Verify:**
```bash
curl -fsS http://localhost:8090/status | jq '.chunks'
# Must return true
```

## 2. Deterministic IDs
**Invariant:** Document IDs are derived solely from their relative filepath (UUIDv5). Re-ingesting the same path yields the same ID.
**Evidence:** `worker/app/utils/docids.py:45` `uuid.uuid5(DEFAULT_NAMESPACE, relpath)`.
**Verify:**
```bash
# Ingest same file twice -> Qdrant point count should remain constant (upsert behavior).
```

## 3. Service Connectivity
**Invariant:** Services communicate via Docker network DNS (`http://worker:8090`, `http://qdrant:6333`).
**Exception:** Host-bound services (Ollama) use `host.docker.internal`.
**Evidence:** `docker-compose.yml` `networks: default: driver: bridge`.
**Verify:**
```bash
docker compose exec api curl -I http://worker:8090/status
```

## 4. Immutable Build (Rebuild Required)
**Invariant:** `api` and `web` containers bake source code during build. Code changes require a rebuild.
**Evidence:** `web/Dockerfile` and `api/Dockerfile` `COPY . /app`. `docker-compose.yml` does NOT bind-mount code for these services.
**Verify:**
Change code -> `docker compose up -d` -> No change.
Change code -> `docker compose up -d --build` -> Change applied.

## 5. Chunk Schema Stability
**Invariant:** `chunk_id` is deterministically derived from `document_id` + `chunk_index`.
**Evidence:** `worker/app/utils/docids.py:49` `uuid.uuid5(document_id, f"chunk:{idx}")`.

## 6. Deep Healthchecks
**Invariant:** `/health/full` (API) and `/status` (Worker) check downstream dependencies, not just process uptime.
**Evidence:**
- `api` check probes `worker` + `qdrant`.
- `worker` check probes `qdrant` + `ollama`.
**Verify:**
Stop Qdrant -> `/health/full` returns `{"ok":false, ...}`.

## 7. Contract Protocols
**Invariant:** API and Worker interfaces are tightly coupled. Changes to `worker/app/routers/*.py` request/response shapes MUST be accompanied by updates to `api/internal/routes/*.go`.
**Evidence:** `api` proxies struct-bound requests directly to `worker`.
