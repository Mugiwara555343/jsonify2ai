# System Contracts

## /search Contract
**Observed:** `api/internal/routes/routes.go:176` → `worker/app/routers/search.py:141`

| Type | Endpoint | Params/Body | Response |
| :--- | :--- | :--- | :--- |
| **GET** | `/search` | `q` (string, required)<br>`kind` (string, default "text")<br>`k` (int, default 10)<br>`path` (optional)<br>`document_id` (optional)<br>`ingested_after` (iso)<br>`ingested_before` (iso) | `{ "ok": true, "kind": "...", "q": "...", "results": [ { "id": "...", "score": 0.9, "text": "...", "meta": {...} } ] }` |
| **POST** | `/search` | JSON Body: Matches GET params | Same as GET |

**Evidence:**
- `worker/app/routers/search.py:142`: `def search(q: str = Query(...), kind: Literal...`
- `web/src/api.ts:201`: Fallback POST usage `apiRequest("/search", { method: "POST", ... body: JSON.stringify(body) })`

## /ask Contract
**Observed:** `api/internal/routes/routes.go:328` → `worker/app/routers/ask.py:205`

### Request (JSON)
Defined in `worker/app/routers/ask.py:16` (`AskBody`):
```json
{
  "query": "string (required)",
  "k": 6,
  "mode": "search | retrieval (default: search)",
  "document_id": "optional-uuid",
  "path_prefix": "optional-string",
  "answer_mode": "retrieve | synthesize (optional)",
  "ingested_after": "optional-iso",
  "ingested_before": "optional-iso"
}
```

### Response (JSON)
Defined in `worker/app/routers/ask.py:257` (Synthesize) and `:238` (Retrieve):
```json
{
  "ok": true,
  "mode": "synthesize | retrieve",
  "model": "model_name (if synthesized)",
  "answer": "string (empty if retrieve-only)",
  "sources": [
    {
      "id": "uuid",
      "text": "snippet...",
      "score": 0.85,
      "kind": "text | image",
      "meta": {
        "source_file": "filename",
        "ingested_at": "iso-date"
      }
    }
  ],
  "stats": { "k": 6, "returned": 4 }
}
```

## Chunk Schema Contract
**Observed:** `worker/app/routers/process.py:607` (Construction) and `worker/app/config.py:37` (Collection Name)

Stored in Qdrant payload:

| Field | Type | Description |
| :--- | :--- | :--- |
| `document_id` | keyword | UUID-like string identifying the source document. |
| `path` | keyword | Relative path (e.g., `folder/doc.txt`). |
| `kind` | keyword | `text`, `pdf`, `image`, `chat`. |
| `idx` | int | Chunk index (0-based). |
| `text` | text | The content chunk. |
| `meta` | json | Provenance metadata (`source_system`, `doc_type`, `detected_as`, timestamps). |

## Qdrant Schema & Indexes
**Observed:** `worker/app/services/qdrant_client.py`

- **Collection:** `jsonify2ai_chunks` (Default, from `config.py`)
- **Vector Size:** `768` (Default, from `config.py`)
- **Distance:** `Cosine`

**Indexes (Payload):**
Created in `worker/app/services/qdrant_client.py:205`:

- `document_id` (KEYWORD)
- `kind` (KEYWORD)
- `path` (KEYWORD)
- `meta.ingested_at_ts` (INTEGER)
- `meta.source_system` (KEYWORD)
- `meta.doc_type` (KEYWORD)
- `meta.detected_as` (KEYWORD)

## Environment Variables
**Observed:** `api/internal/config/config.go` and `worker/app/config.py`

| Variable | Affects | Default |
| :--- | :--- | :--- |
| `PORT_API` | API Port | `8082` |
| `PORT_WORKER` | Worker Port | `8090` |
| `QDRANT_URL` | Connection | `http://host.docker.internal:6333` |
| `OLLAMA_URL` | LLM Connection | `http://host.docker.internal:11434` |
| `EMBEDDINGS_MODEL` | Vector Model | `nomic-embed-text` |
| `QDRANT_COLLECTION` | Chunk Storage | `jsonify2ai_chunks` |

## Known Unknowns
- **Exact Vector Model Binary:** precise model file used by Ollama is external state.
- **Watcher Trigger:** `scripts/filewatcher.py` implementation details not deeply audited (assumed to just POST to worker).

## Protocol
> [!NOTE]
> **Contract Change Protocol**
> If any of these contracts change (endpoints, payloads, schemas), you MUST update this document and verify `docs/golden_path.md` still passes. Breaking changes require version negotiation between API and Worker.
