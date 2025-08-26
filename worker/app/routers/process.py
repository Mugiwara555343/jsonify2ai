from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
import logging

log = logging.getLogger(__name__)
router = APIRouter(prefix="/process", tags=["process"])


class TextPayload(BaseModel):
    document_id: str
    path: str
    mime: str
    kind: str


@router.post("/text")
def process_text(p: TextPayload):
    # Resolve path inside container; we expect /app/data is mounted via compose.
    file_path = Path(p.path)
    if not file_path.is_file():
        # try to normalize (some callers may pass relative or host-like paths)
        file_path = Path("/app/data") / Path(p.path).name
    if not file_path.is_file():
        log.warning("[process/text] file not found: %s (doc=%s)", p.path, p.document_id)
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

    # TODO: parse -> chunk -> embed -> upsert (next slice)
    return {"ok": True, "document_id": p.document_id, "size": size}
