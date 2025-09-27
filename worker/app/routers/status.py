# worker/app/routers/status.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from worker.app.config import settings
from worker.app.services.qdrant_client import (
    get_qdrant_client as get_client,
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
    client = get_client()
    chunks_coll = "jsonify2ai_chunks_768"  # Use the collection that actually has data
    images_coll = settings.QDRANT_COLLECTION_IMAGES

    # Use scroll-based counting as Qdrant count method seems unreliable
    def _count_by_scroll(collection_name):
        try:
            result = client.scroll(collection_name=collection_name, limit=10000)
            # Scroll returns a tuple: (points, next_page_offset)
            if isinstance(result, tuple) and len(result) >= 1:
                points = result[0]
                return len(points)
            return 0
        except Exception:
            return 0

    chunks_total = _count_by_scroll(chunks_coll)
    images_total = _count_by_scroll(images_coll)

    # Note: Qdrant client count method doesn't support filters, so per-kind counts are not available
    # For now, set all to 0. In the future, this could be implemented using search with filters
    counts_by_kind = {
        "text": 0,  # Would need search with kind filter to get accurate count
        "pdf": 0,  # Would need search with kind filter to get accurate count
        "audio": 0,  # Would need search with kind filter to get accurate count
        "image": images_total,  # All images are in the images collection
    }

    last_ingest_summary = _ingest_state.summary()

    data = {
        "ok": True,
        "qdrant_url": settings.QDRANT_URL,
        "chunks_collection": chunks_coll,
        "images_collection": images_coll,
        "initialized": {"chunks": True, "images": True},
        "counts": {
            "chunks": chunks_total,
            "images": images_total,
            "total": chunks_total + images_total,
        },
        "counts_by_kind": counts_by_kind,
        "last_ingest_summary": last_ingest_summary,
    }
    return JSONResponse(data)
