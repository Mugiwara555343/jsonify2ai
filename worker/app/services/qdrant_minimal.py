import requests
import logging
from typing import Optional, Tuple, Any, Dict, Union
from ..config import settings

logger = logging.getLogger(__name__)

# ---------- helpers to robustly read Qdrant shapes ----------

def _get_vectors_block(result_obj: Dict[str, Any]) -> Union[Dict[str, Any], None]:
    """
    Qdrant HTTP returns:
      { "result": { "config": { "params": { "vectors": ... } } }, "status": "ok" }
    'vectors' can be:
      - { "size": int, "distance": "Cosine" }               (single unnamed vector)
      - { "<name>": { "size": int, "distance": "Cosine" } } (named vectors map)
    """
    try:
        return result_obj["config"]["params"]["vectors"]
    except (KeyError, TypeError):
        return None

def _extract_dim_from_vectors(vectors: Any) -> Optional[int]:
    """Return the dimension from the 'vectors' block, regardless of shape."""
    if vectors is None:
        return None

    # Case 1: single unnamed vector {"size": 768, "distance": "Cosine"}
    if isinstance(vectors, dict) and "size" in vectors:
        try:
            return int(vectors["size"])
        except Exception:
            return None

    # Case 2: named vectors {"image": {...}, "text": {...}}
    if isinstance(vectors, dict) and vectors:
        first = next(iter(vectors.values()))
        if isinstance(first, dict) and "size" in first:
            try:
                return int(first["size"])
            except Exception:
                return None

    return None

def ensure_collection_minimal(name: str, dim: int) -> Tuple[bool, Optional[str]]:
    """
    Ensure Qdrant collection exists with correct dimensions using minimal HTTP requests.

    Returns (ok, error_message). If ok is False, no destructive changes were made.
    """
    try:
        # 1) Check if collection exists
        url = f"{settings.QDRANT_URL}/collections/{name}"
        response = requests.get(url, timeout=10)

        # 2) Collection exists → verify dimensions
        if response.status_code == 200:
            try:
                root = response.json()
            except ValueError as e:
                return False, f"Invalid JSON from Qdrant for '{name}': {e}"

            result = root.get("result") or {}
            vectors_block = _get_vectors_block(result)
            current_dim = _extract_dim_from_vectors(vectors_block)

            if current_dim is None:
                return False, f"Collection '{name}' exists but has no vector size configuration"

            if current_dim != dim:
                return False, (
                    f"Collection '{name}' exists with dimension {current_dim}, "
                    f"but model expects {dim}"
                )

            logger.info(f"Collection '{name}' verified: size={current_dim}")
            return True, None

        # 3) Not found → create (single-vector config)
        elif response.status_code == 404:
            create_url = f"{settings.QDRANT_URL}/collections/{name}"
            create_body = {"vectors": {"size": dim, "distance": "Cosine"}}
            create_response = requests.put(create_url, json=create_body, timeout=10)

            if create_response.status_code == 200:
                logger.info(f"Collection '{name}' created: size={dim}, distance=Cosine")
                return True, None

            body = ""
            try:
                body = create_response.text.strip()
            except Exception:
                pass
            return False, (
                f"Failed to create collection '{name}': status {create_response.status_code}"
                + (f", response: {body}" if body else "")
            )

        # 4) Any other status → bubble up detail
        else:
            body = ""
            try:
                body = response.text.strip()
            except Exception:
                pass
            return False, (
                f"Unexpected response checking collection '{name}': status {response.status_code}"
                + (f", response: {body}" if body else "")
            )

    except requests.exceptions.RequestException as e:
        return False, f"Request error ensuring collection '{name}': {e}"
    except Exception as e:
        return False, f"Unexpected error ensuring collection '{name}': {e}"
