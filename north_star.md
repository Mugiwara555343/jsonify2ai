CORE THEME (unchanging — keep this in ChatGPT project instructions)

North Star: Anything → JSON.
Every input (txt, md, pdf, docx, image, audio, email, etc.) is normalized into the same chunk schema, then embedded, then stored. All extensions are just new adapters to the same contract.

Invariant contracts
1) Chunk JSON schema (stable):

{
  "id": "<deterministic-uuid-v5>",
  "document_id": "<deterministic-uuid-v5 per source file>",
  "kind": "text|pdf|docx|image|audio|email|... (one of registry kinds)",
  "path": "<relative path>",
  "idx": <0-based chunk index within document>,
  "text": "<normalized text for this chunk>",
  "meta": {
    "title": "...", "page": 1, "created_at": "...", "tags": [...], "...": "..."
  }
}

Deterministic IDs from (document_id, idx) → re-ingest is idempotent.

Never break fields or rename them. Add only backward-compatible meta keys.

2) Parser Registry (stable surface)

Map: file extension → parser(name, version, fn).

Parser must: (a) load raw file, (b) yield plain text blocks, (c) attach minimal meta.

If an optional dep is missing, skip-with-reason (don’t crash).

Text chunking is centralized (same size/overlap across kinds).

3) Embedder contract (stable)

Embeddings are 768-dim vectors in “prod” mode.

Dev mode exists but must not change the schema (just uses a fake vector).

Collection naming:

Base (dev vectors): jsonify2ai_chunks

Prod (768-dim vectors): jsonify2ai_chunks_768

Query-time and ingest-time must target the same collection.

4) Environment is the truth

Read only from .env (or the shell env). Never hardcode.

Context rule:

If running on host, use localhost-style URLs.

If running in containers, use host.docker.internal to reach host services.

Core vars (names don’t change):

QDRANT_URL, QDRANT_COLLECTION, EMBEDDINGS_MODEL, EMBEDDING_DIM,
EMBED_DEV_MODE, OLLAMA_URL, ASK_MODE, ASK_MODEL.

5) Ops rules

Momentum mode: one milestone at a time; stop on success.

Step-by-step: one command, wait for output.

Proactive sweep: when we fix a pattern (e.g., from __future__ order), fix all entrypoints of the same class.

Idempotency first: re-runs never duplicate or crash; they skip with reasons.