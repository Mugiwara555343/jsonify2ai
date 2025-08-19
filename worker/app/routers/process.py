"""
Routers: text & image processing.

- TEXT: unchanged behavior (chunk → embed → upsert via your existing helper).
- IMAGE (dev mode): caption-from-filename → deterministic embedding
  → direct Qdrant upsert, using a UUIDv5 point ID (no 'parallel' kwarg).

Important updates in this file:
  1) /process/image uses UUIDv5 for point IDs (Qdrant requires int or UUID).
  2) /process/image still checks/creates collection via ensure_collection_minimal(...).
  3) /process/image avoids the shared upsert helper to stay compatible with your qdrant-client.
  4) _dev_mode() is robust (env first, then settings; accepts 1/true/yes/on).
  5) GET /process/image/debug remains for quick visibility of what the image path sees.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from uuid import UUID, uuid5  # --- NEW: for deterministic UUID point IDs

# ---------- TEXT pipeline imports (existing) ----------
from ..services.chunker import chunk_text
from ..services.embed_ollama import embed_texts
from ..services.qdrant_client import get_qdrant_client, upsert_points  # text path uses helper
from ..services.qdrant_minimal import ensure_collection_minimal
from ..config import settings

# ---------- IMAGE: direct Qdrant structs ----------
from qdrant_client.models import PointStruct

# ---------- IMAGE models ----------
from ..models import ImageProcessIn, ImageProcessOut

router = APIRouter()

# =============================================================================
# TEXT PIPELINE (kept intact)
# =============================================================================

class ProcessTextRequest(BaseModel):
    document_id: str = Field(..., description="Unique document identifier")
    text: Optional[str] = Field(None, description="Raw text content")
    path: Optional[str] = Field(None, description="Path to text file")

class ProcessTextResponse(BaseModel):
    ok: bool
    document_id: str
    chunks: int
    embedded: int
    upserted: int
    collection: str
    error: Optional[str] = None

@router.post("/text", response_model=ProcessTextResponse)
async def process_text(request: ProcessTextRequest):
    """
    Process text: chunk, embed, and store in Qdrant.

    Accepts either raw text or file path, processes into chunks,
    generates embeddings via Ollama (or dev mode in embed_texts), and stores vectors.
    """
    try:
        # 1) Source text
        text_content = request.text
        if request.path and not text_content:
            file_path = Path(request.path)
            if not file_path.exists():
                raise HTTPException(status_code=400, detail="File not found")
            if file_path.stat().st_size > 5 * 1024 * 1024:
                raise HTTPException(status_code=400, detail="File too large (>5MB)")
            try:
                text_content = file_path.read_text(encoding="utf-8")
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to read file: {e}")

        if not text_content or not text_content.strip():
            raise HTTPException(status_code=400, detail="No text content provided")

        # 2) Chunk
        chunks = chunk_text(text_content, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)
        if not chunks:
            raise HTTPException(status_code=400, detail="No chunks generated")

        # 3) Embed
        try:
            embeddings = embed_texts(
                chunks,
                settings.EMBEDDINGS_MODEL,
                settings.OLLAMA_URL,
                settings.EMBEDDING_DIM,
            )
            if len(embeddings) != len(chunks):
                raise ValueError("Embedding count mismatch")
        except ValueError as e:
            return ProcessTextResponse(
                ok=False,
                document_id=request.document_id,
                chunks=len(chunks),
                embedded=0,
                upserted=0,
                collection=settings.QDRANT_COLLECTION,
                error=f"Embedding error: {e}",
            )

        # 4) Ensure collection
        qdrant_client = get_qdrant_client()
        collection_name = settings.QDRANT_COLLECTION
        ok, err = ensure_collection_minimal(collection_name, settings.EMBEDDING_DIM)
        if not ok:
            return ProcessTextResponse(
                ok=False,
                document_id=request.document_id,
                chunks=len(chunks),
                embedded=len(embeddings),
                upserted=0,
                collection=collection_name,
                error=f"Collection error: {err}",
            )

        # 5) Build payloads + IDs and upsert via existing helper
        payloads, ids = [], []
        for idx, chunk in enumerate(chunks):
            payloads.append({"document_id": request.document_id, "idx": idx, "text": chunk})
            ids.append(f"{request.document_id}:{idx}")

        upsert_points(qdrant_client, collection_name, embeddings, payloads, ids)

        return ProcessTextResponse(
            ok=True,
            document_id=request.document_id,
            chunks=len(chunks),
            embedded=len(embeddings),
            upserted=len(ids),
            collection=collection_name,
        )

    except HTTPException:
        raise
    except Exception as e:
        return ProcessTextResponse(
            ok=False,
            document_id=request.document_id,
            chunks=0,
            embedded=0,
            upserted=0,
            collection=settings.QDRANT_COLLECTION,
            error=str(e),
        )

# =============================================================================
# IMAGE PIPELINE (dev-mode stub)
#   - Path: POST /process/image  (router is mounted at '/process' in main app)
#   - Changes:
#       * Deterministic UUIDv5 point ID (Qdrant requires int/UUID; avoids SHA1 hex issue)
#       * Direct client.upsert(...) (no 'parallel' kwarg)
#       * Robust _dev_mode() that honors .env and accepts 1/true/yes/on
# =============================================================================

def _images_collection_name() -> str:
    """Images collection name (env override allowed)."""
    return os.getenv("QDRANT_IMAGES_COLLECTION", "jsonify2ai_images")

def _embedding_dim() -> int:
    try:
        return int(getattr(settings, "EMBEDDING_DIM", 768))
    except Exception:
        return 768

def _dev_mode() -> bool:
    """
    Truthy when EMBED_DEV_MODE is set to 1/true/yes/on.
    Env has priority; settings fallback.
    """
    val = os.getenv("EMBED_DEV_MODE", None)
    if val is None:
        val = getattr(settings, "EMBED_DEV_MODE", "0")

    if isinstance(val, bool):
        return val
    try:
        return int(str(val)) != 0
    except Exception:
        pass
    return str(val).strip().lower() in ("1", "true", "yes", "on")

@router.get("/image/debug")
def image_debug_config():
    """Quick probe to verify what *this* router sees."""
    return {
        "seen_dev_mode": _dev_mode(),
        "dim": _embedding_dim(),
        "collection": _images_collection_name(),
    }

def _stub_caption(path: str) -> str:
    """Deterministic caption from filename (no file I/O needed)."""
    p = Path(path)
    stem = p.stem or "image"
    ext = (p.suffix or "").lower()
    return f"image:{stem} {ext}".strip()

def _deterministic_embedding(text: str, dim: int) -> List[float]:
    """SHA1(text) → values in [-1, 1] for reproducible dev-mode vectors."""
    h = hashlib.sha1(text.encode("utf-8", "ignore")).digest()
    return [((h[i % len(h)] / 255.0) * 2.0 - 1.0) for i in range(dim)]

@router.post("/image", response_model=ImageProcessOut)
async def process_image(request: ImageProcessIn) -> ImageProcessOut:
    """
    Dev-mode image pipeline:
      1) Caption from filename
      2) Deterministic embedding (no external model)
      3) Direct Qdrant upsert with a UUIDv5 point ID (derived from document_id + path)
    """
    if not _dev_mode():
        raise HTTPException(status_code=503, detail="Set EMBED_DEV_MODE=1 for image dev mode.")

    collection = _images_collection_name()
    dim = _embedding_dim()

    # 1) caption
    caption = _stub_caption(request.path)

    # 2) embedding
    vector = _deterministic_embedding(caption, dim)

    # 3) ensure collection exists with correct dim
    ok, err = ensure_collection_minimal(collection, dim)
    if not ok:
        raise HTTPException(status_code=502, detail=f"Collection error: {err}")

    # 4) upsert directly using a UUIDv5 point ID
    try:
        client = get_qdrant_client()

        # --- NEW: deterministic UUID ID instead of SHA1 hex string ---
        # This satisfies Qdrant's "unsigned integer or UUID" requirement.
        # Namespace = the document_id itself; Name = the path (keeps it stable & unique per doc/path)
        if isinstance(request.document_id, UUID):
            ns = request.document_id
        else:
            ns = UUID(str(request.document_id))

        point_uuid = uuid5(ns, request.path)  # deterministic, stable across re-runs
        payload = {
            "kind": "image",
            "document_id": str(request.document_id),
            "path": request.path,
            "caption": caption,
        }
        points = [PointStruct(id=str(point_uuid), vector=vector, payload=payload)]
        client.upsert(collection_name=collection, points=points)  # no 'parallel' kwarg
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"image upsert failed: {e}")

    return ImageProcessOut(ok=True, caption=caption, points_written=1, collection=collection)
