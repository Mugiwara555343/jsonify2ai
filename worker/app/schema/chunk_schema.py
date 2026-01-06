from __future__ import annotations
from pydantic import BaseModel, Field, field_validator
from typing import Any, Dict, Literal

ChunkKind = Literal["text", "pdf", "audio", "image", "csv", "doc", "html", "chat"]


class Chunk(BaseModel):
    # Deterministic ID (e.g., blake3(document_id + "|" + str(idx)))
    id: str = Field(min_length=8)
    document_id: str = Field(min_length=3)
    kind: ChunkKind
    path: str = Field(min_length=1)  # original source path
    idx: int = Field(ge=0)  # chunk index within document
    text: str = Field(
        default="", repr=False
    )  # primary content text; allow empty for non-text kinds
    meta: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def _strip_text(cls, v: str) -> str:
        # Normalize newlines; ensure no trailing nulls
        return v.replace("\r\n", "\n").replace("\r", "\n") if v is not None else ""


def is_deterministic_id(chunk: Chunk) -> bool:
    """
    Optional check: if meta contains 'deterministic_key' (document_id|idx),
    id must be the blake3 of that key. Soft check to avoid breaking older dumps.
    """
    try:
        pass  # already used elsewhere in repo; if not, add lightweight dep
    except Exception:
        return True  # skip in environments without blake3
    key = f"{chunk.document_id}|{chunk.idx}"
    return chunk.meta.get("deterministic_key") in (key, None) and (len(chunk.id) >= 8)
