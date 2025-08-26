# at top: existing imports
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
import logging

log = logging.getLogger(__name__)
router = APIRouter(prefix="/process", tags=["process"])

# ✅ what the tests expect:
class ProcessTextRequest(BaseModel):
    document_id: str
    path: str
    mime: str
    kind: str

class ProcessTextResponse(BaseModel):
    ok: bool
    document_id: str
    size: int

# (optional) keep your previous name as an alias to avoid breaking anything:
TextPayload = ProcessTextRequest

@router.post("/text", response_model=ProcessTextResponse)
def process_text(p: ProcessTextRequest):
    # Resolve inside-container path; we expect /app/data to be mounted
    file_path = Path(p.path)
    if not file_path.is_file():
        file_path = Path("/app/data") / Path(p.path).name
    if not file_path.is_file():
        log.warning("[process/text] file not found: %s (doc=%s)", p.path, p.document_id)
        raise HTTPException(status_code=404, detail="file not found")

    size = file_path.stat().st_size
    log.info("[process/text] received doc=%s kind=%s mime=%s path=%s size=%d",
             p.document_id, p.kind, p.mime, str(file_path), size)

    return ProcessTextResponse(ok=True, document_id=p.document_id, size=size)
