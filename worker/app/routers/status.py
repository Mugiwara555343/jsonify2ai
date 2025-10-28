# worker/app/routers/status.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from worker.app.config import settings
from worker.app.services.qdrant_client import (
    count_total,
    count_match,
)
from worker.app.telemetry import telemetry

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
    chunks_coll = settings.QDRANT_COLLECTION
    images_coll = settings.QDRANT_COLLECTION_IMAGES

    chunks_total = count_total(chunks_coll)
    try:
        images_total = count_total(images_coll)
    except Exception as e:
        images_total = 0
        telemetry.set_error(f"images_count: {e}")

    counts_by_kind = {
        "text": count_match(chunks_coll, "kind", "text"),
        "pdf": count_match(chunks_coll, "kind", "pdf"),
        "audio": count_match(chunks_coll, "kind", "audio"),
        "image": count_match(images_coll, "kind", "image"),
    }

    last_ingest_summary = _ingest_state.summary()

    # Get telemetry stats
    telemetry_stats = telemetry.get_stats()

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
        # Add telemetry fields
        "uptime_s": telemetry_stats["uptime_s"],
        "ingest_total": telemetry_stats["ingest_total"],
        "ingest_failed": telemetry_stats["ingest_failed"],
        "watcher_triggers_total": telemetry_stats["watcher_triggers_total"],
        "export_total": telemetry_stats["export_total"],
        "ask_synth_total": telemetry_stats["ask_synth_total"],
        "last_error": telemetry_stats["last_error"],
    }
    return JSONResponse(data)
