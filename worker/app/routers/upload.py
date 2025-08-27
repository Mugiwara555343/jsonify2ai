from fastapi import APIRouter, UploadFile, File
from pathlib import Path
import shutil
import uuid
import os

router = APIRouter()
DROP = Path("data/dropzone")
DROP.mkdir(parents=True, exist_ok=True)


@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    # sanitize filename
    name = os.path.basename(file.filename or f"file-{uuid.uuid4().hex}")
    dest = DROP / name
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"ok": True, "path": str(dest), "filename": name, "mime": file.content_type}
