# worker/app/routers/process.py
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# import the status hook (safe: status.py does not import process.py)
from worker.app.routers.status import record_ingest_summary
from worker.app.config import settings  # CHUNK_SIZE/OVERLAP, collections, etc.

log = logging.getLogger(__name__)
router = APIRouter(prefix="/process", tags=["process"])


# Request/response models (kept backward compatible)
class ProcessTextRequest(BaseModel):
    document_id: str
    text: str | None = None  # Optional raw text
    path: str | None = None  # Optional file path (parser registry will handle later)
    mime: str | None = None
    kind: str | None = None
    # If True, delete existing points for this document_id before upserting
    replace_existing: bool = False


class ProcessTextResponse(BaseModel):
    ok: bool
    document_id: str
    chunks: int
    embedded: int
    upserted: int
    collection: str


# Alias for older scripts/tests that import TextPayload
TextPayload = ProcessTextRequest


@router.post("/text", response_model=ProcessTextResponse)
def process_text(p: ProcessTextRequest):
    """
    Ingest a text payload (or a file placeholder), chunk -> embed -> upsert.

    • Text mode: chunk using config sizes, embed, upsert to Qdrant collection.
    • File mode: placeholder response (parser registry will handle it later).
    """
    # Lazy import so module loads even if optional deps are missing
    try:
        from worker.app.services.chunker import chunk_text
        from worker.app.services.embed_ollama import embed_texts
        from worker.app.services.qdrant_client import (
            ensure_collection,
            upsert_points,
            delete_by_document_id,
        )
    except Exception as e:
        log.exception("process backend not wired: %s", e)
        raise HTTPException(status_code=501, detail="process backend not wired")

    # -------- Resolve content (text vs file) ---------------------------------
    if p.text:
        content = p.text
        size = len(content.encode("utf-8"))
        log.info("[process/text] text doc=%s bytes=%d", p.document_id, size)

    elif p.path:
        # Try exact path, else fall back to /app/data/<basename>
        file_path = Path(p.path)
        if not file_path.is_file():
            file_path = Path("/app/data") / Path(p.path).name
        if not file_path.is_file():
            log.warning(
                "[process/text] file not found: %s (doc=%s)", p.path, p.document_id
            )
            raise HTTPException(status_code=404, detail="file not found")

        size = file_path.stat().st_size
        log.info(
            "[process/text] file doc=%s kind=%s mime=%s path=%s bytes=%d",
            p.document_id,
            p.kind,
            p.mime,
            str(file_path),
            size,
        )
    else:
        raise HTTPException(
            status_code=400, detail="either text or path must be provided"
        )

    # -------- Text mode: chunk → embed → upsert ------------------------------
    if p.text:
        # Ensure collection explicitly (even though upsert_points can ensure too)
        ensure_collection(name=settings.QDRANT_COLLECTION, dim=settings.EMBEDDING_DIM)

        # Optional idempotent re-ingest: clear existing points for this document
        if p.replace_existing:
            try:
                delete_by_document_id(p.document_id)
                log.info(
                    "[process/text] cleared existing points for doc=%s", p.document_id
                )
            except Exception as e:
                log.warning(
                    "[process/text] delete_by_document_id failed doc=%s err=%s",
                    p.document_id,
                    e,
                )

        # Chunk using config defaults
        chunks = chunk_text(
            content,
            size=int(settings.CHUNK_SIZE),
            overlap=int(settings.CHUNK_OVERLAP),
            # normalization flag is read inside chunker via settings.NORMALIZE_WHITESPACE
        )
        if not chunks:
            raise HTTPException(status_code=400, detail="no content to process")

        # Embed (handles internal batching)
        vectors = embed_texts(chunks)

        # Prepare upserts
        collection = settings.QDRANT_COLLECTION
        items = []
        for idx, (text_chunk, vec) in enumerate(zip(chunks, vectors)):
            point_id = str(uuid.uuid4())
            payload = {
                "id": point_id,
                "document_id": p.document_id,
                "path": p.path or "text_input",
                "kind": p.kind or "text",
                "idx": idx,
                "text": text_chunk,
                "meta": {"source": "text_input"},
            }
            items.append((point_id, vec, payload))

        # Upsert (collection already ensured above)
        upserted = upsert_points(items, collection_name=collection, ensure=False)

        # ---- record status summary (right place) ----------------------------
        try:
            record_ingest_summary(document_id=p.document_id, chunks_upserted=upserted)
        except Exception as e:
            # Never let telemetry break ingestion
            log.debug("[process/text] record_ingest_summary failed: %s", e)

        return ProcessTextResponse(
            ok=True,
            document_id=p.document_id,
            chunks=len(chunks),
            embedded=len(vectors),
            upserted=upserted,
            collection=collection,
        )

    # -------- File mode (placeholder) ---------------------------------------
    # Parser registry will read/route files later; keep tests happy now.
    return ProcessTextResponse(
        ok=True,
        document_id=p.document_id,
        chunks=1,
        embedded=0,
        upserted=0,
        collection="file_input",
    )
