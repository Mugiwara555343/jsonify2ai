# worker/app/services/file_router.py
from __future__ import annotations
from pathlib import Path
from typing import Optional

from .parse_csv import extract_text_from_csv
from .parse_json import extract_text_from_json, extract_text_from_jsonl
from .parse_docx import extract_text_from_docx
from .parse_pdf import extract_text_from_pdf
from .parse_audio import transcribe_audio

AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}

def extract_text_auto(path: str, mime: Optional[str] = None) -> str:
    p = Path(path)
    ext = p.suffix.lower()

    if ext in {".csv", ".tsv"}:
        return extract_text_from_csv(str(p))
    if ext == ".jsonl":
        return extract_text_from_jsonl(str(p))
    if ext == ".json":
        return extract_text_from_json(str(p))
    if ext == ".docx":
        return extract_text_from_docx(str(p))
    if ext == ".pdf":
        return extract_text_from_pdf(str(p))
    if ext in AUDIO_EXTS:
        return transcribe_audio(str(p))

    # Default: treat as text
    return p.read_text(encoding="utf-8", errors="ignore")
