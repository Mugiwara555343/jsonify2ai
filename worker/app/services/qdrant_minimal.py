# worker/app/services/qdrant_minimal.py
from __future__ import annotations

import requests
from typing import Dict, Any

from worker.app.config import settings


def _qdrant_base() -> str:
    # e.g. http://host.docker.internal:6333
    return settings.QDRANT_URL.rstrip("/")


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
            vectors_config = None
            config = data.get("config", {})
            params = config.get("params", {})

            # Try the standard path first
            vectors = params.get("vectors", {})

            # Check if we have unnamed vectors (single vector form)
            if "size" in vectors and "distance" in vectors:
                vectors_config = vectors
            else:
                # We might have named vectors or a different format
                if isinstance(vectors, dict) and not any(
                    k in ("size", "distance") for k in vectors
                ):
                    # This appears to be a named vectors structure
                    raise RuntimeError(
                        f"Collection '{name}' uses named vectors, but the project requires unnamed vectors"
                    )

            # Normalize to a standard format for comparison
            if vectors_config:
                size = vectors_config.get("size")
                actual_distance = vectors_config.get("distance")

                if size == dim and actual_distance == distance:
                    # Collection exists with correct config
                    return config

                # Schema mismatch
                mismatch_msg = f"Collection '{name}' schema mismatch: found size={size}, distance={actual_distance}, expected size={dim}, distance={distance}"

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
                        return get_r.json().get("config", {})
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
                    return get_r.json().get("config", {})
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
