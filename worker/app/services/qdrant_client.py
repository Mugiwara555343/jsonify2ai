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


import sys
from typing import Iterable, List, Dict, Any, Tuple, Optional

from qdrant_client import QdrantClient, models
from qdrant_client.models import Distance, VectorParams
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
    distance: Distance = Distance.COSINE,
    recreate_bad: Optional[bool] = None,
    create_payload_indexes: bool = True,
) -> None:
    """Create the collection if missing; optionally repair dim mismatch.

    - `name`: defaults to `settings.QDRANT_COLLECTION`
    - `dim`:  defaults to `settings.EMBEDDING_DIM`
    - `recreate_bad`: if True (or env QDRANT_RECREATE_BAD=1), will recreate the
      collection when a dimension mismatch is detected.
    - Adds payload indexes for {document_id, kind, path} to speed filters.
    """
    qc = client or get_qdrant_client()
    name = name or settings.QDRANT_COLLECTION
    dim = dim or settings.EMBEDDING_DIM
    recreate_bad = (settings.QDRANT_RECREATE_BAD == 1) if recreate_bad is None else recreate_bad

    if not _collection_exists(qc, name):
        qc.recreate_collection(
            collection_name=name,
            vectors_config=VectorParams(size=dim, distance=distance),
        )
    else:
        size = _current_vector_size(qc, name)
        if size is not None and size != dim:
            if recreate_bad:
                qc.recreate_collection(
                    collection_name=name,
                    vectors_config=VectorParams(size=dim, distance=distance),
                )
            else:
                raise RuntimeError(
                    f"Qdrant collection '{name}' has dim={size}, expected {dim}. "
                    "Set QDRANT_RECREATE_BAD=1 to auto-fix."
                )

    if create_payload_indexes:
        _ensure_payload_indexes(qc, name)


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
    - Never raises for empty input.
    """
    if not items:
        return 0

    qc = client or get_qdrant_client()
    col = collection_name or settings.QDRANT_COLLECTION

    if ensure:
        ensure_collection(qc, col, settings.EMBEDDING_DIM)

    total = 0
    points_skipped_embed_error = 0
    for batch in _batched(items, batch_size):
        valid_points = []
        for pid, vec, payload in batch:
            expected_dim = getattr(settings, "EMBEDDING_DIM", 768)
            if not isinstance(vec, list) or len(vec) != expected_dim:
                points_skipped_embed_error += 1
                print(f"[warn] Skipping upsert id={pid} due to embedding shape: got {type(vec)} len={len(vec) if isinstance(vec, list) else 'N/A'}")
                continue
            valid_points.append(models.PointStruct(id=pid, vector=vec, payload=payload))
            print({"upserted": pid, "vector_len": len(vec)})
        if not valid_points:
            continue
        try:
            qc.upsert(collection_name=col, wait=True, points=valid_points)
            total += len(valid_points)
        except Exception as e:
            # If it's a Qdrant HTTP error, print raw status/body and request payload
            try:
                from qdrant_client.http.exceptions import UnexpectedResponse
                if isinstance(e, UnexpectedResponse):
                    import json
                    print("[error] upsert request payload (truncated):", json.dumps([p.dict() for p in valid_points])[:2000], file=sys.stderr)
                    if valid_points:
                        print("[error] upsert summary: points_count=", len(valid_points), "first_point_keys=", list(valid_points[0].dict().keys()), file=sys.stderr)
                    print(f"[qdrant error] status={e.status_code} body={e.body}", file=sys.stderr)
            except Exception:
                pass
            print(f"[error] upsert failed: {e}", file=sys.stderr)
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
    flt = models.Filter(must=[models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id))])
    try:
        res = qc.delete(collection_name=col, points_selector=models.FilterSelector(filter=flt))
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
        must.append(models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id)))
    if kind:
        must.append(models.FieldCondition(key="kind", match=models.MatchValue(value=kind)))
    if path:
        must.append(models.FieldCondition(key="path", match=models.MatchValue(value=path)))

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
        raise RuntimeError("No Qdrant collection specified. Use --collection or set QDRANT_COLLECTION.")
    # Check collection exists and schema matches
    try:
        info = qc.get_collection(collection_name)
        cfg = getattr(info, "config", None)
        params = getattr(cfg, "params", None)
        vectors = getattr(params, "vectors", None)
        # Support both dict and object
        if hasattr(vectors, "size"):
            dim = int(vectors.size)
            dist = getattr(vectors, "distance", None)
        elif isinstance(vectors, dict):
            first = next(iter(vectors.values()))
            dim = int(getattr(first, "size"))
            dist = getattr(first, "distance", None)
        else:
            dim = None
            dist = None
        expected_dim = getattr(settings, "EMBEDDING_DIM", 768)
        if dim != expected_dim or (dist and str(dist).lower() != "cosine"):
            raise RuntimeError(f"collection {collection_name} schema mismatch: expected dim={expected_dim} distance=Cosine — see README sanity checks")
    except Exception as e:
        raise RuntimeError(f"Failed to fetch collection info for '{collection_name}': {e}")

    # Debug diagnostics: raw collection JSON and parsed fields
    if debug:
        import requests, json
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
                        indexed_vectors_count = result["result"].get("indexed_vectors_count")
                    print(f"debug: collection={collection_name} raw_points_count={points_count} indexed_vectors_count={indexed_vectors_count}")
                else:
                    print(f"debug: GET {endpoint} status={resp.status_code} body={resp.text}")
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
        res = qc.count(collection_name=col, exact=exact, query_filter=query_filter)
        return int(getattr(res, "count", 0))
    except Exception:
        return 0


# ------------------------------ Utils ----------------------------------


def _batched(seq: List[Any], n: int) -> Iterable[List[Any]]:
    for i in range(0, len(seq), n):
        yield seq[i : i + n]
