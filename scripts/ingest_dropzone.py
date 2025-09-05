#!/usr/bin/env python3
# --- repo-root import bootstrap (works even if PYTHONPATH is unset) ----------
from __future__ import annotations
import sys
import pathlib

REPO_ROOT = (
    pathlib.Path(__file__).resolve().parents[1]
)  # parent of 'scripts/' or 'examples/'
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
# -----------------------------------------------------------------------------
"""
Batch-ingest a 'drop zone' folder into JSON+Qdrant, using the same contract as /process,
plus read-only inspection utilities (--stats, --list).

Usage:
    # Ingest directory (default mode)
    PYTHONPATH=worker python scripts/ingest_dropzone.py --dir data/dropzone --export data/exports/ingest.jsonl

    # Run one pass only (no watch loop)
    PYTHONPATH=worker python scripts/ingest_dropzone.py --once

    # Restrict to specific kinds (comma/space separated)
    PYTHONPATH=worker python scripts/ingest_dropzone.py --kinds pdf,txt,md

    # Read-only stats (optionally filtered)
    PYTHONPATH=worker python scripts/ingest_dropzone.py --stats
    PYTHONPATH=worker python scripts/ingest_dropzone.py --stats --kind pdf
    PYTHONPATH=worker python scripts/ingest_dropzone.py --stats --filter-by path=README.md

    # List matching payloads (no vectors, filter-only)
    PYTHONPATH=worker python scripts/ingest_dropzone.py --list --limit 5 --document-id <uuid>

    # Extras
    PYTHONPATH=worker python scripts/ingest_dropzone.py --strict
    PYTHONPATH=worker python scripts/ingest_dropzone.py --recreate-bad-collection
    PYTHONPATH=worker python scripts/ingest_dropzone.py --replace-existing
    PYTHONPATH=worker python scripts/ingest_dropzone.py --images
"""

import argparse
import hashlib
import importlib.util
import json
import os
import textwrap
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List, Dict, Any, Tuple, Callable, Optional


# worker config + services
from worker.app.config import settings
from worker.app.services.chunker import chunk_text
from worker.app.services.embed_ollama import embed_texts as embed_texts_real
from worker.app.services.image_caption import caption_image  # optional, behind flag

try:
    from worker.app.services.qdrant_client import (
        get_qdrant_client,
        upsert_points,
        delete_by_document_id,
        count as q_count,
        build_filter,
    )
    from worker.app.services.qdrant_minimal import ensure_collection_minimal
except ImportError:
    from worker.app.services.qdrant_client import (
        get_qdrant_client,
        upsert_points,
        delete_by_document_id,
        count as q_count,
        build_filter,
    )

    def ensure_collection_minimal(*a, **kw):
        raise RuntimeError("ensure_collection_minimal not available")


# Canonical collection and schema
CANONICAL_COLLECTION = getattr(
    settings,
    "QDRANT_COLLECTION",
    os.getenv("QDRANT_COLLECTION", "jsonify2ai_chunks_768"),
)
CANONICAL_DIM = int(getattr(settings, "EMBEDDING_DIM", 768))
CANONICAL_MODEL = getattr(
    settings, "EMBEDDINGS_MODEL", os.getenv("EMBEDDINGS_MODEL", "nomic-embed-text")
)
CANONICAL_DISTANCE = "Cosine"

try:
    # used only in --list path
    from qdrant_client import models as qmodels  # type: ignore
except Exception:  # pragma: no cover
    qmodels = None  # type: ignore

# ===================== Parser registry (lazy + optional) =====================


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


# Each factory returns a callable (path: str) -> str
def _csv_factory():
    from worker.app.services.parse_csv import extract_text_from_csv

    return extract_text_from_csv


def _json_factory():
    from worker.app.services.parse_json import extract_text_from_json

    return extract_text_from_json


def _jsonl_factory():
    from worker.app.services.parse_json import extract_text_from_jsonl

    return extract_text_from_jsonl


def _docx_factory():
    if not _module_available("docx"):
        raise RuntimeError("python-docx not installed; pip install python-docx")
    from worker.app.services.parse_docx import extract_text_from_docx

    return extract_text_from_docx


def _pdf_factory():
    if not _module_available("pypdf"):
        raise RuntimeError("pypdf not installed; pip install pypdf")
    from worker.app.services.parse_pdf import extract_text_from_pdf

    return extract_text_from_pdf


def _audio_factory():
    # dev-mode works without faster-whisper; real STT requires it (+ ffmpeg)
    from worker.app.services.parse_audio import transcribe_audio

    return transcribe_audio


AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}

REGISTRY: List[Tuple[set[str], Callable[[], Callable[[str], str]], Optional[str]]] = [
    ({"." + ext for ext in ("csv", "tsv")}, _csv_factory, None),
    ({".json"}, _json_factory, None),
    ({".jsonl"}, _jsonl_factory, None),
    ({".docx"}, _docx_factory, "python-docx"),
    ({".pdf"}, _pdf_factory, "pypdf"),
    (AUDIO_EXTS, _audio_factory, "faster-whisper (only for real STT; dev-mode works)"),
]

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
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",  # handled separately when --images is on
}


class SkipFile(RuntimeError):
    """Non-fatal: skip this file with a message."""


def extract_text_auto(path: str, strict: bool = False) -> str:
    p = Path(path)
    ext = p.suffix.lower()

    if ext in IGNORED_EXTS:
        raise SkipFile(f"ignored extension: {ext}")

    for exts, factory, _need in REGISTRY:
        if ext in exts:
            try:
                handler = factory()
                return handler(str(p))
            except RuntimeError as e:
                if strict:
                    raise
                raise SkipFile(str(e))
            except Exception as e:
                if strict:
                    raise
                raise SkipFile(f"failed to parse {ext}: {e}")

    # Fallback: treat as text
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        if strict:
            raise
        raise SkipFile(f"could not read as text: {e}")


# ============================== Qdrant payload ===============================


@dataclass
class ChunkRecord:
    id: str  # point id (uuid4 for Qdrant)
    document_id: str
    path: str
    kind: str  # "text" | "pdf" | "audio" | "image"
    idx: int
    text: str
    meta: Dict[str, Any]

    def payload(self) -> Dict[str, Any]:
        # match /process schema: flat fields + nested meta
        return {
            "document_id": self.document_id,
            "path": self.path,
            "kind": self.kind,
            "idx": self.idx,
            "text": self.text,
            "meta": self.meta,
        }


# ============================== Embeddings ==================================


def _deterministic_vec(s: str, dim: int) -> List[float]:
    h = hashlib.sha256(s.encode("utf-8")).digest()
    return [((h[i % len(h)]) / 255.0) * 2 - 1 for i in range(dim)]  # [-1, 1]


def embed_texts(texts: List[str]) -> List[List[float]]:
    dim = CANONICAL_DIM
    if (
        str(getattr(settings, "EMBED_DEV_MODE", 0)) == "1"
        or os.getenv("EMBED_DEV_MODE") == "1"
    ):
        return [_deterministic_vec(t, dim) for t in texts]
    vecs = embed_texts_real(texts, model=CANONICAL_MODEL)
    if not vecs or len(vecs[0]) != dim:
        raise RuntimeError(
            f"Embedding dimension mismatch: expected {dim}, got {len(vecs[0]) if vecs else 'none'}"
        )
    return vecs


# ============================== Orchestration ===============================


def _iter_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*"):
        if p.is_file():
            yield p


def _kind_for_ext(ext: str) -> str:
    if ext in {".pdf"}:
        return "pdf"
    if ext in AUDIO_EXTS:
        return "audio"
    return "text"


def _document_id_for_file(fp: Path) -> str:
    # deterministic, rename-proof doc id from file bytes
    data = fp.read_bytes()
    doc_hash = hashlib.sha256(data).hexdigest()
    return str(uuid.uuid5(settings.NAMESPACE_UUID, doc_hash))


def ingest_dir(
    drop_dir: Path,
    export_jsonl: Path | None,
    strict: bool,
    recreate_bad: bool,
    replace_existing: bool,
    do_images: bool = False,
) -> Dict[str, Any]:
    """Core ingest routine."""

    client = get_qdrant_client()

    # Ensure canonical collection exists and matches schema
    try:
        ensure_collection_minimal(
            client=client,
            name=CANONICAL_COLLECTION,
            dim=CANONICAL_DIM,
            distance=CANONICAL_DISTANCE,
            recreate_bad=recreate_bad,
        )
    except Exception as e:
        print(f"[error] Collection schema mismatch: {e}")
        if not recreate_bad:
            print(
                f"Set --recreate-bad-collection to drop and recreate the collection. Expected dim={CANONICAL_DIM}, distance={CANONICAL_DISTANCE}."
            )
            sys.exit(2)

    IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
    if do_images:
        ensure_collection_minimal(
            client=client,
            name=getattr(settings, "QDRANT_COLLECTION_IMAGES", "jsonify2ai_images_768"),
            dim=CANONICAL_DIM,
            distance=CANONICAL_DISTANCE,
            recreate_bad=recreate_bad,
        )

    export_f = None
    if export_jsonl:
        export_jsonl.parent.mkdir(parents=True, exist_ok=True)
        export_f = export_jsonl.open("w", encoding="utf-8")

    total_files = 0
    total_chunks = 0
    skipped: List[str] = []

    batch_size = int(getattr(settings, "QDRANT_UPSERT_BATCH_SIZE", 128))
    seen_points = set()
    points_skipped_dedupe = 0
    for fp in _iter_files(drop_dir):
        ext = fp.suffix.lower()
        rel_path = str(fp).replace("\\", "/")
        # Kind normalization
        if ext == ".pdf":
            kind = "pdf"
        elif ext == ".md":
            kind = "md"
        elif ext == ".txt":
            kind = "text"
        elif ext in IMAGE_EXTS:
            kind = "image"
        elif ext in AUDIO_EXTS:
            kind = "audio"
        else:
            kind = "text"
        total_files += 1

        # Handle images if enabled
        if do_images and ext in IMAGE_EXTS:
            try:
                cap = caption_image(fp)
                vec = embed_texts([cap])[0]
                item = (
                    str(uuid.uuid4()),
                    vec,
                    {
                        "document_id": _document_id_for_file(fp),
                        "path": rel_path,
                        "kind": "image",
                        "idx": 0,
                        "text": cap,
                        "meta": {"source_ext": ext, "caption_model": "blip"},
                    },
                )
                upsert_points(
                    [item],
                    collection_name=getattr(
                        settings, "QDRANT_COLLECTION_IMAGES", "jsonify2ai_images_768"
                    ),
                    client=client,
                    batch_size=1,
                    ensure=False,
                )
                print(f"[images] {fp.name} → '{cap[:64]}…'")
            except Exception as e:
                skipped.append(f"{fp.name}: {e}")
            continue

        # Parse text-like files
        try:
            raw = extract_text_auto(str(fp), strict=strict)
        except SkipFile as e:
            skipped.append(f"{fp.name}: {e}")
            continue

        if not raw.strip():
            skipped.append(f"{fp.name}: empty content")
            continue

        # Determine document id (deterministic) and optional cleanup
        document_id = _document_id_for_file(fp)
        if replace_existing:
            try:
                delete_by_document_id(document_id, client=client)
            except Exception as e:
                skipped.append(f"{fp.name}: delete failed ({e})")
                # continue anyway

        # Chunk using config defaults (normalization inside chunker)
        chunks = chunk_text(
            raw,
            size=int(getattr(settings, "CHUNK_SIZE", 800)),
            overlap=int(getattr(settings, "CHUNK_OVERLAP", 100)),
        )
        if not chunks:
            skipped.append(f"{fp.name}: no chunks")
            continue

        vecs = embed_texts(chunks)

        # Build items with unified payload
        items: List[Tuple[str, List[float], Dict[str, Any]]] = []
        for idx, (text, vec) in enumerate(zip(chunks, vecs)):
            point_key = (document_id, idx)
            if point_key in seen_points:
                points_skipped_dedupe += 1
                continue
            seen_points.add(point_key)
            point_id = str(uuid.uuid4())
            rec = ChunkRecord(
                id=point_id,
                document_id=document_id,
                path=rel_path,
                kind=kind,
                idx=idx,
                text=text,
                meta={"source_ext": ext},
            )
            items.append((rec.id, vec, rec.payload()))
            if export_f:
                export_f.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")

        # Batched upsert through our wrapper
        total_chunks += upsert_points(
            items,
            collection_name=CANONICAL_COLLECTION,
            client=client,
            batch_size=batch_size,
            ensure=False,  # already ensured at the start
        )

    if export_f:
        export_f.close()

    return {
        "files_scanned": total_files,
        "chunks_parsed": total_chunks,
        "points_upserted": total_chunks,
        "points_skipped_dedupe": points_skipped_dedupe,
        "collection": CANONICAL_COLLECTION,
        "skipped": skipped,
    }


# ================================ Inspect ===================================


def _parse_filter_sugar(filter_pairs: List[str] | None) -> Dict[str, str]:
    """Parse --filter-by key=value (repeatable). Only allow supported keys."""
    out: Dict[str, str] = {}
    if not filter_pairs:
        return out
    allowed = {"document_id", "kind", "path"}
    for pair in filter_pairs:
        if "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k in allowed and v:
            out[k] = v
    return out


def do_stats(
    document_id: str | None, kind: str | None, path: str | None
) -> Dict[str, Any]:
    """Return total counts, per-kind counts, and optional filtered count."""
    client = get_qdrant_client()
    total = q_count(collection_name=settings.QDRANT_COLLECTION, client=client)

    # Per-kind counts, optionally scoped by doc/path if provided
    per_kind: Dict[str, int] = {}
    for k in ("text", "pdf", "audio", "image"):
        per_kind[k] = q_count(
            collection_name=settings.QDRANT_COLLECTION,
            client=client,
            query_filter=build_filter(document_id=document_id, path=path, kind=k),
        )

    filtered = None
    if document_id or kind or path:
        filtered = q_count(
            collection_name=settings.QDRANT_COLLECTION,
            client=client,
            query_filter=build_filter(document_id=document_id, kind=kind, path=path),
        )

    return {
        "ok": True,
        "collection": settings.QDRANT_COLLECTION,
        "total": total,
        "per_kind": per_kind,
        "filtered": filtered,
        "filters": {"document_id": document_id, "kind": kind, "path": path},
    }


def do_list(
    document_id: str | None, kind: str | None, path: str | None, limit: int = 10
) -> Dict[str, Any]:
    """List up to N payloads matching filters (no vectors, no scores)."""
    client = get_qdrant_client()

    if qmodels is None:
        return {"ok": False, "error": "qdrant-client not available for scroll"}

    flt = build_filter(document_id=document_id, kind=kind, path=path)
    points, _next = client.scroll(
        collection_name=settings.QDRANT_COLLECTION,
        scroll_filter=flt,  # type: ignore[arg-type]
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )

    rows: List[Dict[str, Any]] = []
    for p in points:
        payload = getattr(p, "payload", {}) or {}
        rows.append(
            {
                "id": str(getattr(p, "id", "")),
                "document_id": payload.get("document_id"),
                "path": payload.get("path"),
                "kind": payload.get("kind"),
                "idx": payload.get("idx"),
                "text": textwrap.shorten(
                    (payload.get("text") or "").strip(), width=160, placeholder="…"
                ),
            }
        )

    return {
        "ok": True,
        "collection": settings.QDRANT_COLLECTION,
        "limit": limit,
        "filters": {"document_id": document_id, "kind": kind, "path": path},
        "rows": rows,
    }


# ================================== CLI =====================================


def main():
    p = argparse.ArgumentParser(
        description="Ingest a drop-zone folder into Qdrant + JSONL export, with stats/list utilities"
    )
    p.add_argument("--dir", default="data/dropzone")
    p.add_argument(
        "--export",
        default=os.getenv(
            "EXPORT_JSONL",
            getattr(settings, "EXPORT_JSONL", "data/exports/ingest.jsonl"),
        ),
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="fail on missing optional deps instead of skipping",
    )
    p.add_argument(
        "--recreate-bad-collection",
        action="store_true",
        help="If existing collection has incorrect vector dim, drop and recreate it.",
    )
    p.add_argument(
        "--replace-existing",
        action="store_true",
        help="Delete old points for a document_id before upserting (idempotent re-ingest).",
    )
    p.add_argument(
        "--images",
        action="store_true",
        help="Also caption + index images in the images collection.",
    )
    p.add_argument(
        "--once",
        action="store_true",
        help="Run one pass over the dropzone then exit (no watch loop).",
    )
    p.add_argument(
        "--kinds",
        type=str,
        default=None,
        help="Comma/space list of kinds to include (e.g., pdf,txt,md).",
    )

    p.add_argument(
        "--debug",
        action="store_true",
        help="Print resolved env and collection info for debugging.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Run selection/embedding logic but do not upsert. Print summary JSON and exit.",
    )

    # Read-only inspection modes (mutually exclusive)
    mx = p.add_mutually_exclusive_group()
    mx.add_argument(
        "--stats",
        action="store_true",
        help="Print total/per-kind counts (optionally filtered)",
    )
    mx.add_argument(
        "--list-files",
        action="store_true",
        help="List filesystem candidates to ingest (respects --dir, --kinds, --limit)",
    )
    mx.add_argument(
        "--list-collection",
        action="store_true",
        help="List Qdrant rows already stored (respects --limit)",
    )
    mx.add_argument("--list", action="store_true", help="Alias for --list-files")
    p.add_argument(
        "--limit", type=int, default=10, help="Max rows for --list (default 10)"
    )

    # Filters (work with --stats/--list; ignored during ingest)
    p.add_argument("--document-id", type=str, default=None)
    p.add_argument("--kind", type=str, default=None)
    p.add_argument("--path", type=str, default=None)
    p.add_argument(
        "--filter-by",
        action="append",
        help="Sugar for filters, repeatable (key=value). Allowed keys: document_id, kind, path",


    # Read-only inspection modes (mutually exclusive)
    mx = p.add_mutually_exclusive_group()
    mx.add_argument(
        "--stats",
        action="store_true",
        help="Print total/per-kind counts (optionally filtered)",
    )
    mx.add_argument(
        "--list-files",
        action="store_true",
        help="List filesystem candidates to ingest (respects --dir, --kinds, --limit)",
    )
    mx.add_argument(
        "--list-collection",
        action="store_true",
        help="List Qdrant rows already stored (respects --limit)",
    )
    mx.add_argument("--list", action="store_true", help="Alias for --list-files")
    p.add_argument(
        "--limit", type=int, default=10, help="Max rows for --list (default 10)"
    )

    # Filters (work with --stats/--list; ignored during ingest)
    p.add_argument("--document-id", type=str, default=None)
    p.add_argument("--kind", type=str, default=None)
    p.add_argument("--path", type=str, default=None)
    p.add_argument(
        "--filter-by",
        action="append",
        help="Sugar for filters, repeatable (key=value). Allowed keys: document_id, kind, path",
    )

    args = p.parse_args()

    # Merge sugar filters into explicit flags (explicit flags win)
    sugar = _parse_filter_sugar(args.filter_by)
    document_id = args.document_id or sugar.get("document_id")
    kind = args.kind or sugar.get("kind")
    path = args.path or sugar.get("path")

    # Parse --kinds and combine with --kind
    kinds_set = set()
    if args.kinds:
        for k in args.kinds.replace(",", " ").split():
            if k:
                kinds_set.add(k.strip())
    if kind:
        kinds_set.add(kind)
    kinds_list = list(kinds_set) if kinds_set else None

    # Candidate selection logic
    drop = Path(args.dir)
    candidate_files = []
    # If --path is provided and exists, always include it
    explicit_path = None
    if args.path:
        explicit_path = Path(args.path)
        if explicit_path.exists():
            rel_path = str(explicit_path).replace("\\", "/")
            ext = explicit_path.suffix.lower()
            if ext == ".pdf":
                kind_norm = "pdf"
            elif ext in {".md", ".txt"}:
                kind_norm = "text"
            elif ext in {".jpg", ".jpeg", ".png", ".webp"}:
                kind_norm = "image"
            elif ext in AUDIO_EXTS:
                kind_norm = "audio"
            else:
                kind_norm = "text"
            candidate_files.append((explicit_path, rel_path, kind_norm))
    # Add other files from dropzone, respecting --kinds
    for p in _iter_files(drop):
        rel_path = str(p).replace("\\", "/")
        ext = p.suffix.lower()
        if ext == ".pdf":
            kind_norm = "pdf"
        elif ext in {".md", ".txt"}:
            kind_norm = "text"
        elif ext in {".jpg", ".jpeg", ".png", ".webp"}:
            kind_norm = "image"
        elif ext in AUDIO_EXTS:
            kind_norm = "audio"
        else:
            kind_norm = "text"
        # If --path was provided, skip duplicate
        if explicit_path and p.resolve() == explicit_path.resolve():
            continue
        # Filter by kinds if set
        if kinds_list and kind_norm not in kinds_list:
            continue
        candidate_files.append((p, rel_path, kind_norm))
        if len(candidate_files) >= args.limit:
            break

    # --list-files and --list output
    if args.list_files or args.list:
        files_out = [
            {"path": rel_path, "kind": kind_norm}
            for _, rel_path, kind_norm in candidate_files
        ]
        print(json.dumps({"files": files_out, "count": len(files_out)}))
        return

    if args.list_collection:
        # List Qdrant collection rows
        client = get_qdrant_client()
        points, _ = client.scroll(
            collection_name=CANONICAL_COLLECTION,
            scroll_filter=None,
            limit=args.limit,
            with_payload=True,
            with_vectors=False,
        )
        rows = []
        for p in points:
            payload = getattr(p, "payload", {}) or {}
            rel_path = (payload.get("path") or "").replace("\\", "/")
            kind = payload.get("kind") or "text"
            rows.append(
                {
                    "id": str(getattr(p, "id", "")),
                    "document_id": payload.get("document_id"),
                    "path": rel_path,
                    "kind": kind,
                    "idx": payload.get("idx"),
                }
            )
        print(json.dumps({"rows": rows, "count": len(rows)}))
        return

    # Ingest execution path
    recreate_bad = (
        args.recreate_bad_collection or os.getenv("QDRANT_RECREATE_BAD", "0") == "1"

    )
    import time

    args = p.parse_args()

    # Merge sugar filters into explicit flags (explicit flags win)
    sugar = _parse_filter_sugar(args.filter_by)
    document_id = args.document_id or sugar.get("document_id")
    kind = args.kind or sugar.get("kind")
    path = args.path or sugar.get("path")

    # Parse --kinds and combine with --kind
    kinds_set = set()
    if args.kinds:
        for k in args.kinds.replace(",", " ").split():
            if k:
                kinds_set.add(k.strip())
    if kind:
        kinds_set.add(kind)
    kinds_list = list(kinds_set) if kinds_set else None

    # Candidate selection logic
    drop = Path(args.dir)
    candidate_files = []
    # If --path is provided and exists, always include it
    explicit_path = None
    if args.path:
        explicit_path = Path(args.path)
        if explicit_path.exists():
            rel_path = str(explicit_path).replace("\\", "/")
            ext = explicit_path.suffix.lower()
            if ext == ".pdf":
                kind_norm = "pdf"
            elif ext in {".md", ".txt"}:
                kind_norm = "text"
            elif ext in {".jpg", ".jpeg", ".png", ".webp"}:
                kind_norm = "image"
            elif ext in AUDIO_EXTS:
                kind_norm = "audio"
            else:
                kind_norm = "text"
            candidate_files.append((explicit_path, rel_path, kind_norm))
    # Add other files from dropzone, respecting --kinds
    for p in _iter_files(drop):
        rel_path = str(p).replace("\\", "/")
        ext = p.suffix.lower()
        if ext == ".pdf":
            kind_norm = "pdf"
        elif ext in {".md", ".txt"}:
            kind_norm = "text"
        elif ext in {".jpg", ".jpeg", ".png", ".webp"}:
            kind_norm = "image"
        elif ext in AUDIO_EXTS:
            kind_norm = "audio"
        else:
            kind_norm = "text"
        # If --path was provided, skip duplicate
        if explicit_path and p.resolve() == explicit_path.resolve():
            continue
        # Filter by kinds if set
        if kinds_list and kind_norm not in kinds_list:
            continue
        candidate_files.append((p, rel_path, kind_norm))
        if len(candidate_files) >= args.limit:
            break

    # --debug: print resolved env and collection info
    if args.debug or args.dry_run:
        qdrant_url = os.getenv(
            "QDRANT_URL", getattr(settings, "QDRANT_URL", "http://localhost:6333")
        )
        qdrant_collection = getattr(
            settings,
            "QDRANT_COLLECTION",
            os.getenv("QDRANT_COLLECTION", "jsonify2ai_chunks_768"),
        )
        embeddings_model = getattr(
            settings,
            "EMBEDDINGS_MODEL",
            os.getenv("EMBEDDINGS_MODEL", "nomic-embed-text"),
        )
        embedding_dim = int(getattr(settings, "EMBEDDING_DIM", 768))
        print(
            f"[debug] QDRANT_URL={qdrant_url} QDRANT_COLLECTION={qdrant_collection} EMBEDDINGS_MODEL={embeddings_model} EMBEDDING_DIM={embedding_dim}"
        )
        print(
            f"[debug] candidate_files={len(candidate_files)} per_kind={{'text': {sum(1 for _,_,k in candidate_files if k=='text')}, 'pdf': {sum(1 for _,_,k in candidate_files if k=='pdf')}, 'image': {sum(1 for _,_,k in candidate_files if k=='image')}, 'audio': {sum(1 for _,_,k in candidate_files if k=='audio')}}}"
        )
        # Try to get Qdrant collection info
        try:
            client = get_qdrant_client()
            info = client.get_collection(qdrant_collection)
            points_count = info.get("points_count", "?")
            indexed_vectors_count = info.get("indexed_vectors_count", "?")
            print(
                f"[debug] collection_info points_count={points_count} indexed_vectors_count={indexed_vectors_count}"
            )
        except Exception:
            print("[debug] collection_info unavailable")

    # --dry-run: print summary and exit
    if args.dry_run:
        per_kind = {"text": 0, "pdf": 0, "image": 0, "audio": 0}
        for _, _, k in candidate_files:
            if k in per_kind:
                per_kind[k] += 1
        summary = {
            "ok": True,
            "files_scanned": len(candidate_files),
            "chunks_parsed": 0,  # Not chunked in dry-run
            "per_kind": per_kind,
            "collection": getattr(
                settings,
                "QDRANT_COLLECTION",
                os.getenv("QDRANT_COLLECTION", "jsonify2ai_chunks_768"),
            ),
            "embed_dim": int(getattr(settings, "EMBEDDING_DIM", 768)),
        }
        print(json.dumps(summary, indent=2))
        sys.exit(0)

    # --list-files and --list output
    if args.list_files or args.list:
        files_out = [
            {"path": rel_path, "kind": kind_norm}
            for _, rel_path, kind_norm in candidate_files
        ]
        print(json.dumps({"files": files_out, "count": len(files_out)}))
        return

    if args.list_collection:
        # List Qdrant collection rows
        client = get_qdrant_client()
        points, _ = client.scroll(
            collection_name=CANONICAL_COLLECTION,
            scroll_filter=None,
            limit=args.limit,
            with_payload=True,
            with_vectors=False,
        )
        rows = []
        for p in points:
            payload = getattr(p, "payload", {}) or {}
            rel_path = (payload.get("path") or "").replace("\\", "/")
            kind = payload.get("kind") or "text"
            rows.append(
                {
                    "id": str(getattr(p, "id", "")),
                    "document_id": payload.get("document_id"),
                    "path": rel_path,
                    "kind": kind,
                    "idx": payload.get("idx"),
                }
            )
        print(json.dumps({"rows": rows, "count": len(rows)}))
        return

    # Ingest execution path
    recreate_bad = (
        args.recreate_bad_collection or os.getenv("QDRANT_RECREATE_BAD", "0") == "1"
    )
    import time

    t0 = time.time()
    total_files = 0
    total_chunks = 0
    points_upserted = 0
    points_skipped_dedupe = 0
    per_kind = {"text": 0, "pdf": 0, "image": 0, "audio": 0}
    seen_points = set()
    client = get_qdrant_client()
    batch_size = int(getattr(settings, "QDRANT_UPSERT_BATCH_SIZE", 128))
    for p, rel_path, kind_norm in candidate_files:
        total_files += 1
        parser_name = None
        if kind_norm == "pdf":
            parser_name = "pdf"
        elif kind_norm == "image":
            parser_name = "image"
        elif kind_norm == "audio":
            parser_name = "audio"
        else:
            parser_name = "text"
        if args.stats:
            print(
                json.dumps(
                    {
                        "trace": "candidate",
                        "path": rel_path,
                        "kind": kind_norm,
                        "parser": parser_name,
                    },
                    ensure_ascii=False,
                )
            )
        # Handle images
        if kind_norm == "image" and args.images:
            try:
                cap = caption_image(p)
                vec = embed_texts([cap])[0]
                item = (
                    str(uuid.uuid4()),
                    vec,
                    {
                        "document_id": _document_id_for_file(p),
                        "path": rel_path,
                        "kind": "image",
                        "idx": 0,
                        "text": cap,
                        "meta": {
                            "source_ext": p.suffix.lower(),
                            "caption_model": "blip",
                        },
                    },
                )
                upsert_points(
                    [item],
                    collection_name=getattr(
                        settings, "QDRANT_COLLECTION_IMAGES", "jsonify2ai_images_768"
                    ),
                    client=client,
                    batch_size=1,
                    ensure=False,
                )
                points_upserted += 1
                per_kind["image"] += 1
            except Exception:
                continue
            continue
        # Parse text-like files
        try:
            raw = extract_text_auto(str(p), strict=args.strict)
        except SkipFile:
            continue
        if not raw.strip():
            continue
        document_id = _document_id_for_file(p)
        # Chunk using config defaults
        chunks = chunk_text(
            raw,
            size=int(getattr(settings, "CHUNK_SIZE", 800)),
            overlap=int(getattr(settings, "CHUNK_OVERLAP", 100)),
        )

    t0 = time.time()
    total_files = 0
    total_chunks = 0
    points_upserted = 0
    points_skipped_dedupe = 0
    per_kind = {"text": 0, "pdf": 0, "image": 0, "audio": 0}
    seen_points = set()
    client = get_qdrant_client()
    batch_size = int(getattr(settings, "QDRANT_UPSERT_BATCH_SIZE", 128))
    for p, rel_path, kind_norm in candidate_files:
        total_files += 1
        parser_name = None
        if kind_norm == "pdf":
            parser_name = "pdf"
        elif kind_norm == "image":
            parser_name = "image"
        elif kind_norm == "audio":
            parser_name = "audio"
        else:
            parser_name = "text"
        if args.stats:
            print(
                json.dumps(
                    {
                        "trace": "candidate",
                        "path": rel_path,
                        "kind": kind_norm,
                        "parser": parser_name,
                    },
                    ensure_ascii=False,
                )
            )
        # Handle images
        if kind_norm == "image" and args.images:
            try:
                cap = caption_image(p)
                vec = embed_texts([cap])[0]
                item = (
                    str(uuid.uuid4()),
                    vec,
                    {
                        "document_id": _document_id_for_file(p),
                        "path": rel_path,
                        "kind": "image",
                        "idx": 0,
                        "text": cap,
                        "meta": {
                            "source_ext": p.suffix.lower(),
                            "caption_model": "blip",
                        },
                    },
                )
                upsert_points(
                    [item],
                    collection_name=getattr(
                        settings, "QDRANT_COLLECTION_IMAGES", "jsonify2ai_images_768"
                    ),
                    client=client,
                    batch_size=1,
                    ensure=False,
                )
                points_upserted += 1
                per_kind["image"] += 1
            except Exception:
                continue
            continue
        # Parse text-like files
        try:
            raw = extract_text_auto(str(p), strict=args.strict)
        except SkipFile:
            continue
        if not raw.strip():
            continue
        document_id = _document_id_for_file(p)
        # Chunk using config defaults
        chunks = chunk_text(
            raw,
            size=int(getattr(settings, "CHUNK_SIZE", 800)),
            overlap=int(getattr(settings, "CHUNK_OVERLAP", 100)),
        )

        if not chunks:
            continue
        vecs = embed_texts(chunks)
        items: List[Tuple[str, List[float], Dict[str, Any]]] = []
        for idx, (text, vec) in enumerate(zip(chunks, vecs)):
            point_key = (document_id, idx)
            if point_key in seen_points:
                points_skipped_dedupe += 1
                if not args.replace_existing:
                    continue
            seen_points.add(point_key)
            point_id = str(uuid.uuid4())
            rec = ChunkRecord(
                id=point_id,
                document_id=document_id,
                path=rel_path,
                kind=kind_norm,
                idx=idx,
                text=text,
                meta={"source_ext": p.suffix.lower()},
            )
            items.append((rec.id, vec, rec.payload()))
            total_chunks += 1
            per_kind[kind_norm] = per_kind.get(kind_norm, 0) + 1
        if items:
            upsert_points(
                items,
                collection_name=CANONICAL_COLLECTION,
                client=client,
                batch_size=batch_size,
                ensure=False,
            )
            points_upserted += len(items)
    elapsed = time.time() - t0
    stats = {
        "ok": True,
        "collection": CANONICAL_COLLECTION,
        "files_scanned": total_files,
        "chunks_parsed": total_chunks,
        "points_upserted": points_upserted,
        "points_skipped_dedupe": points_skipped_dedupe,
        "elapsed_seconds": elapsed,
        "per_kind": per_kind,
    }
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
