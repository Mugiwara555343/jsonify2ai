from fastapi import APIRouter, Query
from typing import Literal, Optional, List
from datetime import datetime
from qdrant_client.models import Filter, FieldCondition, MatchValue, Range
from worker.app.config import settings
from worker.app.services.embed_ollama import embed_texts
from worker.app.services.qdrant_client import search as q_search

router = APIRouter()


def _parse_iso_to_timestamp(iso_str: str) -> Optional[int]:
    """Parse ISO-8601 string to unix timestamp (seconds). Returns None if invalid."""
    try:
        # Handle both 'Z' and '+00:00' formats
        iso_str = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso_str)
        return int(dt.timestamp())
    except (ValueError, AttributeError):
        return None


def _normalize_source(hit: dict) -> dict:
    """Convert raw Qdrant hit to standardized Source object."""
    # Handle both direct fields and nested payload
    # If payload is nested, use it; otherwise the hit itself IS the payload (already spread)
    if "payload" in hit and isinstance(hit.get("payload"), dict):
        payload = hit["payload"]
    else:
        # Payload was already spread into hit at top level
        payload = hit

    # Extract text excerpt (trim to 400-800 chars by default, use 600 as middle ground)
    text = payload.get("content") or payload.get("text") or payload.get("caption") or ""
    if len(text) > 600:
        text = text[:600] + "…"

    # Build meta object
    meta = payload.get("meta", {}) if isinstance(payload.get("meta"), dict) else {}
    if not isinstance(meta, dict):
        meta = {}

    # Preserve existing meta fields
    source_meta = {}
    for key in [
        "ingested_at",
        "ingested_at_ts",
        "source_system",
        "title",
        "logical_path",
        "conversation_id",
        "source_file",
    ]:
        if key in meta:
            source_meta[key] = meta[key]

    # Allow passthrough of additional meta keys
    for k, v in meta.items():
        if k not in source_meta:
            source_meta[k] = v

    return {
        "id": str(hit.get("id", "")),
        "document_id": hit.get("document_id") or payload.get("document_id", ""),
        "path": hit.get("path") or payload.get("path"),
        "kind": hit.get("kind") or payload.get("kind"),
        "idx": hit.get("idx") or payload.get("idx") or hit.get("chunk_index"),
        "score": hit.get("score"),
        "text": text,
        "meta": source_meta if source_meta else None,
    }


def _build_filter(
    path: Optional[str],
    document_id: Optional[str],
    kind: Optional[str] = None,
    ingested_after: Optional[str] = None,
    ingested_before: Optional[str] = None,
) -> Optional[Filter]:
    conds: List[FieldCondition] = []
    if path:
        conds.append(FieldCondition(key="path", match=MatchValue(value=path)))
    if document_id:
        conds.append(
            FieldCondition(key="document_id", match=MatchValue(value=document_id))
        )
    if kind:
        conds.append(FieldCondition(key="kind", match=MatchValue(value=kind)))

    # Time range filters on meta.ingested_at_ts
    if ingested_after:
        ts_after = _parse_iso_to_timestamp(ingested_after)
        if ts_after is not None:
            conds.append(
                FieldCondition(key="meta.ingested_at_ts", range=Range(gte=ts_after))
            )
    if ingested_before:
        ts_before = _parse_iso_to_timestamp(ingested_before)
        if ts_before is not None:
            conds.append(
                FieldCondition(key="meta.ingested_at_ts", range=Range(lt=ts_before))
            )

    return Filter(must=conds) if conds else None


def _search(
    collection: str,
    vec,
    k: int,
    query_text: Optional[str] = None,
    path: Optional[str] = None,
    document_id: Optional[str] = None,
    kind: Optional[str] = None,
    ingested_after: Optional[str] = None,
    ingested_before: Optional[str] = None,
):
    # Debug: log received parameters
    print(f"DEBUG _search: query_text={query_text!r}, collection={collection}, k={k}")

    qf = _build_filter(path, document_id, kind, ingested_after, ingested_before)

    # Use shared search wrapper which supports both query_vector and query_text
    hits = q_search(
        query_vector=vec,
        query_text=query_text,
        collection_name=collection,
        k=k,
        query_filter=qf,
        with_payload=True,
    )

    out = []
    for h in hits:
        p = h.payload or {}
        raw_hit = {"id": str(h.id), "score": float(h.score), **p}
        # Normalize to standardized Source shape
        normalized = _normalize_source(raw_hit)
        out.append(normalized)
    return out


@router.get("/search")
def search(
    q: str = Query(...),
    kind: Literal["text", "pdf", "image", "audio", "chat"] = "text",
    k: int = 10,
    path: Optional[str] = Query(None),
    document_id: Optional[str] = Query(None),
    ingested_after: Optional[str] = Query(None),
    ingested_before: Optional[str] = Query(None),
):
    try:
        vec = embed_texts([q])[0]
        col = (
            settings.QDRANT_COLLECTION
            if kind in ["text", "pdf", "audio", "chat"]
            else getattr(settings, "QDRANT_COLLECTION_IMAGES", "jsonify2ai_images_768")
        )
        return {
            "ok": True,
            "kind": kind,
            "q": q,
            "results": _search(
                col,
                vec,
                k,
                query_text=q,
                path=path,
                document_id=document_id,
                kind=kind,
                ingested_after=ingested_after,
                ingested_before=ingested_before,
            ),
        }
    except Exception as e:
        msg = str(e).lower()
        if "not found" in msg or ("collection" in msg and "exist" in msg):
            return {"ok": True, "kind": kind, "q": q, "results": []}
        raise


@router.post("/search")
def search_post(body: dict):
    q = body.get("query_text") or body.get("query") or body.get("q")
    kind = body.get("kind", "text")
    k = body.get("k") or body.get("top_k", 10)
    path = body.get("path")
    document_id = body.get("document_id")
    ingested_after = body.get("ingested_after")
    ingested_before = body.get("ingested_before")
    try:
        vec = embed_texts([q])[0]
        col = (
            settings.QDRANT_COLLECTION
            if kind in ["text", "pdf", "audio", "chat"]
            else getattr(settings, "QDRANT_COLLECTION_IMAGES", "jsonify2ai_images_768")
        )
        return {
            "ok": True,
            "kind": kind,
            "q": q,
            "results": _search(
                col,
                vec,
                k,
                query_text=q,
                path=path,
                document_id=document_id,
                kind=kind,
                ingested_after=ingested_after,
                ingested_before=ingested_before,
            ),
        }
    except Exception as e:
        msg = str(e).lower()
        if "not found" in msg or ("collection" in msg and "exist" in msg):
            return {"ok": True, "kind": kind, "q": q, "results": []}
        raise
