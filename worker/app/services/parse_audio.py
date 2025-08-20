# worker/app/services/parse_audio.py
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from app.config import settings


def transcribe_audio(
    path: str,
    model_size: Optional[str] = None,
    beam_size: int = 1,
    vad_filter: bool = True,
) -> str:
    """
    Transcribe an audio file to text.

    - If AUDIO_DEV_MODE=1 (env or settings), returns a quick stub so tests/CI stay fast.
    - Otherwise uses faster-whisper on CPU (compute_type=int8).
    - Requires ffmpeg available on PATH for mp3/m4a etc.

    Returns: plain text transcript.
    """
    # Dev-mode short-circuit for tests/CI/local
    if str(getattr(settings, "AUDIO_DEV_MODE", 0)) == "1" or os.getenv("AUDIO_DEV_MODE") == "1":
        name = Path(path).name
        return f"[DEV] transcript of {name}"

    # Lazy import so importing this module doesn't require the heavy dep
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "faster-whisper is required for audio transcription. "
            "Install with: pip install faster-whisper\n"
            "Also install ffmpeg and ensure it's on PATH (needed for mp3/m4a)."
        ) from e

    # Choose model size (tiny/base/small/medium/large-v2 etc.)
    size = model_size or getattr(settings, "STT_MODEL", "tiny")

    # CPU-friendly config
    model = WhisperModel(size, device="cpu", compute_type="int8")

    # Transcribe
    segments, _info = model.transcribe(
        path,
        vad_filter=vad_filter,
        beam_size=beam_size,
        language=None,   # let it auto-detect
    )
    # Join text pieces
    parts = []
    for s in segments:
        if getattr(s, "text", None):
            t = s.text.strip()
            if t:
                parts.append(t)
    return " ".join(parts).strip()
