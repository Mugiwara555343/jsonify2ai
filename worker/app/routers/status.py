# worker/app/routers/status.py
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Dict, Optional

import requests
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

# Module-level memoization for Ollama reachability (15s cache)
_ollama_cache: tuple = (0.0, False)


def _ollama_reachable() -> bool:
    """
    Check if Ollama is reachable with 2s timeout, memoized for 15s.
    """
    global _ollama_cache
    now = time.time()
    last_ts, last_bool = _ollama_cache

    # Return cached value if within 15s
    if now - last_ts < 15.0:
        return last_bool

    # Check reachability
    try:
        resp = requests.get(f"{settings.OLLAMA_HOST}/api/tags", timeout=2.0)
        reachable = resp.status_code == 200
    except Exception:
        reachable = False

    # Update cache
    _ollama_cache = (now, reachable)
    return reachable


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

    # Build LLM status
    llm = {
        "provider": settings.LLM_PROVIDER or "none",
        "model": settings.OLLAMA_MODEL if settings.LLM_PROVIDER == "ollama" else "",
        "reachable": (
            _ollama_reachable() if settings.LLM_PROVIDER == "ollama" else False
        ),
        "synth_total": telemetry_stats["ask_synth_total"],
    }

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
        # LLM status
        "llm": llm,
    }
    return JSONResponse(data)
