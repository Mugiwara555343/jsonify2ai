# worker/app/services/qdrant_minimal.py
from __future__ import annotations

from typing import Optional, Tuple
import requests

from app.config import settings


def _qdrant_base() -> str:
    # e.g. http://host.docker.internal:6333
    return settings.QDRANT_URL.rstrip("/")


def ensure_collection_minimal(name: str, dim: int) -> Tuple[bool, Optional[str]]:
    """
    Idempotently ensure a Qdrant collection exists with the given vector size.
    Uses plain HTTP so it's easy to unit test.

    Returns:
        (True, None)   -> collection exists with matching dim OR was created successfully
        (False, error) -> mismatch, API failure, or unexpected error
    """
    url = f"{_qdrant_base()}/collections/{name}"

    try:
        # Check if collection exists
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            data = r.json()
            size = (
                data.get("config", {}).get("params", {}).get("vectors", {}).get("size")
            )
            if size == dim:
                return True, None  # existed + OK  :contentReference[oaicite:0]{index=0}
            return (
                False,
                f"Collection '{name}' exists with dimension {size}, but model expects {dim}",
            )  # mismatch  :contentReference[oaicite:1]{index=1}

        # Not found → create it
        if r.status_code == 404:
            payload = {"vectors": {"size": dim, "distance": "Cosine"}}
            pr = requests.put(url, json=payload, timeout=10)
            if pr.status_code == 200:
                return True, None  # created OK  :contentReference[oaicite:2]{index=2}
            return (
                False,
                f"Failed to create collection '{name}': status {pr.status_code} {pr.text}",
            )  # creation failed  :contentReference[oaicite:3]{index=3}

        # Any other GET status is unexpected
        return False, f"Unexpected status {r.status_code}: {r.text}"

    except Exception as e:
        # Network or other exceptions
        return False, f"Unexpected error: {e}"  #  :contentReference[oaicite:4]{index=4}
