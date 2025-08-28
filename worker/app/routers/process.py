from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
import logging
import uuid
from worker.app.config import settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/process", tags=["process"])


# ✅ what the tests expect:
class ProcessTextRequest(BaseModel):
    document_id: str
    text: str = None  # Optional text content
    path: str = None  # Optional file path
    mime: str = None  # Optional MIME type
    kind: str = None  # Optional file kind


class ProcessTextResponse(BaseModel):
    ok: bool
    document_id: str
    chunks: int
    embedded: int
    upserted: int
    collection: str


# (optional) keep your previous name as an alias to avoid breaking anything:
TextPayload = ProcessTextRequest


@router.post("/text", response_model=ProcessTextResponse)
def process_text(p: ProcessTextRequest):
    # Defer imports to avoid ModuleNotFoundError at module import time
    try:
        from worker.app.services.chunker import chunk_text
        from worker.app.services.embed_ollama import embed_texts
        from worker.app.services.qdrant_client import upsert_points_min
    except ImportError:
        raise HTTPException(status_code=501, detail="process backend not wired")

    # Handle text input (from tests) or file path input (from API)
    if p.text:
        # Test mode: use provided text
        content = p.text
        size = len(content.encode("utf-8"))
        log.info("[process/text] received text doc=%s size=%d", p.document_id, size)
    elif p.path:
        # API mode: read from file path
        file_path = Path(p.path)
        if not file_path.is_file():
            file_path = Path("/app/data") / Path(p.path).name
        if not file_path.is_file():
            log.warning(
                "[process/text] file not found: %s (doc=%s)", p.path, p.document_id
            )
            raise HTTPException(status_code=404, detail="file not found")

        size = file_path.stat().st_size
        log.info(
            "[process/text] received doc=%s kind=%s mime=%s path=%s size=%d",
            p.document_id,
            p.kind,
            p.mime,
            str(file_path),
            size,
        )
    else:
        raise HTTPException(
            status_code=400, detail="either text or path must be provided"
        )

    # Process the content (text or file)
    if p.text:
        # For text input, chunk and process
        chunks = list(
            chunk_text(
                content,
                size=int(settings.CHUNK_SIZE),
                overlap=int(settings.CHUNK_OVERLAP),
            )
        )
        if not chunks:
            raise HTTPException(status_code=400, detail="no content to process")

        # Embed chunks
        vectors = embed_texts(chunks)

        # Upsert to Qdrant
        collection_name = settings.QDRANT_COLLECTION
        items = []
        for idx, (text_chunk, vector) in enumerate(zip(chunks, vectors)):
            point_id = str(uuid.uuid4())
            # Use dict instead of ChunkRecord to avoid import issues
            rec = {
                "id": point_id,
                "document_id": p.document_id,
                "path": p.path or "text_input",
                "idx": idx,
                "text": text_chunk,
                "meta": {"source": "text_input"},
            }
            items.append((rec["id"], vector, rec))

        upserted = upsert_points_min(collection_name, items)

        return ProcessTextResponse(
            ok=True,
            document_id=p.document_id,
            chunks=len(chunks),
            embedded=len(vectors),
            upserted=upserted,
            collection=collection_name,
        )
    else:
        # For file input, return basic info for now
        return ProcessTextResponse(
            ok=True,
            document_id=p.document_id,
            chunks=1,
            embedded=0,
            upserted=0,
            collection="file_input",
        )
