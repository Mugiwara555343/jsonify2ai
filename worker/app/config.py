# worker/app/config.py
from __future__ import annotations

from pathlib import Path
from typing import Optional
from uuid import UUID

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve repo root: repo/ (since this file is repo/worker/app/config.py)
REPO_ENV = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """
    Central config for the worker. Uses Pydantic v2 + pydantic-settings.

    - Loads env from the repo root .env if present
    - Ignores unknown env vars (prevents CI/local crashes)
    - Case-insensitive env keys
    - Sane defaults for local dev & tests (no live services required)
    - Captures *pipeline contract* knobs (ids, chunking, batching, versions)
    """

    model_config = SettingsConfigDict(
        env_file=str(REPO_ENV),
        extra="ignore",  # accept extra env vars (POSTGRES_DSN, PORT_API, etc.)
        case_sensitive=False,  # allow OLLAMA_URL or ollama_url, etc.
    )

    # --- Service URLs ---------------------------------------------------------
    OLLAMA_URL: str = "http://host.docker.internal:11434"
    QDRANT_URL: str = "http://host.docker.internal:6333"

    # --- Collections (text and optional images) -------------------------------
    QDRANT_COLLECTION: str = "jsonify2ai_chunks"
    QDRANT_COLLECTION_IMAGES: str = "jsonify2ai_images_768"

    # --- Embeddings -----------------------------------------------------------
    EMBEDDINGS_MODEL: str = "nomic-embed-text"
    EMBEDDING_DIM: int = 768

    # Batch sizes (keep small for CPU/dev, bump in prod)
    EMBED_BATCH_SIZE: int = 64
    QDRANT_UPSERT_BATCH_SIZE: int = 128

    # --- Chunking (token-ish sizing) -----------------------------------------
    CHUNK_SIZE: int = 800
    CHUNK_OVERLAP: int = 100
    NORMALIZE_WHITESPACE: int = 1  # normalize spaces/newlines before chunk/hash

    # --- Hashing & IDs --------------------------------------------------------
    # Document hash is sha256(file bytes); chunk hash uses normalized text.
    # Namespace seed for UUID5(document_hash) to make document_id deterministic.
    NAMESPACE_SEED: str = "2b00c5a8-0ec2-4f1f-9c7e-3f7b7c0f8a77"  # can override in .env
    USE_DOC_HASH_FROM_BYTES: int = 1  # 1=file bytes, 0=normalized text

    # --- Dev Toggles / Modes --------------------------------------------------
    EMBED_DEV_MODE: int = 0  # 1 to bypass real embeddings in dev/tests
    AUDIO_DEV_MODE: int = 0  # 1 -> stub transcript; requires no ffmpeg/whisper
    IMAGES_CAPTION: int = 0  # 1 -> enable BLIP captioning path (optional)
    STT_MODEL: str = "tiny"
    DEBUG_CONFIG: Optional[int] = 0
    QDRANT_RECREATE_BAD: int = 0  # 1 -> auto recreate bad/mismatched collection

    # --- Dropzone / Exports (used by scripts + status summaries) --------------
    DROPZONE_DIR: str = "data/dropzone"
    EXPORT_JSONL: str = "data/exports/ingest.jsonl"

    # --- Pipeline versioning (for payload/debug provenance) -------------------
    PIPELINE_VERSION: str = "2025-08-31"
    PARSER_REGISTRY_VERSION: str = "2025-08-31"
    CHUNKER_NAME: str = "standard_fixed"
    CHUNKER_VERSION: str = "1.0"

    # --- Ask/LLM defaults -----------------------------------------------------
    ASK_MODE: str = "search"  # search|llm
    ASK_MODEL: str = "qwen2.5:3b-instruct-q4_K_M"
    ASK_MAX_TOKENS: int = 512
    ASK_TEMP: float = 0.3
    ASK_TOP_P: float = 0.9

    # --- Timeouts / Limits (ms) ----------------------------------------------
    HTTP_TIMEOUT_MS: int = 15000  # outbound calls (ollama/qdrant)
    PARSER_TIMEOUT_MS: int = 120000  # per-file parser max
    MAX_FILE_BYTES: int = 1024 * 1024 * 128  # 128 MiB soft cap

    # --- Sanity/filters -------------------------------------------------------
    IGNORE_GLOBS: str = "*.tmp,*.part,~$*,.DS_Store,__pycache__"

    # Convenience: expose a UUID object from NAMESPACE_SEED (validated by pydantic)
    @property
    def NAMESPACE_UUID(self) -> UUID:
        return UUID(self.NAMESPACE_SEED)


# Singleton-style instance used by the app/tests
settings = Settings()
