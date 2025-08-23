from fastapi import APIRouter, Query
from typing import Literal
from qdrant_client import QdrantClient
from worker.app.config import settings
from worker.app.services.embed_ollama import embed_texts

router = APIRouter()

def _search(collection: str, vec, k: int):
    q = QdrantClient(url=settings.QDRANT_URL)
    hits = q.search(collection_name=collection, query_vector=vec, limit=k)
    out = []
    for h in hits:
        p = h.payload or {}
        out.append({"id": str(h.id), "score": float(h.score), **p})
    return out

@router.get("/search")
def search(q: str = Query(...), kind: Literal["text", "images"] = "text", k: int = 10):
    vec = embed_texts([q])[0]
    col = settings.QDRANT_COLLECTION if kind == "text" else getattr(settings, "QDRANT_COLLECTION_IMAGES", "jsonify2ai_images_768")
    return {"ok": True, "kind": kind, "q": q, "results": _search(col, vec, k)}
