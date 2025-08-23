# worker/app/config.py
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve repo root: repo/ (since this file is repo/worker/app/config.py)
REPO_ENV = Path(__file__).resolve().parents[2] / ".env"

class Settings(BaseSettings):
    """
    Central config for the worker. Uses Pydantic v2 + pydantic-settings.
    - Loads env from the repo root .env if present
    - Ignores unknown env vars (prevents CI/local crashes)
    - Case-insensitive env keys
    - Provides sane defaults for unit tests (no live services required)
    """
    model_config = SettingsConfigDict(
        env_file=str(REPO_ENV),
        extra="ignore",          # <- accept extra env vars (POSTGRES_DSN, PORT_API, etc.)
        case_sensitive=False,    # <- allow OLLAMA_URL or ollama_url, etc.
    )

    # --- Known fields (defaults safe for tests) ---
    OLLAMA_URL: str = "http://host.docker.internal:11434"
    QDRANT_URL: str = "http://host.docker.internal:6333"
    QDRANT_COLLECTION: str = "jsonify2ai_chunks"
    QDRANT_COLLECTION_IMAGES: str = "jsonify2ai_images_768"

    EMBEDDINGS_MODEL: str = "nomic-embed-text"
    EMBEDDING_DIM: int = 768

    CHUNK_SIZE: int = 800
    CHUNK_OVERLAP: int = 100

    EMBED_DEV_MODE: int = 0      # 1 to bypass real embeddings in dev/tests
    DEBUG_CONFIG: Optional[int] = 0
    STT_MODEL: str = "tiny"
    AUDIO_DEV_MODE: int = 0
    IMAGES_CAPTION: int = 0
    QDRANT_RECREATE_BAD: int = 0


# Singleton-style instance used by the app/tests
settings = Settings()
