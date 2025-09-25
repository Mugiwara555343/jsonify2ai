# worker/app/routers/process.py
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

# import the status hook (safe: status.py does not import process.py)
from worker.app.routers.status import record_ingest_summary
from worker.app.config import settings  # CHUNK_SIZE/OVERLAP, collections, etc.
from worker.app.utils.docids import document_id_for_relpath, canonicalize_relpath
from worker.app.services.qdrant_client import (
    get_qdrant_client,
    upsert_points,
    delete_by_document_id,
    ensure_collection,
)
from worker.app.services.embed_ollama import embed_texts
from worker.app.services.file_router import extract_text_auto
from worker.app.services.chunker import chunk_text
from worker.app.services.image_caption import caption_image
from worker.app.services.parse_audio import transcribe_audio

log = logging.getLogger(__name__)
router = APIRouter(prefix="/process", tags=["process"])


# New unified payload model for all process endpoints
class ProcessPayload(BaseModel):
    document_id: Optional[str] = None
    path: Optional[str] = None

    @field_validator("document_id", mode="before")
    def _strip_docid(cls, v):
        return v.strip() if isinstance(v, str) else v

    def require_docid(self) -> str:
        """
        Return a valid document_id. If not provided, compute it from path using the existing
        canonical doc-id helper already used in ingest/discovery. Do NOT reimplement hashing here.
        """
        if self.document_id:
            return self.document_id
        if not self.path:
            raise ValueError("either document_id or path is required")
        # Reuse the existing helper used elsewhere in worker to compute document_id from a rel POSIX path.
        from worker.app.utils.docids import document_id_for_relpath

        # Normalize to the same relpath that ingest uses (e.g., without leading 'data/dropzone/').
        rel = self.path.replace("\\", "/")
        if rel.startswith("data/dropzone/"):
            rel = rel[len("data/dropzone/") :]
        return str(document_id_for_relpath(rel))


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
async def process_text(request: Request):
    """
    Ingest a text file using the same pipeline as scripts/ingest_dropzone.py.

    • Parse file using extract_text_auto (same as CLI)
    • Chunk using config sizes, embed, upsert to Qdrant collection
    • Return precise summary with real counts
    """
    payload = ProcessPayload(**(await request.json()))
    try:
        docid = payload.require_docid()
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=422)

    # Normalize rel_path (same as CLI)
    rel_path = payload.path.replace("\\", "/")
    if rel_path.startswith("data/dropzone/"):
        rel_path = rel_path[len("data/dropzone/") :]

    # Create absolute path for canonicalize_relpath
    abs_dropzone = Path("data/dropzone").resolve()
    abs_file_path = (abs_dropzone / rel_path).resolve()
    rel_path = canonicalize_relpath(abs_file_path, abs_dropzone)

    # Compute document_id if missing (same as CLI)
    docid = payload.document_id or str(document_id_for_relpath(rel_path))

    # Parse file using same parser as CLI
    abs_path = f"data/dropzone/{rel_path}"
    try:
        raw_text = extract_text_auto(abs_path)
    except Exception as e:
        log.warning("[process/text] parse failed: %s", e)
        raise HTTPException(status_code=400, detail=f"failed to parse file: {e}")

    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="no content to process")

    # Ensure collection (same as CLI)
    client = get_qdrant_client()
    ensure_collection(
        client=client,
        name=settings.QDRANT_COLLECTION,
        dim=settings.EMBEDDING_DIM,
    )

    # Delete existing points for this document (idempotent re-ingest)
    try:
        delete_by_document_id(docid, client=client)
        log.info("[process/text] cleared existing points for doc=%s", docid)
    except Exception as e:
        log.warning(
            "[process/text] delete_by_document_id failed doc=%s err=%s", docid, e
        )

    # Chunk using config defaults (same as CLI)
    chunks = chunk_text(
        raw_text,
        size=int(settings.CHUNK_SIZE),
        overlap=int(settings.CHUNK_OVERLAP),
    )
    if not chunks:
        raise HTTPException(status_code=400, detail="no content to process")

    # Embed (same as CLI)
    vectors = embed_texts(chunks)

    # Build items with deterministic IDs (same as CLI)
    items = []
    for idx, (text_chunk, vec) in enumerate(zip(chunks, vectors)):
        point_id = str(uuid.uuid4())  # Use same ID scheme as CLI
        payload_data = {
            "document_id": docid,
            "path": rel_path,
            "kind": "text",
            "idx": idx,
            "text": text_chunk,
            "meta": {
                "source_ext": Path(abs_path).suffix.lower(),
                "content_sig": "",  # Could add file hash if needed
                "bytes": len(raw_text.encode("utf-8")),
            },
        }
        items.append((point_id, vec, payload_data))

    # Upsert to collection (same as CLI)
    upserted = upsert_points(
        items,
        collection_name=settings.QDRANT_COLLECTION,
        client=client,
        ensure=False,
    )

    # Record status summary
    try:
        record_ingest_summary(document_id=docid, chunks_upserted=upserted)
    except Exception as e:
        log.debug("[process/text] record_ingest_summary failed: %s", e)

    return ProcessTextResponse(
        ok=True,
        document_id=docid,
        chunks=len(chunks),
        embedded=len(vectors),
        upserted=upserted,
        collection=settings.QDRANT_COLLECTION,
    )


@router.post("/pdf", response_model=ProcessTextResponse)
async def process_pdf(request: Request):
    """Process PDF files using the same pipeline as text."""
    payload = ProcessPayload(**(await request.json()))
    try:
        docid = payload.require_docid()
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=422)

    # Normalize rel_path (same as text)
    rel_path = payload.path.replace("\\", "/")
    if rel_path.startswith("data/dropzone/"):
        rel_path = rel_path[len("data/dropzone/") :]

    # Create absolute path for canonicalize_relpath
    abs_dropzone = Path("data/dropzone").resolve()
    abs_file_path = (abs_dropzone / rel_path).resolve()
    rel_path = canonicalize_relpath(abs_file_path, abs_dropzone)

    # Compute document_id if missing
    docid = payload.document_id or str(document_id_for_relpath(rel_path))

    # Parse PDF using same parser as CLI
    abs_path = f"data/dropzone/{rel_path}"
    try:
        raw_text = extract_text_auto(abs_path)
    except Exception as e:
        log.warning("[process/pdf] parse failed: %s", e)
        raise HTTPException(status_code=400, detail=f"failed to parse PDF: {e}")

    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="no content to process")

    # Ensure collection (same as text)
    client = get_qdrant_client()
    ensure_collection(
        client=client,
        name=settings.QDRANT_COLLECTION,
        dim=settings.EMBEDDING_DIM,
    )

    # Delete existing points for this document
    try:
        delete_by_document_id(docid, client=client)
        log.info("[process/pdf] cleared existing points for doc=%s", docid)
    except Exception as e:
        log.warning(
            "[process/pdf] delete_by_document_id failed doc=%s err=%s", docid, e
        )

    # Chunk using config defaults
    chunks = chunk_text(
        raw_text,
        size=int(settings.CHUNK_SIZE),
        overlap=int(settings.CHUNK_OVERLAP),
    )
    if not chunks:
        raise HTTPException(status_code=400, detail="no content to process")

    # Embed
    vectors = embed_texts(chunks)

    # Build items with deterministic IDs
    items = []
    for idx, (text_chunk, vec) in enumerate(zip(chunks, vectors)):
        point_id = str(uuid.uuid4())
        payload_data = {
            "document_id": docid,
            "path": rel_path,
            "kind": "pdf",
            "idx": idx,
            "text": text_chunk,
            "meta": {
                "source_ext": Path(abs_path).suffix.lower(),
                "content_sig": "",
                "bytes": len(raw_text.encode("utf-8")),
            },
        }
        items.append((point_id, vec, payload_data))

    # Upsert to collection
    upserted = upsert_points(
        items,
        collection_name=settings.QDRANT_COLLECTION,
        client=client,
        ensure=False,
    )

    # Record status summary
    try:
        record_ingest_summary(document_id=docid, chunks_upserted=upserted)
    except Exception as e:
        log.debug("[process/pdf] record_ingest_summary failed: %s", e)

    return ProcessTextResponse(
        ok=True,
        document_id=docid,
        chunks=len(chunks),
        embedded=len(vectors),
        upserted=upserted,
        collection=settings.QDRANT_COLLECTION,
    )


@router.post("/image", response_model=ProcessTextResponse)
async def process_image(request: Request):
    """Process image files using image captioning."""
    payload = ProcessPayload(**(await request.json()))
    try:
        docid = payload.require_docid()
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=422)

    # Normalize rel_path
    rel_path = payload.path.replace("\\", "/")
    if rel_path.startswith("data/dropzone/"):
        rel_path = rel_path[len("data/dropzone/") :]

    # Create absolute path for canonicalize_relpath
    abs_dropzone = Path("data/dropzone").resolve()
    abs_file_path = (abs_dropzone / rel_path).resolve()
    rel_path = canonicalize_relpath(abs_file_path, abs_dropzone)

    # Compute document_id if missing
    docid = payload.document_id or str(document_id_for_relpath(rel_path))

    # Get image caption
    abs_path = f"data/dropzone/{rel_path}"
    try:
        caption = caption_image(abs_path)
        if not caption.strip():
            caption = f"image: {rel_path}"
    except Exception as e:
        log.warning("[process/image] caption failed: %s", e)
        caption = f"image: {rel_path}"

    # Ensure images collection
    client = get_qdrant_client()
    ensure_collection(
        client=client,
        name=settings.QDRANT_COLLECTION_IMAGES,
        dim=settings.EMBEDDING_DIM,
    )

    # Delete existing points for this document
    try:
        delete_by_document_id(docid, client=client)
        log.info("[process/image] cleared existing points for doc=%s", docid)
    except Exception as e:
        log.warning(
            "[process/image] delete_by_document_id failed doc=%s err=%s", docid, e
        )

    # Create single chunk from caption
    chunks = [caption]
    vectors = embed_texts(chunks)

    # Build items
    items = []
    for idx, (text_chunk, vec) in enumerate(zip(chunks, vectors)):
        point_id = str(uuid.uuid4())
        payload_data = {
            "document_id": docid,
            "path": rel_path,
            "kind": "image",
            "idx": idx,
            "text": text_chunk,
            "meta": {
                "source_ext": Path(abs_path).suffix.lower(),
                "content_sig": "",
                "bytes": 0,  # Images don't have text bytes
            },
        }
        items.append((point_id, vec, payload_data))

    # Upsert to images collection
    upserted = upsert_points(
        items,
        collection_name=settings.QDRANT_COLLECTION_IMAGES,
        client=client,
        ensure=False,
    )

    # Record status summary
    try:
        record_ingest_summary(document_id=docid, chunks_upserted=upserted)
    except Exception as e:
        log.debug("[process/image] record_ingest_summary failed: %s", e)

    return ProcessTextResponse(
        ok=True,
        document_id=docid,
        chunks=len(chunks),
        embedded=len(vectors),
        upserted=upserted,
        collection=settings.QDRANT_COLLECTION_IMAGES,
    )


@router.post("/audio", response_model=ProcessTextResponse)
async def process_audio(request: Request):
    """Process audio files using transcription."""
    payload = ProcessPayload(**(await request.json()))
    try:
        docid = payload.require_docid()
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=422)

    # Check for dev mode short-circuit
    if getattr(settings, "AUDIO_DEV_MODE", 0) == 1:
        return ProcessTextResponse(
            ok=True,
            document_id=docid,
            chunks=0,
            embedded=0,
            upserted=0,
            collection=settings.QDRANT_COLLECTION,
        )

    # Normalize rel_path
    rel_path = payload.path.replace("\\", "/")
    if rel_path.startswith("data/dropzone/"):
        rel_path = rel_path[len("data/dropzone/") :]

    # Create absolute path for canonicalize_relpath
    abs_dropzone = Path("data/dropzone").resolve()
    abs_file_path = (abs_dropzone / rel_path).resolve()
    rel_path = canonicalize_relpath(abs_file_path, abs_dropzone)

    # Compute document_id if missing
    docid = payload.document_id or str(document_id_for_relpath(rel_path))

    # Transcribe audio
    abs_path = f"data/dropzone/{rel_path}"
    try:
        transcript = transcribe_audio(abs_path)
        if not transcript.strip():
            raise HTTPException(status_code=400, detail="no content to process")
    except Exception as e:
        log.warning("[process/audio] transcription failed: %s", e)
        raise HTTPException(status_code=400, detail=f"failed to transcribe audio: {e}")

    # Ensure collection (same as text)
    client = get_qdrant_client()
    ensure_collection(
        client=client,
        name=settings.QDRANT_COLLECTION,
        dim=settings.EMBEDDING_DIM,
    )

    # Delete existing points for this document
    try:
        delete_by_document_id(docid, client=client)
        log.info("[process/audio] cleared existing points for doc=%s", docid)
    except Exception as e:
        log.warning(
            "[process/audio] delete_by_document_id failed doc=%s err=%s", docid, e
        )

    # Chunk transcript using config defaults
    chunks = chunk_text(
        transcript,
        size=int(settings.CHUNK_SIZE),
        overlap=int(settings.CHUNK_OVERLAP),
    )
    if not chunks:
        raise HTTPException(status_code=400, detail="no content to process")

    # Embed
    vectors = embed_texts(chunks)

    # Build items with deterministic IDs
    items = []
    for idx, (text_chunk, vec) in enumerate(zip(chunks, vectors)):
        point_id = str(uuid.uuid4())
        payload_data = {
            "document_id": docid,
            "path": rel_path,
            "kind": "audio",
            "idx": idx,
            "text": text_chunk,
            "meta": {
                "source_ext": Path(abs_path).suffix.lower(),
                "content_sig": "",
                "bytes": len(transcript.encode("utf-8")),
            },
        }
        items.append((point_id, vec, payload_data))

    # Upsert to collection
    upserted = upsert_points(
        items,
        collection_name=settings.QDRANT_COLLECTION,
        client=client,
        ensure=False,
    )

    # Record status summary
    try:
        record_ingest_summary(document_id=docid, chunks_upserted=upserted)
    except Exception as e:
        log.debug("[process/audio] record_ingest_summary failed: %s", e)

    return ProcessTextResponse(
        ok=True,
        document_id=docid,
        chunks=len(chunks),
        embedded=len(vectors),
        upserted=upserted,
        collection=settings.QDRANT_COLLECTION,
    )
