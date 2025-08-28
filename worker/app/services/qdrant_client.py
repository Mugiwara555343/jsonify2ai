from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
from typing import List, Dict, Any
from worker.app.config import settings


def get_qdrant_client() -> QdrantClient:
    """Get Qdrant client instance."""
    return QdrantClient(url=settings.QDRANT_URL)


def ensure_collection(client: QdrantClient, name: str, dim: int) -> None:
    """
    Ensure Qdrant collection exists with correct dimensions.

    Args:
        client: Qdrant client instance
        name: Collection name
        dim: Expected vector dimension

    Raises:
        ValueError: If collection exists with wrong dimensions
    """
    collections = client.get_collections()
    collection_names = [c.name for c in collections.collections]

    if name in collection_names:
        # Verify existing collection dimensions
        collection_info = client.get_collection(name)
        current_dim = collection_info.config.params.vectors.size

        if current_dim != dim:
            raise ValueError(
                f"Collection '{name}' exists with dimension {current_dim}, "
                f"but model expects {dim}. Please use a different collection name "
                f"or change the embedding model."
            )
    else:
        # Create new collection
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )


def upsert_points(
    client: QdrantClient,
    name: str,
    embeddings: List[List[float]],
    payloads: List[Dict[str, Any]],
    ids: List[str],
) -> None:
    """
    Upsert points to Qdrant collection.

    Args:
        client: Qdrant client instance
        name: Collection name
        embeddings: List of embedding vectors
        payloads: List of payload dictionaries
        ids: List of point IDs
    """
    points = []
    for i, (embedding, payload, point_id) in enumerate(zip(embeddings, payloads, ids)):
        points.append({"id": point_id, "vector": embedding, "payload": payload})

    client.upsert(
        collection_name=name,
        points=points,
        parallel=1,  # MVP: sequential processing
    )


def upsert_points_min(
    collection_name: str,
    items: List[tuple],
) -> int:
    """
    Minimal upsert function that takes (id, vector, payload) tuples.

    Args:
        collection_name: Collection name
        items: List of (id, vector, payload) tuples

    Returns:
        Number of points upserted
    """
    client = get_qdrant_client()
    points = []
    for point_id, vector, payload in items:
        points.append({"id": point_id, "vector": vector, "payload": payload})

    client.upsert(
        collection_name=collection_name,
        points=points,
        parallel=1,
    )
    return len(points)
