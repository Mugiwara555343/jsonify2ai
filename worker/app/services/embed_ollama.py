import requests
import hashlib
import os
from typing import List
from worker.app.config import settings


def _parse_embeddings(json_obj) -> List[List[float]]:
    """
    Parse embeddings from Ollama responses.

    Supported shapes:
      1) Modern /api/embed (single or batch):
         {"embeddings": [[...], [...], ...]}

      2) Older /api/embeddings (single):
         {"embedding": [...]}

      3) Older /api/embeddings (batch):
         {"embeddings": [{"embedding": [...]}, ...]}

    Returns:
        List[List[float]]  # one vector per input text
    """
    # Case 1: Modern shape -> embeddings is a list of vectors
    if isinstance(json_obj, dict) and "embeddings" in json_obj:
        embs = json_obj["embeddings"]
        if isinstance(embs, list):
            if len(embs) == 0:
                return []
            first = embs[0]
            # Modern: list[list[float]]
            if isinstance(first, list):
                return embs
            # Legacy-batch: list[{"embedding":[...]}]
            if isinstance(first, dict) and "embedding" in first:
                return [item["embedding"] for item in embs]
    # Case 2: Legacy single: {"embedding":[...]}
    if isinstance(json_obj, dict) and "embedding" in json_obj:
        return [json_obj["embedding"]]

    raise ValueError("Unexpected Ollama response format while parsing embeddings")


def _generate_dummy_embedding(text: str, dim: int) -> List[float]:
    """
    Generate deterministic dummy embedding for dev mode.
    """
    h = hashlib.sha256(text.encode("utf-8")).digest()
    # Map hash bytes to floats in [0,1)
    return [h[i % len(h)] / 256.0 for i in range(dim)]


def embed_texts(
    texts: List[str],
    model: str | None = None,
    base_url: str | None = None,
    dim: int | None = None,
) -> List[List[float]]:
    """
    Embed texts using Ollama.

    - Uses /api/embed (modern, stable).
    - Backwards-compatible parser accepts older shapes.

    Args:
        texts: List of texts to embed (len >= 1)
        model: Embedding model name (defaults to config)
        base_url: Ollama base URL (defaults to config)
        dim: Expected embedding dimension (defaults to config)

    Returns:
        List of embedding vectors (one per input text)
    """
    if not texts:
        return []

    model = model or settings.EMBEDDINGS_MODEL
    base_url = base_url or settings.OLLAMA_URL
    dim = dim or settings.EMBEDDING_DIM

    # Dev mode short-circuit
    if os.getenv("EMBED_DEV_MODE") == "1":
        return [_generate_dummy_embedding(t, dim) for t in texts]

    # Modern endpoint (plural): /api/embed
    url = f"{base_url.rstrip('/')}/api/embed"
    payload = {"model": model, "input": texts}

    try:
        resp = requests.post(url, json=payload, timeout=180)
        resp.raise_for_status()
        data = resp.json()

        embeddings = _parse_embeddings(data)

        # Validate count and non-empty vectors
        if len(embeddings) != len(texts):
            raise ValueError(
                f"Embedding count mismatch: expected {len(texts)}, got {len(embeddings)}"
            )
        if not embeddings or not embeddings[0]:
            raise ValueError("Empty embedding returned from Ollama")

        return embeddings

    except requests.HTTPError as e:
        raise ValueError(f"Ollama API error: {e}")
    except requests.RequestException as e:
        raise ValueError(f"Network error: {e}")
    except (ValueError, KeyError, TypeError) as e:
        raise ValueError(f"Response parsing error: {e}")
    except Exception as e:
        raise ValueError(f"Unexpected error: {e}")
