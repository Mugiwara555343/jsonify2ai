# worker/app/services/qdrant_client.py
"""
Thin, resilient Qdrant wrapper used by the worker.

Goals:
- Single place to create/repair the collection (dim, distance).
- Small, predictable API for upserts, deletes and search.
- Safe defaults that never crash the ingest loop.
- Keep payload schema agnostic: we only assume `document_id`/`path`/`kind` exist
  when you want to filter.

This module intentionally avoids advanced features so it works across
qdrant-client 1.6–1.9 without surprises.
"""

from __future__ import annotations


import requests
import sys
from typing import Iterable, List, Dict, Any, Tuple, Optional
from requests.exceptions import HTTPError

from qdrant_client import QdrantClient, models
from qdrant_client.models import VectorParams
from worker.app.config import settings


# -------------------------- Client helpers --------------------------


def get_qdrant_client() -> QdrantClient:
    """Return a Qdrant client configured from settings."""
    return QdrantClient(url=settings.QDRANT_URL, timeout=10.0)


def _collection_exists(client: QdrantClient, name: str) -> bool:
    try:
        cols = client.get_collections()
        items = getattr(cols, "collections", None) or []
        return any(getattr(c, "name", "") == name for c in items)
    except Exception:
        return False


def _current_vector_size(client: QdrantClient, name: str) -> Optional[int]:
    """Best-effort: read the configured vector dimension for a collection.

    Returns None if it cannot be determined.
    """
    try:
        info = client.get_collection(name)
    except Exception:
        return None

    cfg = getattr(info, "config", None)
    params = getattr(cfg, "params", None)
    vectors = getattr(params, "vectors", None)
    # Newer qdrant may return a typed object with .size, or a dict of named vectors
    if hasattr(vectors, "size"):
        try:
            return int(vectors.size)  # type: ignore[attr-defined]
        except Exception:
            return None
    if isinstance(vectors, dict):
        try:
            first = next(iter(vectors.values()))
            return int(getattr(first, "size"))
        except Exception:
            return None
    return None


def ensure_collection(
    client: Optional[QdrantClient] = None,
    name: Optional[str] = None,
    dim: Optional[int] = None,
    *,
    distance: str = "Cosine",
    recreate_bad: Optional[bool] = None,
    create_payload_indexes: bool = True,
) -> Dict[str, Any]:
    """Create the collection if missing; optionally repair dim mismatch.

    - `name`: defaults to `settings.QDRANT_COLLECTION`
    - `dim`:  defaults to `settings.EMBEDDING_DIM`
    - `recreate_bad`: if True (or env QDRANT_RECREATE_BAD=1), will recreate the
      collection when a dimension mismatch is detected.
    - Adds payload indexes for {document_id, kind, path, meta.ingested_at_ts} to speed filters.

    Returns:
        Dict with the final collection configuration.
    """
    qc = client or get_qdrant_client()
    name = name or settings.QDRANT_COLLECTION
    dim = dim or settings.EMBEDDING_DIM
    recreate_bad = (
        (settings.QDRANT_RECREATE_BAD == 1) if recreate_bad is None else recreate_bad
    )

    # Use the stable minimal implementation with signature adaptation
    config = _ensure_collection_with_signature_adapt(
        qc, name=name, dim=dim, distance=distance, recreate_bad=recreate_bad
    )

    # Create payload indexes after ensuring the collection
    if create_payload_indexes:
        _ensure_payload_indexes(qc, name)

    return config


def _ensure_collection_with_signature_adapt(
    client: QdrantClient,
    *,
    name: str,
    dim: int,
    distance: str = "Cosine",
    recreate_bad: bool = False,
) -> Dict[str, Any]:
    """
    Call ensure_collection_minimal with signature adaptation.

    Handles different signatures and returns the final collection config.

    Args:
        client: Qdrant client
        name: Collection name
        dim: Vector dimension
        distance: Distance metric (default: Cosine)
        recreate_bad: Whether to recreate collections with wrong schema

    Returns:
        Dict containing the collection config
    """

    # Try to get the collection config first to check if it exists
    try:
        info = client.get_collection(name)
        cfg = getattr(info, "config", {}) or {}
        params = getattr(cfg, "params", {}) or {}
        vectors = getattr(params, "vectors", {}) or {}

        # Extract the vector dimension and distance
        vector_size = None
        vector_distance = None

        # Handle both object and dict forms
        if hasattr(vectors, "size"):
            vector_size = int(vectors.size)
            vector_distance = getattr(vectors, "distance", "Cosine")
        elif isinstance(vectors, dict):
            # Check if this is an unnamed vector (has 'size' directly)
            if "size" in vectors:
                vector_size = int(vectors["size"])
                vector_distance = vectors.get("distance", "Cosine")
            else:
                # Could be named vectors, which we don't want
                if vectors:
                    first_key = next(iter(vectors.keys()), None)
                    if first_key:
                        raise RuntimeError(
                            f"Collection '{name}' uses named vectors ('{first_key}'), but the project requires unnamed vectors"
                        )

        # If we have valid info and it matches our requirements, return it
        if vector_size == dim and vector_distance == distance:
            return {"params": {"vectors": {"size": dim, "distance": distance}}}

        # Schema mismatch detected
        mismatch_msg = (
            f"Collection '{name}' schema mismatch: found size={vector_size}, "
            f"distance={vector_distance}, expected size={dim}, distance={distance}"
        )

        if recreate_bad:
            # Will be recreated below
            client.delete_collection(collection_name=name)
        else:
            raise RuntimeError(mismatch_msg)

    except Exception as e:
        # If the collection doesn't exist or we're recreating, we'll create it below
        if "does not exist" not in str(e) and "schema mismatch" not in str(e):
            # Unexpected error
            raise RuntimeError(f"Error accessing collection '{name}': {e}")

    # Create or recreate collection with unnamed vectors
    client.recreate_collection(
        collection_name=name,
        vectors_config=VectorParams(size=dim, distance=distance),
    )

    # Return the final configuration
    try:
        info = client.get_collection(name)
        return getattr(info, "config", {}) or {
            "params": {"vectors": {"size": dim, "distance": distance}}
        }
    except Exception:
        # If we can't get the config, return a synthetic one
        return {"params": {"vectors": {"size": dim, "distance": distance}}}


def _ensure_payload_indexes(client: QdrantClient, name: str) -> None:
    """Best-effort creation of helpful payload indexes; ignore failures."""
    try:
        client.create_payload_index(
            collection_name=name,
            field_name="document_id",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
    except Exception:
        pass
    try:
        client.create_payload_index(
            collection_name=name,
            field_name="kind",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
    except Exception:
        pass
    try:
        client.create_payload_index(
            collection_name=name,
            field_name="path",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
    except Exception:
        pass
    try:
        client.create_payload_index(
            collection_name=name,
            field_name="meta.ingested_at_ts",
            field_schema=models.PayloadSchemaType.INTEGER,
        )
    except Exception:
        pass


# -------------------------- Upserts & deletes --------------------------


def upsert_points(
    items: List[Tuple[str, List[float], Dict[str, Any]]],
    *,
    collection_name: Optional[str] = None,
    client: Optional[QdrantClient] = None,
    batch_size: int = 128,
    ensure: bool = True,
) -> int:
    """Upsert (id, vector, payload) tuples into Qdrant in small batches.

    - Returns the number of points successfully submitted to Qdrant.
    - If `ensure`, the collection will be created/repaired before the first upsert.
    - Validates vector dimension against settings.EMBEDDING_DIM and skips invalid vectors.
    - Never raises for empty input.
    """
    if not items:
        return 0

    qc = client or get_qdrant_client()
    col = collection_name or settings.QDRANT_COLLECTION
    expected_dim = getattr(settings, "EMBEDDING_DIM", 768)

    if ensure:
        # Ensure collection exists with correct schema before upserting
        try:
            ensure_collection(qc, col, expected_dim)
        except Exception as e:
            print(f"[error] Collection ensure failed: {e}", file=sys.stderr)
            return 0

    total = 0
    points_skipped_embed_error = 0
    for batch in _batched(items, batch_size):
        valid_points = []
        for pid, vec, payload in batch:
            # Validate vector format and dimension
            if not isinstance(vec, list):
                points_skipped_embed_error += 1
                print(
                    f"[warn] Skipping upsert id={pid} due to embedding type: got {type(vec).__name__}, expected list"
                )
                continue

            if len(vec) != expected_dim:
                points_skipped_embed_error += 1
                print(
                    f"[warn] Skipping upsert id={pid} due to wrong embedding dimension: got {len(vec)}, expected {expected_dim}"
                )
                continue

            # Create point with unnamed vector format
            valid_points.append(models.PointStruct(id=pid, vector=vec, payload=payload))

        if not valid_points:
            continue

        try:
            qc.upsert(collection_name=col, wait=True, points=valid_points)
            total += len(valid_points)
        except Exception as e:
            # Provide concise error information for debugging
            try:
                from qdrant_client.http.exceptions import UnexpectedResponse

                if isinstance(e, UnexpectedResponse):
                    # Concise error summary focusing on what's needed to diagnose common issues
                    point_count = len(valid_points)
                    first_point_info = {}

                    if valid_points:
                        first_point = valid_points[0]
                        vector_len = (
                            len(first_point.vector)
                            if hasattr(first_point, "vector")
                            else "unknown"
                        )
                        first_point_info = {
                            "id_type": type(first_point.id).__name__,
                            "vector_len": vector_len,
                            "payload_keys": (
                                list(first_point.payload.keys())
                                if hasattr(first_point, "payload")
                                else []
                            ),
                        }

                    print(
                        f"[qdrant error] status={e.status_code} body={e.body} points={point_count} first_point={first_point_info}",
                        file=sys.stderr,
                    )
                else:
                    print(f"[error] upsert failed: {e}", file=sys.stderr)
            except Exception:
                print(f"[error] upsert failed: {e}", file=sys.stderr)

    if points_skipped_embed_error > 0:
        print(
            f"[warn] Total points skipped due to embedding errors: {points_skipped_embed_error}"
        )

    return total


def delete_by_document_id(
    document_id: str,
    *,
    collection_name: Optional[str] = None,
    client: Optional[QdrantClient] = None,
) -> int:
    """Delete all points with payload.document_id == given value. Returns deleted count (best-effort)."""
    qc = client or get_qdrant_client()
    col = collection_name or settings.QDRANT_COLLECTION
    flt = models.Filter(
        must=[
            models.FieldCondition(
                key="document_id", match=models.MatchValue(value=document_id)
            )
        ]
    )
    try:
        res = qc.delete(
            collection_name=col, points_selector=models.FilterSelector(filter=flt)
        )
        # qdrant doesn't always return a count; try to read it, else -1 (unknown)
        return int(getattr(res, "status", 0) == "acknowledged") or -1
    except Exception:
        return 0


# ------------------------------ Search ---------------------------------


def build_filter(
    *,
    document_id: Optional[str] = None,
    kind: Optional[str] = None,
    path: Optional[str] = None,
    extra_must: Optional[List[models.Condition]] = None,
) -> Optional[models.Filter]:
    """Convenience helper to compose common filters."""
    must: List[models.Condition] = []
    if document_id:
        must.append(
            models.FieldCondition(
                key="document_id", match=models.MatchValue(value=document_id)
            )
        )
    if kind:
        must.append(
            models.FieldCondition(key="kind", match=models.MatchValue(value=kind))
        )
    if path:
        must.append(
            models.FieldCondition(key="path", match=models.MatchValue(value=path))
        )

    if extra_must:
        must.extend(extra_must)

    return models.Filter(must=must) if must else None


def search(
    query_vector: List[float],
    *,
    k: int = 5,
    collection_name: str,
    query_filter: Optional[models.Filter] = None,
    client: Optional[QdrantClient] = None,
    with_payload: bool = True,
    debug: bool = False,
) -> List[models.ScoredPoint]:
    """Search similar vectors in the explicit collection. Checks schema and prints debug diagnostics if requested."""
    qc = client or get_qdrant_client()
    if not collection_name:
        raise RuntimeError(
            "No Qdrant collection specified. Use --collection or set QDRANT_COLLECTION."
        )

    expected_dim = getattr(settings, "EMBEDDING_DIM", 768)

    # Validate query vector dimension
    if not isinstance(query_vector, list) or len(query_vector) != expected_dim:
        raise RuntimeError(
            f"Query vector dimension mismatch: got {len(query_vector) if isinstance(query_vector, list) else type(query_vector).__name__}, expected {expected_dim}"
        )

    # Check collection exists and schema matches
    try:
        info = qc.get_collection(collection_name)
        cfg = getattr(info, "config", None)
        params = getattr(cfg, "params", None)
        vectors = getattr(params, "vectors", None)

        # Extract vector dimension and distance from config
        dim = None
        dist = None

        # Support both unnamed vector format (direct size/distance) and named vectors
        if hasattr(vectors, "size"):
            # Object-based unnamed vector
            dim = int(vectors.size)
            dist = getattr(vectors, "distance", None)
        elif isinstance(vectors, dict):
            # Either unnamed vector as dict or named vectors
            if "size" in vectors:
                # Unnamed vector as dict
                dim = int(vectors["size"])
                dist = vectors.get("distance", "Cosine")
            else:
                # Named vectors - get first one (though this isn't our preferred format)
                try:
                    first_key = next(iter(vectors.keys()))
                    first = vectors[first_key]
                    dim = int(getattr(first, "size", 0))
                    dist = getattr(first, "distance", None)
                except Exception:
                    pass

        # Validate dimension and distance
        if dim != expected_dim:
            raise RuntimeError(
                f"Collection '{collection_name}' dimension mismatch: has {dim}, expected {expected_dim}"
            )

        if dist and str(dist).lower() != "cosine":
            raise RuntimeError(
                f"Collection '{collection_name}' distance mismatch: has {dist}, expected Cosine"
            )
    except Exception as e:
        raise RuntimeError(f"Failed to validate collection '{collection_name}': {e}")

    # Debug diagnostics: raw collection JSON and parsed fields
    if debug:
        import requests
        import json

        url = getattr(settings, "QDRANT_URL", None)
        if url:
            endpoint = url.rstrip("/") + f"/collections/{collection_name}"
            try:
                resp = requests.get(endpoint, timeout=10)
                if resp.status_code == 200:
                    raw_json = resp.json()
                    print(json.dumps(raw_json, ensure_ascii=False))
                    result = raw_json.get("result", {})
                    points_count = result.get("points") or result.get("points_count")
                    indexed_vectors_count = result.get("indexed_vectors_count")
                    # Some Qdrant versions nest indexed_vectors_count
                    if indexed_vectors_count is None and "result" in result:
                        indexed_vectors_count = result["result"].get(
                            "indexed_vectors_count"
                        )
                    print(
                        f"debug: collection={collection_name} raw_points_count={points_count} indexed_vectors_count={indexed_vectors_count}"
                    )
                else:
                    print(
                        f"debug: GET {endpoint} status={resp.status_code} body={resp.text}"
                    )
            except Exception as e:
                print(f"debug: collection={collection_name} diagnostics error: {e}")

    # Perform search
    return qc.search(
        collection_name=collection_name,
        query_vector=query_vector,
        limit=k,
        with_payload=with_payload,
        query_filter=query_filter,
    )


def count(
    *,
    collection_name: Optional[str] = None,
    query_filter: Optional[models.Filter] = None,
    client: Optional[QdrantClient] = None,
    exact: bool = True,
) -> int:
    """Count points, optionally with a filter. Returns 0 on failure."""
    qc = client or get_qdrant_client()
    col = collection_name or settings.QDRANT_COLLECTION
    try:
        # Qdrant client count method doesn't support filters, so we ignore query_filter for now
        res = qc.count(collection_name=col, exact=exact)
        return int(getattr(res, "count", 0))
    except Exception:
        return 0


# ------------------------------ Utils ----------------------------------


def _batched(seq: List[Any], n: int) -> Iterable[List[Any]]:
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


# -------------------------- Count helpers --------------------------


def count_total(collection: str) -> int:
    """
    Count total points in a collection using Qdrant's count endpoint.
    If the collection doesn't exist yet (404), return 0 instead of raising.
    """
    url = f"{settings.QDRANT_URL}/collections/{collection}/points/count"
    try:
        r = requests.post(url, json={"exact": True}, timeout=5)
        r.raise_for_status()
        j = r.json()
        return int(j.get("result", {}).get("count", 0))
    except HTTPError as e:
        if getattr(e, "response", None) is not None and e.response.status_code == 404:
            return 0
        raise


def count_match(collection: str, key: str, value: str) -> int:
    """
    Count points matching a specific key-value filter using Qdrant's count endpoint.
    If the collection doesn't exist yet (404), return 0 instead of raising.
    """
    url = f"{settings.QDRANT_URL}/collections/{collection}/points/count"
    body = {
        "exact": True,
        "filter": {"must": [{"key": key, "match": {"value": value}}]},
    }
    try:
        r = requests.post(url, json=body, timeout=5)
        r.raise_for_status()
        j = r.json()
        return int(j.get("result", {}).get("count", 0))
    except HTTPError as e:
        if getattr(e, "response", None) is not None and e.response.status_code == 404:
            return 0
        raise
