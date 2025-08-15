import os
from pathlib import Path
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load .env from repo root if present
repo_root = Path(__file__).parent.parent.parent
env_path = repo_root / ".env"
if env_path.exists():
    load_dotenv(env_path)

class Settings(BaseSettings):
    OLLAMA_URL: str = "http://host.docker.internal:11434"
    QDRANT_URL: str = "http://host.docker.internal:6333"
    QDRANT_COLLECTION: str = "jsonify2ai_chunks"
    EMBEDDINGS_MODEL: str = "nomic-embed-text"
    EMBEDDING_DIM: int = 768
    CHUNK_SIZE: int = 800
    CHUNK_OVERLAP: int = 100

    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
