# worker/app/services/file_router.py
from __future__ import annotations


from pathlib import Path
from typing import Optional

# Always‑available parsers (no heavy deps)
from .parse_csv import extract_text_from_csv
from .parse_json import extract_text_from_json, extract_text_from_jsonl

# NOTE:
# - PDF/DOCX/Audio are imported lazily *inside* the branch that needs them.
#   That way this module can be imported even if optional deps aren’t installed.

AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}


def _read_text(path: Path) -> str:
    """UTF‑8 text reader with forgiving errors."""
    return path.read_text(encoding="utf-8", errors="ignore")


def extract_text_auto(path: str | Path, mime: Optional[str] = None) -> str:
    """
    Return extracted text for the given file path.

    Optional parsers:
      - .pdf    -> requires `pypdf`      (pip install -r worker/requirements.pdf.txt)
      - .docx   -> requires `python-docx`(pip install -r worker/requirements.docx.txt)
      - audio   -> requires faster-whisper + ffmpeg
                   (pip install -r worker/requirements.audio.txt)

    If an optional dependency is missing, we raise ModuleNotFoundError with a
    clear message so callers can choose to skip gracefully (default behavior in
    the drop‑zone script) or fail with --strict.
    """
    p = Path(path)
    ext = p.suffix.lower()

    # Text family
    if ext in {".txt", ".md"}:
        return _read_text(p)

    # CSV / TSV
    if ext in {".csv", ".tsv"}:
        return extract_text_from_csv(str(p))

    # JSON / JSONL
=======
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


    # DOCX (lazy import)
    if ext == ".docx":
        try:
            from .parse_docx import extract_text_from_docx  # noqa: WPS433 (local import)
        except Exception as e:  # ModuleNotFoundError or other import-time issues
            raise ModuleNotFoundError(
                "DOCX support not installed. Run: pip install -r worker/requirements.docx.txt"
            ) from e
        return extract_text_from_docx(str(p))

    # PDF (lazy import)
    if ext == ".pdf":
        try:
            from .parse_pdf import extract_text_from_pdf  # noqa: WPS433
        except Exception as e:
            raise ModuleNotFoundError(
                "PDF support not installed. Run: pip install -r worker/requirements.pdf.txt"
            ) from e
        return extract_text_from_pdf(str(p))

    # Audio (lazy import; AUDIO_DEV_MODE handled inside parse_audio)
    if ext in AUDIO_EXTS:
        try:
            from .parse_audio import transcribe_audio  # noqa: WPS433
        except Exception as e:
            raise ModuleNotFoundError(
                "Audio STT not installed. Run: pip install -r worker/requirements.audio.txt "
                "and make sure ffmpeg is installed."
            ) from e
        return transcribe_audio(str(p))

    # Fallback: treat anything else as UTF‑8 text
    return _read_text(p)
=======
    if ext == ".docx":
        return extract_text_from_docx(str(p))
    if ext == ".pdf":
        return extract_text_from_pdf(str(p))
    if ext in AUDIO_EXTS:
        return transcribe_audio(str(p))

    # Default: treat as text
    return p.read_text(encoding="utf-8", errors="ignore")

