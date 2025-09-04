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

    Args:
        text: Input text to chunk.
        size: Max chunk size in characters (defaults to settings.CHUNK_SIZE).
        overlap: Overlap in characters (defaults to settings.CHUNK_OVERLAP).
        normalize_whitespace: Collapse whitespace before chunking
                              (defaults to bool(settings.NORMALIZE_WHITESPACE)).

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
    # Ensure we always make progress even if overlap >= size (bad config or override)
    effective_step = max(1, size - max(0, overlap))

    if len(text) <= size:
        return [text]

    chunks: List[str] = []
    start = 0
    N = len(text)

    while start < N:
        # Choose a whitespace-friendly cut where possible
        end = _next_cut(text, start, size)
        # Safety: ensure forward progress even if _next_cut returns start
        if end <= start:
            end = min(N, start + size)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= N:
            break

        # New start accounts for desired overlap; ensure monotonic advance
        start = max(0, end - overlap)
        if start <= 0:
            # if we somehow wrap, jump forward by effective_step
            start = min(N, start + effective_step)
        # Last resort: monotonic advance guarantee
        if start <= end - size + 1:
            start = end - size + 1
        if start <= end - effective_step:
            start = end - overlap
        if start <= end - 1:
            start = end - overlap
        if start <= end - overlap:
            # final clamp to guarantee progress
            start = end - overlap
        if start <= end - overlap:
            # if overlap is too large, step by effective_step
            start = end - overlap if (end - overlap) > start else start + effective_step

    return chunks
