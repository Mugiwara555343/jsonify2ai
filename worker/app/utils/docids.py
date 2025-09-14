"""Single-source of truth for document/chunk IDs and canonical relpath.

Centralizes:
  * DEFAULT_NAMESPACE (stable UUID namespace)
  * document_id_for_relpath(relpath) -> UUID
  * chunk_id_for(document_id, idx) -> UUID
  * canonicalize_relpath(path, dropzone_dir) -> canonical POSIX relative path

Canonical path rules:
  * Always relative to provided dropzone root.
  * '/' as separator (POSIX style) regardless of OS.
  * Strip leading './'.
  * Strip historical 'data/dropzone/' prefix if present.
  * Reject paths outside the dropzone (ValueError).

Stdlib-only to avoid circular imports; ensures stable deterministic IDs so
re-ingests replace instead of duplicate.
"""

from __future__ import annotations

from pathlib import Path
import uuid

DEFAULT_NAMESPACE = uuid.UUID("00000000-0000-5000-8000-000000000000")


def canonicalize_relpath(path: str | Path, dropzone_dir: str | Path) -> str:
    """Return canonical POSIX relpath of path within dropzone_dir (ValueError if outside)."""
    p = Path(path).resolve()
    root = Path(dropzone_dir).resolve()
    try:
        rel = p.relative_to(root)
    except ValueError as e:  # outside root
        raise ValueError(f"path outside dropzone: {p} (root={root})") from e
    rel_posix = rel.as_posix()
    if rel_posix.startswith("./"):
        rel_posix = rel_posix[2:]
    if rel_posix.startswith("data/dropzone/"):
        rel_posix = rel_posix[len("data/dropzone/") :]
    return rel_posix


def document_id_for_relpath(relpath: str) -> uuid.UUID:
    return uuid.uuid5(DEFAULT_NAMESPACE, relpath)


def chunk_id_for(document_id: uuid.UUID, idx: int) -> uuid.UUID:
    return uuid.uuid5(document_id, f"chunk:{idx}")


__all__ = [
    "DEFAULT_NAMESPACE",
    "canonicalize_relpath",
    "document_id_for_relpath",
    "chunk_id_for",
]
