from __future__ import annotations
import asyncio
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm
from worker.app.config import settings as C

# single process → reuse client
_client: QdrantClient | None = None


def _client_once() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=C.QDRANT_URL, timeout=10.0)
    return _client


CHUNKS = C.QDRANT_COLLECTION
IMAGES = f"{C.QDRANT_COLLECTION}_images_768"


async def ensure_collections():
    # tiny async shim so we can call from FastAPI startup
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _ensure_sync)


def _ensure_sync():
    cli = _client_once()
    # chunks
    if not _exists(cli, CHUNKS):
        cli.recreate_collection(
            collection_name=CHUNKS,
            vectors_config=qm.VectorParams(
                size=C.EMBEDDING_DIM, distance=qm.Distance.COSINE
            ),
        )
    # images (fixed 768 for now)
    if not _exists(cli, IMAGES):
        cli.recreate_collection(
            collection_name=IMAGES,
            vectors_config=qm.VectorParams(size=768, distance=qm.Distance.COSINE),
        )


def _exists(cli: QdrantClient, name: str) -> bool:
    try:
        _ = cli.get_collection(name)
        return True
    except Exception:
        return False


async def collections_status() -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _status_sync)


def _status_sync() -> dict:
    cli = _client_once()

    def safe(name: str) -> bool:
        try:
            info = cli.get_collection(name)
            # consider initialized if collection exists (points may be 0)
            return info is not None
        except Exception:
            return False

    return {"chunks": safe(CHUNKS), "images": safe(IMAGES)}
