from fastapi import APIRouter, Query
from typing import Literal, Optional, List
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from worker.app.config import settings
from worker.app.services.embed_ollama import embed_texts

router = APIRouter()


def _build_filter(
    path: Optional[str], document_id: Optional[str], kind: Optional[str] = None
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
    return Filter(must=conds) if conds else None


def _search(
    collection: str,
    vec,
    k: int,
    path: Optional[str] = None,
    document_id: Optional[str] = None,
    kind: Optional[str] = None,
):
    q = QdrantClient(url=settings.QDRANT_URL)
    qf = _build_filter(path, document_id, kind)

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
    kind: Literal["text", "pdf", "image", "audio"] = "text",
    k: int = 10,
    path: Optional[str] = Query(None),
    document_id: Optional[str] = Query(None),
):
    try:
        vec = embed_texts([q])[0]
        col = (
            settings.QDRANT_COLLECTION
            if kind in ["text", "pdf", "audio"]
            else getattr(settings, "QDRANT_COLLECTION_IMAGES", "jsonify2ai_images_768")
        )
        return {
            "ok": True,
            "kind": kind,
            "q": q,
            "results": _search(
                col, vec, k, path=path, document_id=document_id, kind=kind
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
    try:
        vec = embed_texts([q])[0]
        col = (
            settings.QDRANT_COLLECTION
            if kind in ["text", "pdf", "audio"]
            else getattr(settings, "QDRANT_COLLECTION_IMAGES", "jsonify2ai_images_768")
        )
        return {
            "ok": True,
            "kind": kind,
            "q": q,
            "results": _search(
                col, vec, k, path=path, document_id=document_id, kind=kind
            ),
        }
    except Exception as e:
        msg = str(e).lower()
        if "not found" in msg or ("collection" in msg and "exist" in msg):
            return {"ok": True, "kind": kind, "q": q, "results": []}
        raise
