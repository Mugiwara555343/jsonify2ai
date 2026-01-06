from fastapi import APIRouter, Query
from typing import Literal, Optional, List
from datetime import datetime
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, Range
from worker.app.config import settings
from worker.app.services.embed_ollama import embed_texts

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
    path: Optional[str] = None,
    document_id: Optional[str] = None,
    kind: Optional[str] = None,
    ingested_after: Optional[str] = None,
    ingested_before: Optional[str] = None,
):
    q = QdrantClient(url=settings.QDRANT_URL)
    qf = _build_filter(path, document_id, kind, ingested_after, ingested_before)

    # NOTE: older/newer qdrant-client versions need `query_filter`, not `filter`
    hits = q.search(
        collection_name=collection,
        query_vector=vec,
        limit=k,
        with_payload=True,
        query_filter=qf,  # ← fixed: was `filter=...` causing 500s
    )

    out = []
    for h in hits:
        p = h.payload or {}
        out.append({"id": str(h.id), "score": float(h.score), **p})
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
    q = body.get("q")
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
