---
name: Add Qdrant payload index for meta.ingested_at_ts
overview: Add a payload index for `meta.ingested_at_ts` in the `_ensure_payload_indexes()` function to optimize time-range filtering. The index will be created for both chunks and images collections when they are ensured.
todos:
  - id: "1"
    content: Add meta.ingested_at_ts index creation in _ensure_payload_indexes() function using PayloadSchemaType.INTEGER
    status: completed
  - id: "2"
    content: Update docstring in ensure_collection() to mention meta.ingested_at_ts index
    status: completed
  - id: "3"
    content: Rebuild and restart containers, run smoke tests to verify
    status: completed
    dependencies:
      - "1"
      - "2"
---

# Add Qd

rant Payload Index for meta.ingested_at_ts

## Overview

Add a payload index for `meta.ingested_at_ts` to optimize time-range filtering queries in Qdrant. The field is already used in search/ask endpoints for filtering by ingestion time, but without an index, these queries will be slow at scale.

## Implementation

### File to Modify

**`worker/app/services/qdrant_client.py`**

1. **Update `_ensure_payload_indexes()` function** (lines 205-230):

- Add a new try/except block to create index for `meta.ingested_at_ts`
- Use `models.PayloadSchemaType.INTEGER` (field stores Unix timestamp as integer)
- Field path: `meta.ingested_at_ts` (nested field in payload)
- Follow existing pattern: wrap in try/except with pass (idempotent, graceful failure)

2. **Update docstring** (line 89):

- Change from "Adds payload indexes for {document_id, kind, path}"
- To: "Adds payload indexes for {document_id, kind, path, meta.ingested_at_ts}"

### Code Changes

```python
# In _ensure_payload_indexes() function, add after the "path" index block:
try:
    client.create_payload_index(
        collection_name=name,
        field_name="meta.ingested_at_ts",
        field_schema=models.PayloadSchemaType.INTEGER,
    )
except Exception:
    pass
```



## Architecture

The index will be created automatically when:

- Collections are ensured via `ensure_collection()` calls in `process.py`
- Both `QDRANT_COLLECTION` (chunks) and `QDRANT_COLLECTION_IMAGES` collections will get the index
- The function is idempotent: if index exists, exception is caught and ignored
- If Qdrant is down, exception is caught and logged (existing pattern), pipeline continues

## Verification

After implementation:

- Index will be created on next collection ensure (next file upload/process)
- Can verify via Qdrant API: `GET /collections/{collection}/index`
- Optional: Add log message when index is created (but not required per constraints)

## Testing (You do this)

1. Rebuild containers: `docker compose build api worker web`
2. Restart services: `docker compose up -d api worker web`
3. Run smoke tests:

- `bash scripts/smoke_http.sh`
- `python scripts/ingest_diagnose.py`

4. Verify index exists (optional): Check Qdrant collection info after ingesting a file

## Notes

- No schema changes needed - field already exists in payload
- No new services or containers
- Follows existing pattern for payload indexes
