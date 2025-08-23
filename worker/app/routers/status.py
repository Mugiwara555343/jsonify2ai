from fastapi import APIRouter
from qdrant_client import QdrantClient
from worker.app.config import settings

router = APIRouter()

def _count(client: QdrantClient, collection: str) -> int:
    try:
        r = client.count(collection, exact=True)
        return int(getattr(r, "count", 0) or r["count"])
    except Exception:
        return 0

@router.get("/status")
def status():
    q = QdrantClient(url=settings.QDRANT_URL)
    return {
        "ok": True,
        "qdrant_url": settings.QDRANT_URL,
        "chunks_collection": settings.QDRANT_COLLECTION,
        "images_collection": getattr(settings, "QDRANT_COLLECTION_IMAGES", "jsonify2ai_images_768"),
        "counts": {
            "chunks": _count(q, settings.QDRANT_COLLECTION),
            "images": _count(q, getattr(settings, "QDRANT_COLLECTION_IMAGES", "jsonify2ai_images_768")),
        },
    }
