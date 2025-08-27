# worker/app/routers/qdrant_utils.py
from typing import Iterable, Tuple, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
import os


def get_client() -> QdrantClient:
    url = os.getenv("QDRANT_URL", "http://host.docker.internal:6333")
    return QdrantClient(url=url)


def ensure_collection(client: QdrantClient, name: str, dim: int):
    cols = [c.name for c in client.get_collections().collections]
    if name in cols:
        return
    client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
    )


def upsert_points(
    client: QdrantClient, name: str, items: Iterable[Tuple[str, list, Dict[str, Any]]]
) -> int:
    points = [PointStruct(id=i, vector=v, payload=p) for (i, v, p) in items]
    client.upsert(collection_name=name, points=points)
    return len(points)
