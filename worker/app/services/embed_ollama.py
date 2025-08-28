import requests
import hashlib
import os
from typing import List
from worker.app.config import settings


def _parse_embeddings(json_obj) -> List[List[float]]:
    """
    Parse embeddings from Ollama API response.

    Handles both response shapes:
    - Single input: {"embedding": [...]}
    - Batch input: {"embeddings": [{"embedding": [...]}, ...]}

    Args:
        json_obj: Parsed JSON response from Ollama

    Returns:
        List of embedding vectors

    Raises:
        ValueError: If response shape is unexpected
    """
    if "embedding" in json_obj:
        # Single input response
        return [json_obj["embedding"]]
    elif "embeddings" in json_obj:
        # Batch response
        return [item["embedding"] for item in json_obj["embeddings"]]
    else:
        raise ValueError("Unexpected Ollama response format")


def _generate_dummy_embedding(text: str, dim: int) -> List[float]:
    """
    Generate deterministic dummy embedding for dev mode.

    Args:
        text: Input text to hash
        dim: Embedding dimension

    Returns:
        List of floats in [0, 1) based on text hash
    """
    # Create stable hash
    hash_obj = hashlib.sha256(text.encode("utf-8"))
    hash_bytes = hash_obj.digest()

    # Map hash bytes to floats in [0, 1)
    embedding = []
    for i in range(dim):
        byte_idx = i % len(hash_bytes)
        # Normalize byte value to [0, 1)
        embedding.append(hash_bytes[byte_idx] / 256.0)

    return embedding


def embed_texts(
    texts: List[str], model: str = None, base_url: str = None, dim: int = None
) -> List[List[float]]:
    """
    Embed texts using Ollama embeddings API or dev mode.

    Args:
        texts: List of texts to embed
        model: Model name (defaults to config)
        base_url: Ollama base URL (defaults to config)
        dim: Embedding dimension (defaults to config)

    Returns:
        List of embedding vectors

    Raises:
        ValueError: On API errors or response format issues
    """
    if not texts:
        return []

    model = model or settings.EMBEDDINGS_MODEL
    base_url = base_url or settings.OLLAMA_URL
    dim = dim or settings.EMBEDDING_DIM

    # Check for dev mode
    if os.getenv("EMBED_DEV_MODE") == "1":
        return [_generate_dummy_embedding(text, dim) for text in texts]

    # Call Ollama API
    url = f"{base_url}/api/embeddings"
    payload = {"model": model, "input": texts}

    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()

        result = response.json()
        embeddings = _parse_embeddings(result)

        # Validate response length matches input
        if len(embeddings) != len(texts):
            raise ValueError(
                f"Embedding count mismatch: expected {len(texts)}, got {len(embeddings)}"
            )

        return embeddings

    except requests.HTTPError as e:
        raise ValueError(f"Ollama API error: {e}")
    except requests.RequestException as e:
        raise ValueError(f"Network error: {e}")
    except (ValueError, KeyError, TypeError) as e:
        raise ValueError(f"Response parsing error: {e}")
    except Exception as e:
        raise ValueError(f"Unexpected error: {e}")
