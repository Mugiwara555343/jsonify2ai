# worker/app/models.py
from pydantic import BaseModel
from uuid import UUID

class ImageProcessIn(BaseModel):
    document_id: UUID
    path: str  # repo-relative or absolute

class ImageProcessOut(BaseModel):
    ok: bool = True
    caption: str
    points_written: int = 0
    collection: str
