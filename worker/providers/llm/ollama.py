# worker/providers/llm/ollama.py
"""
Ollama LLM provider for answer synthesis.

Usage:
    from worker.providers.llm.ollama import generate

    answer = generate(
        prompt="Answer this...",
        host="http://localhost:11434",
        model="llama3.1:8b",
        timeout=180
    )
"""

import requests
from typing import Optional
from worker.app.config import settings


def generate(
    prompt: str,
    host: Optional[str] = None,
    model: Optional[str] = None,
    timeout: int = 180,
) -> str:
    """
    Generate text using Ollama API.

    Args:
        prompt: The prompt to send to the LLM
        host: Ollama host (default: settings.OLLAMA_HOST or http://localhost:11434)
        model: Model to use (default: settings.OLLAMA_MODEL or llama3.1:8b)
        timeout: Request timeout in seconds (default: 180)

    Returns:
        Generated text on success, empty string on failure
    """
    # Get defaults from settings or use sensible defaults
    if host is None:
        host = settings.OLLAMA_HOST
    if model is None:
        model = settings.OLLAMA_MODEL

    try:
        response = requests.post(
            f"{host}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": settings.LLM_TEMPERATURE,
                    "top_p": settings.LLM_TOP_P,
                    "repeat_penalty": settings.LLM_REPEAT_PENALTY,
                    "num_ctx": settings.LLM_NUM_CTX,
                    "num_predict": settings.LLM_MAX_TOKENS,
                },
            },
            timeout=timeout,
        )

        # Handle non-2xx responses gracefully
        if not (200 <= response.status_code < 300):
            return ""

        data = response.json()
        return data.get("response", "").strip()

    except Exception:
        # Return empty string on any failure
        return ""
