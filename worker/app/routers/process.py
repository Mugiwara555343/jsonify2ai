# worker/app/routers/process.py
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

# import the status hook (safe: status.py does not import process.py)
from worker.app.routers.status import record_ingest_summary
from worker.app.config import settings  # CHUNK_SIZE/OVERLAP, collections, etc.
from worker.app.utils.docids import (
    document_id_for_relpath,
    canonicalize_relpath,
    chunk_id_for,
)
from worker.app.services.qdrant_client import (
    get_qdrant_client,
    upsert_points,
    delete_by_document_id,
    ensure_collection,
)
from worker.app.services.embed_ollama import embed_texts
from worker.app.services.file_router import extract_text_auto
from worker.app.services.chunker import chunk_text
from worker.app.services.images import generate_caption
from worker.app.services.parse_audio import transcribe_audio
from worker.app.telemetry import telemetry
from worker.app.dependencies.auth import require_auth

log = logging.getLogger(__name__)
router = APIRouter(prefix="/process", tags=["process"])


def _get_filename_from_path(path: str) -> str:
    """Extract filename from path."""
    if not path:
        return "unknown"
    return Path(path).name


def _build_meta_with_provenance(
    base_meta: dict, source_system: str = "filesystem"
) -> dict:
    """Add ingested_at and source_system to meta, preserving existing fields."""
    from datetime import datetime, timezone

    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    now_ts = int(datetime.now(timezone.utc).timestamp())

    meta = base_meta.copy()
    if not meta.get("ingested_at"):
        meta["ingested_at"] = now_iso
    if not meta.get("ingested_at_ts"):
        meta["ingested_at_ts"] = now_ts
    if not meta.get("source_system"):
        meta["source_system"] = source_system
    return meta


def _record_ingest_start(path: str, kind: str) -> str:
    """Record ingest activity start and return activity_id."""
    try:
        filename = _get_filename_from_path(path)
        return telemetry.record_ingest_activity(
            path=path,
            filename=filename,
            kind=kind,
            status="processing",
            reason="",
            started_at=None,  # Will be set to now
        )
    except Exception as e:
        log.debug(f"Failed to record ingest start: {e}")
        return str(uuid.uuid4())


def _record_ingest_success(
    activity_id: str,
    path: str,
    kind: str,
    chunks: int,
    images: int = 0,
    bytes: int = 0,
):
    """Record ingest activity success."""
    try:
        filename = _get_filename_from_path(path)
        from datetime import datetime, timezone

        finished_at = datetime.now(timezone.utc).isoformat()
        telemetry.record_ingest_activity(
            activity_id=activity_id,
            path=path,
            filename=filename,
            kind=kind,
            status="processed",
            reason="ok",
            chunks=chunks,
            images=images,
            bytes=bytes,
            finished_at=finished_at,
        )
    except Exception as e:
        log.debug(f"Failed to record ingest success: {e}")


def _record_ingest_skip(
    activity_id: str,
    path: str,
    kind: str,
    reason: str,
):
    """Record ingest activity skip."""
    try:
        filename = _get_filename_from_path(path)
        from datetime import datetime, timezone

        finished_at = datetime.now(timezone.utc).isoformat()
        telemetry.record_ingest_activity(
            activity_id=activity_id,
            path=path,
            filename=filename,
            kind=kind,
            status="skipped",
            reason=reason,
            finished_at=finished_at,
        )
    except Exception as e:
        log.debug(f"Failed to record ingest skip: {e}")


def _record_ingest_error(
    activity_id: str,
    path: str,
    kind: str,
    reason: str,
):
    """Record ingest activity error."""
    try:
        filename = _get_filename_from_path(path)
        from datetime import datetime, timezone

        finished_at = datetime.now(timezone.utc).isoformat()
        # Keep reason short (no full trace)
        short_reason = reason[:100] if len(reason) > 100 else reason
        telemetry.record_ingest_activity(
            activity_id=activity_id,
            path=path,
            filename=filename,
            kind=kind,
            status="error",
            reason=short_reason,
            finished_at=finished_at,
        )
    except Exception as e:
        log.debug(f"Failed to record ingest error: {e}")


def _instrument_process_request(
    request: Request, kind: str, docid: str
) -> tuple[str, float]:
    """Helper to instrument process requests with telemetry."""
    import uuid
    import time

    request_id = str(uuid.uuid4())
    start_time = time.time()

    # Check for watcher header
    from_watcher = request.headers.get("X-From-Watcher") == "1"
    if from_watcher:
        telemetry.increment("watcher_triggers_total")

    # Log request start
    telemetry.log_json(
        "process_start",
        level="info",
        request_id=request_id,
        kind=kind,
        document_id=docid,
        from_watcher=from_watcher,
    )

    return request_id, start_time


def _log_process_completion(
    request_id: str,
    kind: str,
    docid: str,
    success: bool,
    duration_ms: int,
    error: str = None,
):
    """Helper to log process completion."""
    if success:
        telemetry.increment("ingest_total")
        telemetry.log_json(
            "process_success",
            level="info",
            request_id=request_id,
            kind=kind,
            document_id=docid,
            duration_ms=duration_ms,
            status="success",
        )
    else:
        telemetry.increment("ingest_failed")
        telemetry.set_error(error or "Unknown error")
        telemetry.log_json(
            "process_failure",
            level="error",
            request_id=request_id,
            kind=kind,
            document_id=docid,
            duration_ms=duration_ms,
            status="error",
            error=error,
        )


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
async def process_text(request: Request, _: bool = Depends(require_auth)):
    """
    Ingest a text file using the same pipeline as scripts/ingest_dropzone.py.

    • Parse file using extract_text_auto (same as CLI)
    • Chunk using config sizes, embed, upsert to Qdrant collection
    • Return precise summary with real counts
    """
    import time

    payload = ProcessPayload(**(await request.json()))
    try:
        docid = payload.require_docid()
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=422)

    # Instrument request
    request_id, start_time = _instrument_process_request(request, "text", docid)

    # Normalize rel_path before recording (same as CLI)
    rel_path = payload.path or ""
    rel_path = rel_path.replace("\\", "/")
    if rel_path.startswith("data/dropzone/"):
        rel_path = rel_path[len("data/dropzone/") :]

    # Record ingest activity start (use normalized path)
    activity_id = None
    try:
        activity_id = _record_ingest_start(rel_path, "text")
    except Exception as e:
        log.debug(f"Failed to record ingest start: {e}")

    try:
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
            if activity_id:
                _record_ingest_error(activity_id, rel_path, "text", "parse_failed")
            raise HTTPException(status_code=400, detail=f"failed to parse file: {e}")

        if not raw_text.strip():
            if activity_id:
                _record_ingest_skip(activity_id, rel_path, "text", "empty_file")
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
            base_meta = {
                "source_ext": Path(abs_path).suffix.lower(),
                "content_sig": "",  # Could add file hash if needed
                "bytes": len(raw_text.encode("utf-8")),
            }
            payload_data = {
                "document_id": docid,
                "path": rel_path,
                "kind": "text",
                "idx": idx,
                "text": text_chunk,
                "meta": _build_meta_with_provenance(base_meta),
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

        # Record ingest activity success
        if activity_id:
            _record_ingest_success(
                activity_id=activity_id,
                path=rel_path,
                kind="text",
                chunks=upserted,
                bytes=len(raw_text.encode("utf-8")),
            )

        # Log success
        duration_ms = int((time.time() - start_time) * 1000)
        _log_process_completion(request_id, "text", docid, True, duration_ms)

        return ProcessTextResponse(
            ok=True,
            document_id=docid,
            chunks=len(chunks),
            embedded=len(vectors),
            upserted=upserted,
            collection=settings.QDRANT_COLLECTION,
        )

    except HTTPException:
        # Re-raise HTTP exceptions (already recorded skip/error above)
        raise
    except Exception as e:
        # Log failure
        duration_ms = int((time.time() - start_time) * 1000)
        _log_process_completion(request_id, "text", docid, False, duration_ms, str(e))
        # Record ingest activity error
        if activity_id:
            _record_ingest_error(activity_id, rel_path, "text", "worker_error")
        raise


@router.post("/pdf", response_model=ProcessTextResponse)
async def process_pdf(request: Request, _: bool = Depends(require_auth)):
    """Process PDF files using the same pipeline as text."""
    import time

    payload = ProcessPayload(**(await request.json()))
    try:
        docid = payload.require_docid()
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=422)

    # Instrument request
    request_id, start_time = _instrument_process_request(request, "pdf", docid)

    # Normalize rel_path before recording (same as text)
    rel_path = payload.path or ""
    rel_path = rel_path.replace("\\", "/")
    if rel_path.startswith("data/dropzone/"):
        rel_path = rel_path[len("data/dropzone/") :]

    # Record ingest activity start (use normalized path)
    activity_id = None
    try:
        activity_id = _record_ingest_start(rel_path, "pdf")
    except Exception as e:
        log.debug(f"Failed to record ingest start: {e}")

    try:
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
            if activity_id:
                _record_ingest_error(activity_id, rel_path, "pdf", "parse_failed")
            raise HTTPException(status_code=400, detail=f"failed to parse PDF: {e}")

        if not raw_text.strip():
            if activity_id:
                _record_ingest_skip(activity_id, rel_path, "pdf", "empty_file")
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
            base_meta = {
                "source_ext": Path(abs_path).suffix.lower(),
                "content_sig": "",
                "bytes": len(raw_text.encode("utf-8")),
            }
            payload_data = {
                "document_id": docid,
                "path": rel_path,
                "kind": "pdf",
                "idx": idx,
                "text": text_chunk,
                "meta": _build_meta_with_provenance(base_meta),
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

        # Record ingest activity success
        if activity_id:
            _record_ingest_success(
                activity_id=activity_id,
                path=rel_path,
                kind="pdf",
                chunks=upserted,
                bytes=len(raw_text.encode("utf-8")),
            )

        # Log success
        duration_ms = int((time.time() - start_time) * 1000)
        _log_process_completion(request_id, "pdf", docid, True, duration_ms)

        return ProcessTextResponse(
            ok=True,
            document_id=docid,
            chunks=len(chunks),
            embedded=len(vectors),
            upserted=upserted,
            collection=settings.QDRANT_COLLECTION,
        )

    except HTTPException:
        # Re-raise HTTP exceptions (already recorded skip/error above)
        raise
    except Exception as e:
        # Log failure
        duration_ms = int((time.time() - start_time) * 1000)
        _log_process_completion(request_id, "pdf", docid, False, duration_ms, str(e))
        # Record ingest activity error
        if activity_id:
            _record_ingest_error(activity_id, rel_path, "pdf", "worker_error")
        raise


@router.post("/image", response_model=ProcessTextResponse)
async def process_image(request: Request, _: bool = Depends(require_auth)):
    """Process image files using image captioning."""
    import time

    payload = ProcessPayload(**(await request.json()))
    try:
        docid = payload.require_docid()
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=422)

    # Instrument request
    request_id, start_time = _instrument_process_request(request, "image", docid)

    # Normalize rel_path before recording
    rel_path = payload.path or ""
    rel_path = rel_path.replace("\\", "/")
    if rel_path.startswith("data/dropzone/"):
        rel_path = rel_path[len("data/dropzone/") :]

    # Record ingest activity start (use normalized path)
    activity_id = None
    try:
        activity_id = _record_ingest_start(rel_path, "image")
    except Exception as e:
        log.debug(f"Failed to record ingest start: {e}")

    try:
        # Create absolute path for canonicalize_relpath
        abs_dropzone = Path("data/dropzone").resolve()
        abs_file_path = (abs_dropzone / rel_path).resolve()
        rel_path = canonicalize_relpath(abs_file_path, abs_dropzone)

        # Compute document_id if missing
        docid = payload.document_id or str(document_id_for_relpath(rel_path))

        # Get image caption
        abs_path = f"data/dropzone/{rel_path}"
        caption = generate_caption(str(abs_path))
        text = caption if caption else f"image: {rel_path}"

        # Ensure images collection
        client = get_qdrant_client()
        ensure_collection(
            client=client,
            name=settings.QDRANT_COLLECTION_IMAGES,
            dim=settings.EMBEDDING_DIM,
        )

        # Delete existing points for this document
        try:
            delete_by_document_id(
                docid, collection_name=settings.QDRANT_COLLECTION_IMAGES, client=client
            )
            log.info("[process/image] cleared existing points for doc=%s", docid)
        except Exception as e:
            log.warning(
                "[process/image] delete_by_document_id failed doc=%s err=%s", docid, e
            )

        # Create single chunk from caption
        chunks = [text]
        vectors = embed_texts(chunks)

        # Build items with deterministic IDs
        items = []
        for idx, (text_chunk, vec) in enumerate(zip(chunks, vectors)):
            point_id = str(chunk_id_for(uuid.UUID(docid), idx))
            base_meta = {
                "source_ext": Path(abs_path).suffix.lower(),
                "content_sig": "",
                "bytes": 0,  # Images don't have text bytes
            }
            payload_data = {
                "document_id": docid,
                "path": rel_path,
                "kind": "image",
                "idx": idx,
                "text": text_chunk,
                "meta": _build_meta_with_provenance(base_meta),
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

        # Record ingest activity success
        if activity_id:
            _record_ingest_success(
                activity_id=activity_id,
                path=rel_path,
                kind="image",
                chunks=0,  # Images go to images collection, not chunks
                images=upserted,
                bytes=0,
            )

        # Log success
        duration_ms = int((time.time() - start_time) * 1000)
        _log_process_completion(request_id, "image", docid, True, duration_ms)

        return ProcessTextResponse(
            ok=True,
            document_id=docid,
            chunks=len(chunks),
            embedded=len(vectors),
            upserted=upserted,
            collection=settings.QDRANT_COLLECTION_IMAGES,
        )

    except Exception as e:
        # Log failure
        duration_ms = int((time.time() - start_time) * 1000)
        _log_process_completion(request_id, "image", docid, False, duration_ms, str(e))
        # Record ingest activity error
        if activity_id:
            _record_ingest_error(activity_id, rel_path, "image", "worker_error")
        raise


@router.post("/audio", response_model=ProcessTextResponse)
async def process_audio(request: Request, _: bool = Depends(require_auth)):
    """Process audio files using transcription."""
    import time

    payload = ProcessPayload(**(await request.json()))
    try:
        docid = payload.require_docid()
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=422)

    # Instrument request
    request_id, start_time = _instrument_process_request(request, "audio", docid)

    # Normalize rel_path before recording
    rel_path = payload.path or ""
    rel_path = rel_path.replace("\\", "/")
    if rel_path.startswith("data/dropzone/"):
        rel_path = rel_path[len("data/dropzone/") :]

    # Record ingest activity start (use normalized path)
    activity_id = None
    try:
        activity_id = _record_ingest_start(rel_path, "audio")
    except Exception as e:
        log.debug(f"Failed to record ingest start: {e}")

    # Check for dev mode short-circuit
    if getattr(settings, "AUDIO_DEV_MODE", 0) == 1:
        # Record skip for dev mode
        if activity_id:
            _record_ingest_skip(activity_id, rel_path, "audio", "audio_dev_mode")
        # Log success for dev mode
        duration_ms = int((time.time() - start_time) * 1000)
        _log_process_completion(request_id, "audio", docid, True, duration_ms)
        return ProcessTextResponse(
            ok=True,
            document_id=docid,
            chunks=0,
            embedded=0,
            upserted=0,
            collection=settings.QDRANT_COLLECTION,
        )

    try:
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
            raise HTTPException(
                status_code=400, detail=f"failed to transcribe audio: {e}"
            )

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
            point_id = str(chunk_id_for(uuid.UUID(docid), idx))
            base_meta = {
                "source_ext": Path(abs_path).suffix.lower(),
                "content_sig": "",
                "bytes": len(transcript.encode("utf-8")),
            }
            payload_data = {
                "document_id": docid,
                "path": rel_path,
                "kind": "audio",
                "idx": idx,
                "text": text_chunk,
                "meta": _build_meta_with_provenance(base_meta),
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

        # Record ingest activity success
        if activity_id:
            _record_ingest_success(
                activity_id=activity_id,
                path=rel_path,
                kind="audio",
                chunks=upserted,
                bytes=len(transcript.encode("utf-8")),
            )

        # Log success
        duration_ms = int((time.time() - start_time) * 1000)
        _log_process_completion(request_id, "audio", docid, True, duration_ms)

        return ProcessTextResponse(
            ok=True,
            document_id=docid,
            chunks=len(chunks),
            embedded=len(vectors),
            upserted=upserted,
            collection=settings.QDRANT_COLLECTION,
        )

    except HTTPException as e:
        # Record skip/error for HTTP exceptions
        if activity_id:
            if "no content" in str(e.detail).lower():
                _record_ingest_skip(activity_id, rel_path, "audio", "empty_file")
            elif "transcribe" in str(e.detail).lower():
                _record_ingest_error(activity_id, rel_path, "audio", "parse_failed")
            else:
                _record_ingest_error(activity_id, rel_path, "audio", "worker_error")
        raise
    except Exception as e:
        # Log failure
        duration_ms = int((time.time() - start_time) * 1000)
        _log_process_completion(request_id, "audio", docid, False, duration_ms, str(e))
        # Record ingest activity error
        if activity_id:
            _record_ingest_error(activity_id, rel_path, "audio", "worker_error")
        raise
