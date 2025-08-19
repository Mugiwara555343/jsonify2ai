# worker/app/services/qdrant_minimal.py
from __future__ import annotations
from typing import Iterable, List, Dict, Any
import os

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

def get_client() -> QdrantClient:
    url = os.getenv("QDRANT_URL", "http://host.docker.internal:6333")
    return QdrantClient(url=url)

def ensure_collection_minimal(
    client: QdrantClient,
    name: str,
    dim: int,
    distance: Distance = Distance.COSINE,
) -> None:
    """Create the collection if missing (idempotent). Never recreate existing."""
    existing = {c.name for c in client.get_collections().collections}
    if name in existing:
        return
    client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=dim, distance=distance),
    )

def upsert_points_minimal(
    client: QdrantClient,
    name: str,
    points: Iterable[PointStruct],
) -> int:
    """Upsert without extra kwargs that trigger strict mode assertions."""
    resp = client.upsert(collection_name=name, points=list(points))
    # Best‑effort count
    try:
        return len(points)  # type: ignore[arg-type]
    except Exception:
        return 0
