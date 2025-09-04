# worker/app/services/chunker.py
from __future__ import annotations

import re
from typing import List

try:
    # Prefer importing the shared settings; fall back gracefully for scripts/tests.
    from worker.app.config import settings
except Exception:  # pragma: no cover - imported context may vary in tests
    from app.config import settings  # type: ignore


_WS_RE = re.compile(r"\s+")


def _normalize(text: str, normalize_ws: bool = True) -> str:
    """
    Normalize text to stabilize hashing & chunk boundaries.

    - Collapse runs of whitespace to a single space
    - Strip leading/trailing whitespace
    """
    if not normalize_ws:
        return text
    if not text:
        return ""
    # Keep it simple & deterministic; no Unicode case folding here.
    return _WS_RE.sub(" ", text).strip()


def _next_cut(text: str, start: int, max_chars: int) -> int:
    """
    Choose a deterministic cut point within [start, start+max_chars].

    Preference order:
    1) Last whitespace before the window end (avoids mid-word cuts)
    2) Hard cut at window end if no whitespace found

    Returns an absolute end index (exclusive).
    """
    end = min(start + max_chars, len(text))
    if end >= len(text):
        return len(text)

    # Look for a whitespace cut point within the window
    window = text[start:end]
    ws_pos = window.rfind(" ")
    if ws_pos > 0:
        return start + ws_pos

    # Fallback: hard cut
    return end


def chunk_text(
    text: str,
    size: int | None = None,
    overlap: int | None = None,
    normalize_whitespace: bool | None = None,
) -> List[str]:
    """
    Chunk text using a stable sliding window with optional whitespace-aware cuts.

    Implementation notes:
    - Step advances by (size - overlap). The last chunk may be shorter.
    - Overlap is clamped to [0, size-1] to guarantee forward progress.
    - Uses _next_cut to prefer whitespace cuts; falls back to fixed-size cuts.
    - Matches unit tests which expect overlapping windows (e.g. for len=200, size=100, overlap=20 -> 3 chunks).

    Returns:
        List of text chunks (str), in order, covering the entire text.
    """
    # --- defaults from config (keeps behavior consistent across the pipeline)
    if size is None:
        size = int(getattr(settings, "CHUNK_SIZE", 800))
    if overlap is None:
        overlap = int(getattr(settings, "CHUNK_OVERLAP", 100))
    if normalize_whitespace is None:
        normalize_whitespace = bool(getattr(settings, "NORMALIZE_WHITESPACE", 1))

    if not text:
        return []

    # Normalize first to stabilize boundaries + content hashes
    text = _normalize(text, normalize_whitespace)

    # Guard rails
    if size <= 0:
        return []

    # Clamp overlap so we always make progress
    overlap = max(0, int(overlap))
    if overlap >= size:
        overlap = max(0, size - 1)

    step = max(1, size - overlap)
    N = len(text)
    chunks: List[str] = []

    start = 0
    prev_start = -1

    while start < N:
        # choose a cut inside the window (whitespace preferred)
        end = _next_cut(text, start, size)
        # safety fallback
        if end <= start:
            end = min(start + size, N)

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= N:
            break

        # desired next start to achieve overlap
        next_start = end - overlap
        if next_start <= start:
            # if overlap too large or no progress, advance by step
            next_start = start + step

        # enforce monotonic growth and not to exceed bounds
        if next_start <= prev_start:
            next_start = prev_start + step if prev_start >= 0 else start + step

        prev_start = start
        start = min(next_start, N)

    return chunks


__all__ = ["chunk_text"]
