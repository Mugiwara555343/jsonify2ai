import requests
from typing import List
from ..config import settings

def embed_texts(texts: List[str], model: str = None, base_url: str = None) -> List[List[float]]:
    """
    Embed texts using Ollama embeddings API.
    
    Args:
        texts: List of texts to embed
        model: Model name (defaults to config)
        base_url: Ollama base URL (defaults to config)
    
    Returns:
        List of embedding vectors
    
    Raises:
        requests.HTTPError: On non-200 response
    """
    if not texts:
        return []
    
    model = model or settings.EMBEDDINGS_MODEL
    base_url = base_url or settings.OLLAMA_URL
    
    url = f"{base_url}/api/embeddings"
    payload = {
        "model": model,
        "input": texts
    }
    
    response = requests.post(url, json=payload, timeout=30)
    
    if response.status_code != 200:
        raise requests.HTTPError(
            f"Ollama API error: {response.status_code} - {response.text}"
        )
    
    result = response.json()
    return [item["embedding"] for item in result["data"]]
