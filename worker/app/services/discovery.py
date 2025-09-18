"""Centralized file discovery utilities.

Provides a single implementation of `discover_candidates` used by ingest and
maintenance scripts. Keeps logic intentionally simple and close to the original
inline helpers previously present in `scripts/ingest_dropzone.py`.

Contract:
    discover_candidates(root: Path, kinds_set: set[str] | None, explicit_path: str | None, limit: int) -> list[tuple[Path, str, str]]

Behavior:
    * Walks `root` recursively collecting files.
    * If `explicit_path` is provided and is a file under `root`, only that file
      is returned (still subject to kind filter and ignored extensions rules).
    * `kinds_set` filters by inferred kind when provided (empty/None => no filter).
    * `limit` applies only when > 0; zero/negative => no limit.
    * Returns list of (absolute_path, canonical_posix_relpath, kind) sorted by rel.
    * Uses `canonicalize_relpath` from `worker.app.utils.docids` for rel paths.

Kinds:
    text | pdf | image | audio (mirrors existing logic)

Ignored extensions mirror previous script constant so image/audio code paths can
opt-in separately if desired.

No external dependencies; fails soft (returns empty list) if root invalid.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple, Optional, Set

from worker.app.utils.docids import canonicalize_relpath  # type: ignore

# Image extensions that we DO allow (ingestion may be gated by flags elsewhere)
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}

# Ignored extensions (exclude image types; keep archives/binaries/logs etc.)
IGNORED_EXTS = {
    ".jsonl",
    ".zip",
    ".tar",
    ".gz",
    ".rar",
    ".7z",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
}

_TEXT_EXTS = {".txt", ".md", ".rst", ".json", ".csv"}
_IMAGE_EXTS = IMAGE_EXTS
_AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}


def _infer_kind(fp: Path) -> str:
    ext = fp.suffix.lower()
    if ext in _IMAGE_EXTS:
        return "image"
    if ext in _AUDIO_EXTS:
        return "audio"
    if ext == ".pdf":
        return "pdf"
    # default bucket
    return "text"


def discover_candidates(
    root: Path,
    kinds_set: Optional[Set[str]],
    explicit_path: Optional[Path],
    limit: int,
) -> List[Tuple[Path, str, str]]:
    """Return list of (abs_path, posix_relpath, kind) sorted by rel path.

    Mirrors historical inline implementation; safe for reuse.
    """
    out: List[Tuple[Path, str, str]] = []

    try:
        root = root.resolve()
    except Exception:
        return out

    # Explicit path short circuit
    if explicit_path:
        try:
            fp = Path(explicit_path).resolve()
            if fp.is_file() and str(fp).startswith(str(root)):
                if fp.suffix.lower() in IGNORED_EXTS:
                    return []
                kind = _infer_kind(fp)
                if kinds_set and kinds_set and kind not in kinds_set:
                    return []
                try:
                    rel = canonicalize_relpath(fp, root)
                except Exception:
                    rel = fp.relative_to(root).as_posix()
                out.append((fp, rel, kind))
                return out
        except Exception:
            return out

    # Recursive scan
    for fp in root.rglob("*"):
        if not fp.is_file():
            continue
        ext = fp.suffix.lower()
        if ext in IGNORED_EXTS:
            continue
        kind = _infer_kind(fp)
        if kinds_set and kind not in kinds_set:
            continue
        try:
            rel = canonicalize_relpath(fp, root)
        except Exception:
            try:
                rel = fp.relative_to(root).as_posix()
            except Exception:
                continue
        out.append((fp, rel, kind))

    out.sort(key=lambda t: t[1])
    if limit and limit > 0:
        return out[:limit]
    return out
