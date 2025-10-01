from __future__ import annotations
from typing import List
from docx import Document  # requires python-docx


def parse_docx(path: str) -> List[str]:
    """
    Parse DOCX paragraphs as a list of strings (skips empty).
    """
    doc = Document(path)
    chunks: List[str] = []
    for p in doc.paragraphs:
        t = (p.text or "").strip()
        if t:
            chunks.append(t)
    return chunks
