# worker/app/routers/status.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import APIRouter

from worker.app.config import settings
from worker.app.services.qdrant_client import (
    get_qdrant_client,
    count as q_count,
    build_filter,
)

# Keep router path exactly as-is for compatibility
router = APIRouter()


# --- Minimal in-memory ingest summary (to be updated by process.py) ----------
class _IngestState:
    def __init__(self) -> None:
        self._last: Optional[Dict] = None

    def record(
        self,
        *,
        document_id: str,
        chunks_upserted: int,
        files_seen: int = 1,
        skips_by_reason: Optional[Dict[str, int]] = None,
    ) -> None:
        self._last = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "document_id": document_id,
            "files_seen": files_seen,
            "chunks_upserted": chunks_upserted,
            "skips_by_reason": skips_by_reason or {},
        }

    def summary(self) -> Optional[Dict]:
        return self._last


_ingest_state = _IngestState()


# public helper for process.py to import and call once per ingest
def record_ingest_summary(
    *,
    document_id: str,
    chunks_upserted: int,
    files_seen: int = 1,
    skips_by_reason: Optional[Dict[str, int]] = None,
) -> None:
    _ingest_state.record(
        document_id=document_id,
        chunks_upserted=chunks_upserted,
        files_seen=files_seen,
        skips_by_reason=skips_by_reason,
    )


@router.get("/status")
async def status():
    """
    Returns service health + collection counts.
    Adds:
      - counts_by_kind: {'text','pdf','audio','image'}
      - last_ingest_summary: last ingest event snapshot (if any)
    """
    qc = get_qdrant_client()

    # Total counts (compatible with your previous response)
    chunks_total = q_count(collection_name=settings.QDRANT_COLLECTION, client=qc)
    images_total = q_count(
        collection_name=getattr(
            settings, "QDRANT_COLLECTION_IMAGES", "jsonify2ai_images_768"
        ),
        client=qc,
    )

    # Per-kind counts for the chunks collection
    kinds = ["text", "pdf", "audio", "image"]
    counts_by_kind = {
        k: q_count(
            collection_name=settings.QDRANT_COLLECTION,
            query_filter=build_filter(kind=k),
            client=qc,
        )
        for k in kinds
    }

    # Keep your existing initialized field if available; fall back to booleans
    initialized = {
        "chunks": chunks_total > 0,
        "images": images_total > 0,
    }
    try:
        # If you have a custom initializer, prefer its output
        from worker.app.qdrant_init import collections_status  # type: ignore

        initialized = await collections_status()  # {"chunks": bool, "images": bool}
    except Exception:
        pass

    return {
        "ok": True,
        "qdrant_url": settings.QDRANT_URL,
        "chunks_collection": settings.QDRANT_COLLECTION,
        "images_collection": getattr(
            settings, "QDRANT_COLLECTION_IMAGES", "jsonify2ai_images_768"
        ),
        "initialized": initialized,
        "counts": {
            "chunks": chunks_total,
            "images": images_total,
        },
        "counts_by_kind": counts_by_kind,
        "last_ingest_summary": _ingest_state.summary(),
    }
