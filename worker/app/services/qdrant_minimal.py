# worker/app/services/qdrant_minimal.py
from __future__ import annotations

import requests
from typing import Dict, Any

from worker.app.config import settings


def _qdrant_base() -> str:
    # e.g. http://host.docker.internal:6333
    return settings.QDRANT_URL.rstrip("/")


def _as_dict(obj: Any) -> Dict[str, Any]:
    """Convert various object types to a dictionary.

    Handles Pydantic models, objects with model_dump/dict methods, and regular objects.
    """
    if obj is None:
        return {}

    # Handle Pydantic v2 model_dump()
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump()
        except Exception:
            pass

    # Handle Pydantic v1 dict() or other similar methods
    if hasattr(obj, "dict") and callable(obj.dict):
        try:
            return obj.dict()
        except Exception:
            pass

    # Handle standard dict
    if isinstance(obj, dict):
        return obj

    # Last resort: try to convert object attributes to dict
    try:
        return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
    except Exception:
        return {}


def ensure_collection_minimal(
    client, *, name: str, dim: int, distance: str = "Cosine", recreate_bad: bool = False
) -> Dict[str, Any]:
    """
    Idempotently ensure a Qdrant collection exists with the given vector configuration.

    Args:
        client: Qdrant client instance (passed through but not used in HTTP-based impl)
        name: Collection name
        dim: Vector dimension size
        distance: Distance function (default: Cosine)
        recreate_bad: If True, recreate collections with wrong schema

    Returns:
        Dict containing the collection config

    Raises:
        RuntimeError: If collection exists with wrong schema and recreate_bad=False
    """
    url = f"{_qdrant_base()}/collections/{name}"

    try:
        # Check if collection exists
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            data = r.json()

            # Extract vectors config - handle both newer and older API response formats
            config = _as_dict(data.get("config", {}))
            params = _as_dict(config.get("params", {}))
            vectors = _as_dict(params.get("vectors", {}))

            # First try to get the result field if present (newer Qdrant versions)
            if not config and "result" in data:
                result_config = _as_dict(data.get("result", {}).get("config", {}))
                if result_config:
                    config = result_config
                    params = _as_dict(config.get("params", {}))
                    vectors = _as_dict(params.get("vectors", {}))

            # Classify vector configuration
            is_valid = False
            is_named_vectors = False
            vector_size = None
            vector_distance = None

            # Case 1: Valid unnamed vectors {'size': 768, 'distance': 'Cosine', ...}
            if isinstance(vectors, dict) and "size" in vectors:
                vector_size = vectors.get("size")
                vector_distance = vectors.get("distance", "")
                # Case-insensitive distance comparison
                is_valid = (
                    vector_size == dim
                    and str(vector_distance).lower() == distance.lower()
                )

            # Case 2: Empty vectors config
            elif not vectors:
                is_valid = False

            # Case 3: Named vectors {'text': {'size': 768, ...}}
            elif isinstance(vectors, dict):
                is_named_vectors = any(
                    isinstance(v, dict) and "size" in v for v in vectors.values()
                )

            # If valid, return the config
            if is_valid:
                return config

            # Schema mismatch - prepare descriptive message
            vector_desc = f"type={type(vectors).__name__}"
            if isinstance(vectors, dict):
                vector_desc += f", keys={list(vectors.keys())}"

            mismatch_msg = (
                f"qdrant collection schema mismatch for {name}: "
                f"expected unnamed(size={dim}, distance={distance}), got {vector_desc}"
            )

            # Add specific details if we could extract size/distance
            if vector_size is not None or vector_distance:
                mismatch_msg += f" with size={vector_size}, distance={vector_distance}"

            # Add named vectors info if detected
            if is_named_vectors:
                mismatch_msg += " (appears to be using named vectors)"

            if recreate_bad:
                # Drop and recreate
                delete_url = url
                delete_r = requests.delete(delete_url, timeout=10)
                if delete_r.status_code not in (200, 204):
                    raise RuntimeError(
                        f"Failed to drop collection '{name}': status {delete_r.status_code}"
                    )

                # Now recreate with correct schema
                payload = {"vectors": {"size": dim, "distance": distance}}
                create_r = requests.put(url, json=payload, timeout=10)
                if create_r.status_code != 200:
                    raise RuntimeError(
                        f"Failed to recreate collection '{name}': status {create_r.status_code}"
                    )

                # Get the final config
                get_r = requests.get(url, timeout=5)
                if get_r.status_code == 200:
                    return get_r.json().get("config", {}) or {
                        "params": {"vectors": payload["vectors"]}
                    }
                return {"params": {"vectors": payload["vectors"]}}
            else:
                # Raise error on mismatch when not recreating
                raise RuntimeError(mismatch_msg)

        # Not found → create it
        if r.status_code == 404:
            payload = {"vectors": {"size": dim, "distance": distance}}
            pr = requests.put(url, json=payload, timeout=10)
            if pr.status_code == 200:
                # Get the final config
                get_r = requests.get(url, timeout=5)
                if get_r.status_code == 200:
                    return get_r.json().get("config", {}) or {
                        "params": {"vectors": payload["vectors"]}
                    }
                return {"params": {"vectors": payload["vectors"]}}

            raise RuntimeError(
                f"Failed to create collection '{name}': status {pr.status_code} {pr.text}"
            )

        # Any other GET status is unexpected
        raise RuntimeError(f"Unexpected status {r.status_code}: {r.text}")

    except Exception as e:
        if isinstance(e, RuntimeError):
            raise
        # Network or other exceptions
        raise RuntimeError(f"Qdrant operation failed: {e}")
