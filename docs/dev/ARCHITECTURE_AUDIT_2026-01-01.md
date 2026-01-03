# Architecture Audit Report

**Date**: 2026-01-01
**Repository**: jsonify2ai-main
**Audit Type**: System Architecture & Data Flow Analysis
**Status**: Read-only analysis (no code changes)

---

## 1. System Diagram

### Container Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Docker Compose                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐     │
│  │   Web (5173) │───▶│  API (8082)  │───▶│Worker (8090) │     │
│  │   React/Vite  │    │   Go/Gin     │    │ FastAPI/Py   │     │
│  └──────────────┘    └──────────────┘    └──────┬───────┘     │
│         │                  │                      │              │
│         │                  │                      ▼              │
│         │                  │              ┌──────────────┐       │
│         │                  │              │  Qdrant      │       │
│         │                  │              │  (6333)      │       │
│         │                  │              │  Vector DB   │       │
│         │                  │              └──────────────┘       │
│         │                  │                                     │
│         └──────────────────┴─────────────────────────────────┘ │
│                            │                                     │
│                            ▼                                     │
│                   ┌─────────────────┐                            │
│                   │  File System    │                            │
│                   │  data/          │                            │
│                   │  - documents/   │                            │
│                   │  - dropzone/    │                            │
│                   │  - exports/     │                            │
│                   │  - logs/        │                            │
│                   └─────────────────┘                            │
│                                                                   │
│  ┌──────────────┐  (optional, profile: watcher)                  │
│  │  Watcher      │                                                │
│  │  Python       │  Monitors data/dropzone/                       │
│  │  filewatcher  │  Auto-ingests new files                        │
│  └──────────────┘                                                │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                         Upload Flow                              │
└─────────────────────────────────────────────────────────────────┘

1. User uploads file via Web UI
   ↓
2. Web → POST /upload (multipart/form-data) → API
   ↓
3. API → POST /process/{text|pdf|image|audio} → Worker
   ↓
4. Worker:
   - Saves file to data/documents/{document_id}/
   - Extracts text (via file_router.py)
   - Chunks text (CHUNK_SIZE=800, OVERLAP=100)
   - Generates embeddings (nomic-embed-text, 768-dim)
   - Upserts to Qdrant (jsonify2ai_chunks_768 or jsonify2ai_images_768)
   ↓
5. Returns: {ok: true, document_id, chunks, upserted, collection}
   ↓
6. Web UI polls /status for ingest_recent activity feed

┌─────────────────────────────────────────────────────────────────┐
│                         Ask/Search Flow                          │
└─────────────────────────────────────────────────────────────────┘

1. User enters query in Web UI
   ↓
2. Web → POST /ask {query, k, document_id?, answer_mode?} → API
   ↓
3. API → POST /ask → Worker
   ↓
4. Worker:
   - Embeds query (nomic-embed-text)
   - Searches Qdrant with optional filters:
     * document_id filter (if scope = "This document")
     * path filter (if path_prefix provided)
     * kind filter (text/pdf/image/audio)
   - Returns top-k results with scores
   ↓
5. If answer_mode = "synthesize" AND LLM_PROVIDER=ollama:
   - Filters snippets (min_score=0.55, max 5 snippets, 8000 chars)
   - Calls Ollama /api/generate
   - Returns {ok, mode: "llm", final: "...", sources: [...]}
   ↓
6. Else: Returns {ok, mode: "search", answer: "...", sources: [...]}
   ↓
7. Web UI displays Answer block + Sources list

┌─────────────────────────────────────────────────────────────────┐
│                         Export Flow                              │
└─────────────────────────────────────────────────────────────────┘

1. User clicks "Export JSON" or "Export ZIP" in Web UI
   ↓
2. Web → GET /export?document_id=...&collection=... → API
   OR
   Web → GET /export/archive?document_id=...&collection=... → API
   ↓
3. API → GET /export or /export/archive → Worker
   ↓
4. Worker:
   - Scrolls Qdrant collection filtered by document_id
   - Builds JSONL rows: {id, document_id, path, kind, idx, text, meta}
   - For ZIP: includes manifest.json + source file (if available)
   ↓
5. Returns: JSONL stream or ZIP archive
   ↓
6. Web UI downloads file
```

---

## 2. Entry Points + Commands

### Startup Scripts

**Windows (PowerShell):**
- `scripts/start_all.ps1` - Starts all services (qdrant, worker, api, web)
- `scripts/stop_all.ps1` - Stops all services
- `scripts/ensure_tokens.ps1` - Generates API_AUTH_TOKEN and WORKER_AUTH_TOKEN

**macOS/Linux (Bash):**
- `scripts/start_all.sh` - Starts all services
- `scripts/stop_all.sh` - Stops all services
- `scripts/ensure_tokens.sh` - Generates tokens

**Docker Compose:**
```bash
docker compose up -d qdrant worker api web
```

### Smoke/Verification Scripts

**Full System Smoke:**
- `scripts/smoke_verify.ps1` / `scripts/smoke_verify.sh`
  - Cleans containers, rebuilds, uploads seed doc
  - Tests: health, upload, search, ask, export
  - Returns JSON verdict: `{api_health_ok, worker_status_ok, api_upload_ok, search_hits_all, ask_answers, export_manifest_ok, qdrant_points, inferred_issue}`

**Ingestion Diagnosis:**
- `python scripts/ingest_diagnose.py`
  - Lightweight ingestion + search test
  - Returns: `{api_upload_ok, worker_process_ok, qdrant_points_count, search_hits, inferred_issue}`

**Export Verification:**
- `python scripts/export_smoke.py`
  - Tests `/export` and `/export/archive` endpoints
  - Returns: `{export_json_ok, export_zip_ok, docs_checked, status}`

### Development Modes

**Environment Variables (from `worker/app/config.py`):**

| Variable | Default | Purpose |
|----------|---------|---------|
| `EMBED_DEV_MODE` | `0` | `1` = Skip real embeddings, use dummy vectors (768-dim zeros) |
| `AUDIO_DEV_MODE` | `0` | `1` = Skip audio transcription, return stub text |
| `IMAGES_CAPTION` | `0` | `1` = Enable BLIP image captioning (requires transformers) |
| `AUTH_MODE` | `local` | `local` = No auth required, `strict` = Bearer token required |
| `LLM_PROVIDER` | `none` | `ollama` = Enable LLM synthesis for Ask |
| `ASK_MODE` | `search` | `search` = Retrieve only, `llm` = Full synthesis |
| `MIN_SYNTH_SCORE` | `0.55` | Minimum confidence score to run LLM synthesis |

**Collection Naming:**
- Dev mode (EMBED_DEV_MODE=1): `jsonify2ai_chunks` (no suffix)
- Prod mode: `jsonify2ai_chunks_768` (768-dim vectors)
- Images: `jsonify2ai_images_768` (always 768-dim)

---

## 3. API Surface

### API Service (Port 8082, Go/Gin)

**Health & Status:**
- `GET /health` - Basic API health check (no auth)
- `GET /health/full` - Full health (includes worker reachability, no auth)
- `GET /status` - Forwards to worker `/status` (no auth)

**File Operations:**
- `POST /upload` - Upload and process file
  - Auth: Required (except AUTH_MODE=local)
  - Rate limit: 10/min
  - Body: `multipart/form-data` with `file` field
  - Response: `{ok: true, document_id, chunks, upserted, collection}`

**Search:**
- `GET /search?q=...&k=...&document_id=...&kind=...&path=...`
  - Auth: Required
  - Query params:
    - `q` (required) - Search query
    - `k` (optional, default: 5) - Number of results
    - `document_id` (optional) - Filter by document
    - `kind` (optional) - Filter by type: text, pdf, image, audio
    - `path` (optional) - Filter by file path
  - Response: `{ok: true, results: [{id, score, text, path, document_id, kind, idx}]}`

**Ask (Q&A):**
- `POST /ask`
  - Auth: Required (optional in AUTH_MODE=local)
  - Rate limit: 30/min
  - Body: `{query: string, kind?: string, limit?: number}`
  - Query params: `document_id?`, `path_prefix?`
  - Response (with LLM): `{ok: true, mode: "llm", model, final: "...", sources: [...]}`
  - Response (search only): `{ok: true, mode: "search", answer: "...", sources: [...]}`

**Documents:**
- `GET /documents` - List all documents (no auth)
  - Response: `[{document_id, kinds, paths, counts}]`
- `DELETE /documents/:id` - Delete document (auth required, gated by AUTH_MODE or ENABLE_DOC_DELETE)
  - Response: `{ok: true, document_id, deleted_chunks, deleted_images}`

**Export:**
- `GET /export?document_id=...&collection=...` - Export as JSONL (auth required)
  - Response: JSONL stream with `Content-Disposition: attachment`
- `GET /export/archive?document_id=...&collection=...` - Export as ZIP (auth required)
  - Response: ZIP file containing:
    - `export_<document_id>_chunks.jsonl` or `export_<document_id>_images.jsonl`
    - `manifest.json` - `{request_id, timestamp, collection, document_id, counts, files: [{path, sha256, bytes}]}`
    - `source/<filename>` - Original source file (if available)

### Worker Service (Port 8090, FastAPI/Python)

**Health:**
- `GET /health` - Health check
- `GET /status` - System status with LLM reachability, telemetry, ingest_recent

**Processing:**
- `POST /process/text` - Process text file
- `POST /process/pdf` - Process PDF file
- `POST /process/image` - Process image file
- `POST /process/audio` - Process audio file
  - All require `WORKER_AUTH_TOKEN` (except AUTH_MODE=local)
  - Body: `{path: string}` (relative path to file in data/documents/)
  - Response: `{ok: true, document_id, chunks, upserted, collection}`

**Search:**
- `GET /search?q=...&k=...&document_id=...&kind=...&path=...`
- `POST /search` - Same as GET but with JSON body

**Ask:**
- `POST /ask` - Ask questions with optional LLM synthesis
  - Body: `{query: string, k?: int, document_id?: string, path_prefix?: string, answer_mode?: string}`
  - Response: Same as API `/ask`

**Documents:**
- `GET /documents` - List all documents (aggregates from both collections)
- `DELETE /documents/:id` - Delete document from both collections

**Export:**
- `GET /export` - Export document as JSONL
- `GET /export/archive` - Export document as ZIP archive

### Ask Context Retrieval

**Current Implementation:**

The Ask endpoint supports two scopes:

1. **Vault-wide retrieval** (default when `document_id` is not provided):
   - Searches across all documents in the collection
   - Returns top-k results from any document
   - Used in Web UI "All documents" scope

2. **Document-scoped retrieval** (when `document_id` is provided):
   - Filters Qdrant search by `document_id` payload field
   - Returns top-k results from a single document
   - Used in Web UI "This document" scope

**Code Location:**
- `worker/app/routers/ask.py` - `_search()` function (lines 23-71)
- `worker/app/routers/search.py` - `_build_filter()` function (lines 11-23)

**Filter Support:**
- `document_id` - Exact match filter
- `path` - Exact match filter (not prefix match currently)
- `kind` - Exact match filter (text, pdf, image, audio)

**Limitations:**
- No date/time range filters
- No metadata filters (e.g., tags, author)
- Path filter is exact match, not prefix match
- No support for multi-document scopes (e.g., "these 3 documents")

---

## 4. Data Contracts

### Document/Chunk JSONL Schema

**Fields (from `docs/DATA_MODEL.md` and `worker/app/schema/chunk_schema.py`):**

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",  // Qdrant point ID (UUID string)
  "document_id": "3fddcff6-90bb-5160-8eae-28200792d6a8",  // Deterministic UUID5 based on document hash
  "kind": "text",  // Content type: text, pdf, image, audio, csv, html, docx
  "path": "data/documents/3fddcff6-90bb-5160-8eae-28200792d6a8/example.md",  // Original file path (relative to repo root)
  "idx": 0,  // Chunk index within document (0-based)
  "text": "This is the first chunk of text from the document...",  // Chunk text content (or image caption)
  "meta": {  // Metadata object
    "ext": ".md",  // File extension
    "size": 2048,  // File size in bytes
    "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"  // SHA-256 hash of original file bytes
  }
}
```

**Additional meta fields (from `worker/app/routers/process.py`):**
- `source_ext` - Source file extension (lowercase)
- `content_sig` - Content signature (currently empty, could add file hash)
- `bytes` - Content size in bytes

**Deterministic IDs:**
- `document_id` = UUID5(namespace_seed, sha256(file_bytes))
- Same file content always produces the same `document_id`
- Enables idempotent processing (safe to re-run)

### Qdrant Payload Keys

**Indexed Fields (from `worker/app/services/qdrant_client.py`):**
- `document_id` - KEYWORD index (for filtering by document)
- `kind` - KEYWORD index (for filtering by content type)
- `path` - KEYWORD index (for filtering by file path)

**Payload Structure:**
```python
{
  "document_id": str,  # UUID5 string
  "path": str,  # Relative file path
  "kind": str,  # text, pdf, image, audio, csv, html, docx
  "idx": int,  # Chunk index (0-based)
  "text": str,  # Chunk text (or image caption)
  "meta": dict,  # Metadata object (ext, size, sha256, etc.)
}
```

**Filters Available:**
- `document_id` - Exact match (FieldCondition with MatchValue)
- `kind` - Exact match
- `path` - Exact match (not prefix match)

**Collections:**
- `jsonify2ai_chunks_768` - Text chunks (768-dim vectors, Cosine distance)
- `jsonify2ai_images_768` - Image embeddings (768-dim vectors, Cosine distance)

**Vector Dimensions:**
- Embedding model: `nomic-embed-text`
- Dimension: 768
- Distance metric: Cosine

---

## 5. Current UX Flows

### Upload Flow

1. **User Action:** Drag & drop file or click "Upload" button
2. **Web UI:** Shows upload progress, adds to ingestion activity feed
3. **API Call:** `POST /upload` with multipart/form-data
4. **Processing:** Worker saves file, extracts text, chunks, embeds, upserts to Qdrant
5. **Feedback:** Activity feed shows status (processing → processed/skipped/error)
6. **Update:** Document list refreshes, new document appears

**Activity Feed States:**
- `uploading` - File being uploaded
- `indexing` - Worker processing
- `processed` - Success (shows chunk count)
- `skipped` - Skipped with reason (unsupported_extension, empty_file, etc.)
- `error` - Processing failed

### Recent Docs Flow

1. **User Action:** View Documents section
2. **API Call:** `GET /documents` (no auth required)
3. **Display:** List of documents with:
   - Document ID (short version)
   - Kinds (text, pdf, image, etc.)
   - Paths (first 3 paths)
   - Counts (chunks per kind)
4. **Filtering:** By kind (text, pdf, image, audio, all)
5. **Sorting:** Newest, oldest, most-chunks

**Document Status:**
- `indexed` - Has chunks (counts.total > 0)
- `pending` - No chunks yet (counts.total === 0)

### Preview JSON Flow

1. **User Action:** Click "Preview JSON" on document card
2. **API Call:** `GET /export?document_id=...&collection=...`
3. **Processing:** Worker scrolls Qdrant, builds JSONL
4. **Display:** Drawer opens showing:
   - First 500 characters of JSONL
   - "Copy JSON" button
   - "Preview full JSON" link (downloads full JSONL)

**Smart Snippets (DocumentDrawer):**
- Strategy 1: Uses best matching excerpt from last global retrieve (highest score)
- Strategy 2: Falls back to `previewLines` if available
- Strategy 3: Shows hint "Preview JSON to see sample content" if no data

### Ask Flow

1. **User Action:** Enter query in Ask panel
2. **Scope Selection:**
   - "This document" - Searches only active document (requires document_id)
   - "All documents" - Searches across all documents (no document_id)
3. **Answer Mode Selection:**
   - "Retrieve" - Shows top matching sources only, no LLM synthesis
   - "Synthesize" - Uses LLM to generate answer (if LLM_PROVIDER=ollama and confidence >= MIN_SYNTH_SCORE)
4. **API Call:** `POST /ask` with `{query, k, document_id?, answer_mode?}`
5. **Processing:**
   - Worker embeds query, searches Qdrant
   - If synthesize: Filters snippets, calls Ollama, generates answer
6. **Display:**
   - **Top matching documents** (Global mode only) - Shows which documents contributed sources, with "Use this doc" buttons
   - **Answer block** (if synthesis enabled and confident) - Shows synthesized answer with "local (ollama)" badge
   - **Sources section** - Always shows matching snippets with filenames, document IDs, and scores

**"Use this doc" Workflow:**
- In Global mode results, click "Use this doc" on any document
- Switches to "This document" scope
- Sets that document as active
- Optionally switches to "Synthesize" mode (if LLM available)

### Export Flow

1. **User Action:** Click "Export JSON" or "Export ZIP" on document card or drawer
2. **API Call:**
   - `GET /export?document_id=...&collection=...` (JSONL)
   - `GET /export/archive?document_id=...&collection=...` (ZIP)
3. **Processing:** Worker scrolls Qdrant, builds JSONL or ZIP archive
4. **Download:** Browser downloads file
   - JSONL: `export_<document_id>_chunks.jsonl` or `export_<document_id>_images.jsonl`
   - ZIP: `export_<document_id>_chunks.zip` or `export_<document_id>_images.zip`

**ZIP Contents:**
- `export_<document_id>_chunks.jsonl` or `images.jsonl` - All chunks
- `manifest.json` - Export metadata (request_id, timestamp, collection, document_id, counts, files with sha256)
- `source/<filename>` - Original source file (if available under data/)
- `README.txt` - Export information

### Status/Telemetry Flow

1. **User Action:** View status chips in Web UI
2. **API Call:** `GET /status` (no auth required)
3. **Response:** `{ok, counts: {chunks, images, total}, uptime_s, ingest_total, ingest_failed, export_total, ask_synth_total, ingest_recent: [...], llm: {provider, model, reachable}}`
4. **Display:**
   - **API chip:** "API: healthy" (green) / "API: checking" (yellow) / "API: unreachable" (red)
   - **LLM chip:** "LLM: on (ollama)" (blue) / "LLM: offline" (yellow) / "LLM: off" (gray, hidden if not configured)
   - **Ingestion Activity:** Recent 50 ingest events (filename, status, chunks, images, reason, timestamps)

**Ingest Activity Fields:**
- `id` - Activity ID (UUID)
- `filename` - File name
- `status` - processing, processed, skipped, error
- `reason` - Skip/error reason code
- `chunks` - Number of chunks created
- `images` - Number of images processed
- `started_at` - ISO timestamp
- `finished_at` - ISO timestamp (null if processing)
- `kind` - Content type
- `path` - File path

---

## 6. Gaps vs "Memory Vault" Wedge

### Chat Export Ingestion Support

**What Exists:**
- ✅ JSON/JSONL parser (`worker/app/services/file_router.py` - `extract_text_from_json()`)
- ✅ Generic text extraction from JSON files
- ✅ Support for `.json` and `.jsonl` extensions

**What's Missing:**
- ❌ No specialized chat export parser (e.g., ChatGPT, Claude, Discord, Slack formats)
- ❌ No conversation structure preservation (messages, threads, participants)
- ❌ No metadata extraction (timestamps, authors, thread IDs)
- ❌ No support for chat-specific formats (Markdown chat logs, HTML chat exports)

**Recommendation:**
- Add `kind: "chat"` to parser registry
- Create `worker/app/services/parsers_chat.py` with format-specific parsers
- Preserve conversation structure in `meta` field (e.g., `meta.conversation_id`, `meta.message_id`, `meta.author`, `meta.timestamp`)
- Chunk by message or thread, not by arbitrary text boundaries

### Provenance Fields

**What Exists:**
- ✅ `document_id` - Deterministic UUID5 based on file hash
- ✅ `path` - Original file path
- ✅ `kind` - Content type
- ✅ `meta.sha256` - File hash
- ✅ `meta.size` - File size
- ✅ `meta.ext` - File extension
- ✅ `meta.source_ext` - Source file extension
- ✅ `meta.bytes` - Content size in bytes

**What's Missing:**
- ❌ No `created_at` / `updated_at` timestamps (document-level or chunk-level)
- ❌ No `author` / `creator` field
- ❌ No `tags` / `categories` field
- ❌ No `source_url` field (for web-scraped content)
- ❌ No `parent_document_id` (for nested documents)
- ❌ No `ingest_timestamp` (when document was ingested)
- ❌ No `last_accessed` timestamp
- ❌ No `version` field (for document revisions)

**Recommendation:**
- Add timestamp fields to `meta` object (ISO 8601 format)
- Add optional `meta.tags: string[]` for user-defined tags
- Add `meta.author` for documents with author information
- Add `meta.source_url` for web-scraped or imported content
- Consider adding document-level metadata table (PostgreSQL) for richer queries

### Vault-wide Retrieval

**What Exists:**
- ✅ Vault-wide search (when `document_id` is not provided)
- ✅ Filtering by `kind` (text, pdf, image, audio)
- ✅ Filtering by `path` (exact match)
- ✅ Top-k results across all documents
- ✅ Score-based ranking

**What's Missing:**
- ❌ No date/time range filters (e.g., "documents ingested in last week")
- ❌ No metadata filters (tags, author, source_url)
- ❌ No multi-document scopes (e.g., "these 3 documents")
- ❌ No document grouping in results (currently flat list)
- ❌ No "recent documents" filter (by ingest timestamp)
- ❌ No "frequently accessed" ranking
- ❌ No semantic document clustering

**Recommendation:**
- Add `meta.ingest_timestamp` to enable time-based filtering
- Add `meta.tags` to enable tag-based filtering
- Extend Qdrant filters to support range queries (date ranges)
- Add document-level aggregation in search results (group by document_id)
- Consider adding PostgreSQL metadata table for complex queries (tags, timestamps, access patterns)

### Organization Suggestions/Rules

**What Exists:**
- ✅ Document list with filter by kind
- ✅ Document list with sort (newest, oldest, most-chunks)
- ✅ Document deletion (gated by AUTH_MODE or ENABLE_DOC_DELETE)
- ✅ Document preview and export

**What's Missing:**
- ❌ No document tagging system
- ❌ No document folders/collections
- ❌ No document aliases/names (only document_id)
- ❌ No document notes/annotations
- ❌ No automatic organization (e.g., "group similar documents")
- ❌ No document relationships (e.g., "this document references that document")
- ❌ No document expiration/archival rules
- ❌ No document access control (all documents are accessible to all users)

**Recommendation:**
- Add document-level metadata table (PostgreSQL) for:
  - Tags (many-to-many relationship)
  - Aliases/names (user-friendly names)
  - Notes/annotations
  - Folders/collections
  - Access control (if multi-user)
- Add API endpoints for:
  - `POST /documents/:id/tags` - Add tags
  - `GET /documents?tags=...` - Filter by tags
  - `PUT /documents/:id/alias` - Set alias
  - `POST /documents/:id/notes` - Add notes
- Consider adding semantic document clustering (group similar documents)

---

## 7. Recommended Next 3 Milestones

### Milestone 1: Enhanced Provenance & Metadata (1-2 weeks)

**Goal:** Add timestamp and metadata fields to enable time-based filtering and richer queries.

**Scope:**
- Add `meta.ingest_timestamp` to all chunks (ISO 8601 format)
- Add `meta.created_at` and `meta.updated_at` (if available from source)
- Add `meta.author` (if available from source)
- Extend Qdrant filters to support range queries (date ranges)
- Add `GET /documents?ingested_after=...&ingested_before=...` filter

**Files Likely Touched:**
- `worker/app/routers/process.py` - Add timestamp fields to payload
- `worker/app/routers/documents.py` - Add time-based filtering
- `worker/app/routers/search.py` - Add date range filters
- `worker/app/services/qdrant_client.py` - Extend filter builder
- `web/src/App.tsx` - Add date filter UI
- `web/src/api.ts` - Add date filter params

**Endpoints Added/Extended:**
- `GET /documents?ingested_after=...&ingested_before=...` - Filter by ingest timestamp
- `GET /search?created_after=...&created_before=...` - Filter by document creation date

**UI Changes:**
- Add date range picker to Documents filter
- Show ingest timestamp in document cards
- Add "Recent documents" filter option

**Smoke Tests:**
- Verify timestamp fields in exported JSONL
- Test date range filters in search
- Test date range filters in documents list

---

### Milestone 2: Chat Export Ingestion (1-2 weeks)

**Goal:** Add specialized parser for chat export formats (ChatGPT, Claude, Discord, Slack).

**Scope:**
- Create `worker/app/services/parsers_chat.py` with format-specific parsers
- Add `kind: "chat"` to parser registry
- Preserve conversation structure in `meta` field (conversation_id, message_id, author, timestamp)
- Chunk by message or thread, not by arbitrary text boundaries
- Support common formats: ChatGPT JSON, Claude JSON, Discord HTML, Slack JSON

**Files Likely Touched:**
- `worker/app/services/file_router.py` - Add chat parser routing
- `worker/app/services/parsers_chat.py` - New file with chat parsers
- `worker/app/routers/process.py` - Add chat processing endpoint
- `docs/DATA_MODEL.md` - Document chat schema
- `web/src/App.tsx` - Add chat kind to UI

**Endpoints Added/Extended:**
- `POST /process/chat` - Process chat export file
- `GET /search?kind=chat&conversation_id=...` - Filter by conversation

**UI Changes:**
- Add "chat" to kind filter
- Show conversation metadata in document cards (author, message count)
- Add conversation view in document drawer

**Smoke Tests:**
- Test ChatGPT JSON export ingestion
- Test Claude JSON export ingestion
- Verify conversation structure in exported JSONL
- Test conversation-scoped search

---

### Milestone 3: Document Organization & Tags (1-2 weeks)

**Goal:** Add document tagging and organization features.

**Scope:**
- Create PostgreSQL metadata table for documents (tags, aliases, notes, folders)
- Add API endpoints for tag management
- Add tag filtering to search and documents list
- Add document aliases (user-friendly names)
- Add document notes/annotations

**Files Likely Touched:**
- `db/migrations/0002_document_metadata.sql` - New migration for metadata table
- `worker/app/routers/documents.py` - Add tag/alias/note endpoints
- `worker/app/services/document_metadata.py` - New service for metadata operations
- `api/internal/routes/routes.go` - Add metadata endpoints
- `web/src/App.tsx` - Add tag/alias/note UI
- `web/src/api.ts` - Add metadata API calls

**Endpoints Added/Extended:**
- `POST /documents/:id/tags` - Add tags to document
- `DELETE /documents/:id/tags` - Remove tags from document
- `GET /documents?tags=...` - Filter by tags
- `PUT /documents/:id/alias` - Set document alias
- `POST /documents/:id/notes` - Add notes to document
- `GET /search?tags=...` - Filter search by tags

**UI Changes:**
- Add tag input to document cards
- Add tag filter to Documents section
- Add alias input to document drawer
- Add notes section to document drawer
- Show tags in document cards and search results

**Smoke Tests:**
- Test tag creation and deletion
- Test tag filtering in documents list
- Test tag filtering in search
- Test alias setting and display
- Test notes creation and display

---

## 8. Where We Are / Where We Go Next

### Current State

**Strengths:**
- ✅ Solid foundation: Multi-format ingestion (text, PDF, DOCX, CSV, HTML, images, audio)
- ✅ Vector search working: Qdrant-backed semantic retrieval with optional LLM synthesis
- ✅ Document-centric workflow: Scope-based Ask (document vs. vault-wide)
- ✅ Export functionality: JSONL and ZIP exports with manifest
- ✅ Local-first architecture: Runs entirely offline, no cloud dependencies
- ✅ Idempotent processing: Safe to re-run, deterministic IDs
- ✅ Telemetry: Activity feed, status monitoring, ingest tracking

**Limitations:**
- ⚠️ Limited provenance: No timestamps, author, tags, or metadata beyond file info
- ⚠️ No chat export support: Generic JSON parser only, no conversation structure
- ⚠️ Basic organization: No tags, folders, aliases, or notes
- ⚠️ Simple filtering: Only by kind, path (exact), and document_id
- ⚠️ No document relationships: Can't link or reference documents

### Next Steps (Aligned with dump → inspect → recall → export)

**Phase 1: Enhanced Metadata (Milestone 1)**
- Add timestamps and metadata fields
- Enable time-based filtering
- Improve provenance tracking
- **Outcome:** Better inspect and recall capabilities

**Phase 2: Chat Export Support (Milestone 2)**
- Add specialized chat parsers
- Preserve conversation structure
- Enable conversation-scoped search
- **Outcome:** Support for chat export dump and recall

**Phase 3: Organization Features (Milestone 3)**
- Add tags, aliases, and notes
- Enable tag-based filtering
- Improve document discovery
- **Outcome:** Better organization and recall

### Long-term Vision

**Memory Vault Features:**
- Rich provenance (timestamps, authors, sources, relationships)
- Multi-format ingestion (chat exports, emails, web pages, etc.)
- Advanced organization (tags, folders, collections, relationships)
- Semantic document clustering (group similar documents)
- Document access patterns (frequently accessed, recently viewed)
- Document expiration/archival rules
- Multi-user support with access control

**Technical Improvements:**
- PostgreSQL metadata table for complex queries
- Hybrid search (vector + metadata filtering)
- Document-level aggregation in search results
- Semantic document clustering
- Document relationship graph
- Advanced analytics (usage patterns, document health)

---

## Appendix: Key Files Reference

### API Service (Go)
- `api/internal/routes/routes.go` - Main route registration
- `api/internal/routes/upload.go` - Upload handler
- `api/internal/routes/ask.go` - Ask handler
- `api/internal/routes/health.go` - Health endpoints
- `api/internal/middleware/auth.go` - Authentication middleware
- `api/internal/middleware/ratelimit.go` - Rate limiting middleware

### Worker Service (Python)
- `worker/app/routers/process.py` - File processing endpoints
- `worker/app/routers/ask.py` - Ask endpoint with LLM synthesis
- `worker/app/routers/search.py` - Search endpoint
- `worker/app/routers/documents.py` - Document list and delete
- `worker/app/routers/export.py` - Export endpoints
- `worker/app/routers/status.py` - Status endpoint with telemetry
- `worker/app/services/file_router.py` - File type detection and routing
- `worker/app/services/qdrant_client.py` - Qdrant operations
- `worker/app/services/embed_ollama.py` - Embedding generation
- `worker/app/config.py` - Configuration settings
- `worker/app/telemetry.py` - Telemetry and logging

### Web UI (React/TypeScript)
- `web/src/App.tsx` - Main application component
- `web/src/api.ts` - API client functions
- `web/src/components/AskPanel.tsx` - Ask panel component
- `web/src/components/DocumentList.tsx` - Document list component
- `web/src/components/DocumentDrawer.tsx` - Document details drawer
- `web/src/components/IngestionActivity.tsx` - Activity feed component
- `web/src/components/BulkActionBar.tsx` - Bulk actions component

### Configuration
- `docker-compose.yml` - Service definitions
- `.env` - Environment variables (auto-generated by ensure_tokens scripts)
- `worker/app/config.py` - Worker configuration
- `api/internal/config/config.go` - API configuration

### Documentation
- `docs/ARCHITECTURE.md` - System architecture overview
- `docs/API.md` - API reference
- `docs/DATA_MODEL.md` - Data schema documentation
- `north_star.md` - Core design principles

---

**End of Report**
