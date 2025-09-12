#!/usr/bin/env python3
"""
ingest_dropzone.py

Batch-ingest a "drop zone" folder into Qdrant using the unified chunk schema.
Also provides read-only utilities: --stats, --list-files, --list, --list-collection.

Notes (to prevent regressions):
- Imports: stdlib → repo-root bootstrap → local imports with # noqa: E402.
- Idempotence: deterministic document_id (from file bytes); --replace-existing re-writes.
- Dev mode: EMBED_DEV_MODE=1 returns deterministic fake vectors (keeps pipeline alive).
"""

from __future__ import annotations

# ─── stdlib ───────────────────────────────────────────────────────────────────
import argparse
import hashlib
import importlib.util
import inspect
import json
import os
import sys
import textwrap
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
import pathlib

# === BEGIN discovery helpers ===

KIND_MAP = {
    ".txt": "text",
    ".md": "text",
    ".rst": "text",
    ".json": "text",
    ".csv": "text",
    ".pdf": "pdf",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".wav": "audio",
    ".mp3": "audio",
    ".m4a": "audio",
}


def _infer_kind(fp: Path) -> str:
    return KIND_MAP.get(fp.suffix.lower(), "text")


def _posix_rel(fp: Path, root: Path) -> str:
    return fp.relative_to(root).as_posix()


def discover_candidates(
    root: Path, kinds_set: set[str], explicit_path: Optional[Path], limit: int
) -> List[Tuple[Path, str, str]]:
    """
    Return [(abs_path, posix_rel_path, kind)] sorted by rel path.
    Applies kinds filter, explicit file path, then limit (0 = no limit).
    """
    out: List[Tuple[Path, str, str]] = []
    root = root.resolve()
    if explicit_path:
        fp = Path(explicit_path).resolve()
        if fp.is_file() and str(fp).startswith(str(root)):
            kind = _infer_kind(fp)
            if not kinds_set or kind in kinds_set:
                out.append((fp, _posix_rel(fp, root), kind))
    else:
        for fp in root.rglob("*"):
            if not fp.is_file():
                continue
            kind = _infer_kind(fp)
            if kinds_set and kind not in kinds_set:
                continue
            out.append((fp, _posix_rel(fp, root), kind))
    out.sort(key=lambda t: t[1])
    return out[:limit] if limit and limit > 0 else out


# === END discovery helpers ===

# === BEGIN id helpers ===

# Use the top-level 'uuid' module (no mid-file imports).
DEFAULT_NAMESPACE = uuid.UUID("00000000-0000-5000-8000-000000000000")


def _ns() -> uuid.UUID:
    try:
        from worker.app import settings  # optional

        return getattr(settings, "NAMESPACE_UUID", DEFAULT_NAMESPACE)
    except Exception:
        return DEFAULT_NAMESPACE


def document_id_for_relpath(relpath: str) -> str:
    return str(uuid.uuid5(_ns(), relpath))


def chunk_id_for(document_id: str, idx: int) -> str:
    return str(uuid.uuid5(uuid.UUID(document_id), f"chunk:{idx}"))


def content_sig_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# === END id helpers ===

# ─── repo-root bootstrap (must precede local imports) ─────────────────────────
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ─── third-party imports ──────────────────────────────────────────────────────────
try:
    from qdrant_client import models as qmodels  # type: ignore
except Exception:  # pragma: no cover
    qmodels = None  # type: ignore

# ─── local imports (after bootstrap; silenced for E402) ──────────────────────
from worker.app.config import settings  # noqa: E402
from worker.app.services.chunker import chunk_text  # noqa: E402
from worker.app.services.embed_ollama import (  # noqa: E402
    embed_texts as embed_texts_real,
)
from worker.app.services.image_caption import caption_image  # noqa: E402

try:
    from worker.app.services.qdrant_client import (  # noqa: E402
        get_qdrant_client,
        upsert_points,
        delete_by_document_id,
        count as q_count,
        build_filter,
    )
    from worker.app.services.qdrant_minimal import (  # noqa: E402
        ensure_collection_minimal,
    )
except ImportError:
    from worker.app.services.qdrant_client import (  # noqa: E402
        get_qdrant_client,
        upsert_points,
        delete_by_document_id,
        count as q_count,
        build_filter,
    )

    def ensure_collection_minimal(*a, **kw):  # type: ignore
        raise RuntimeError("ensure_collection_minimal not available")


# ─── config/constants ─────────────────────────────────────────────────────────
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

AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
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
    ".webp",
    ".png",
    ".jpg",
    ".jpeg",
}  # images handled via --images


# ─── parser registry (ext → factory) ──────────────────────────────────────────
def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _csv_factory():
    from worker.app.services.parse_csv import extract_text_from_csv  # noqa: E402

    return extract_text_from_csv


def _json_factory():
    from worker.app.services.parse_json import extract_text_from_json  # noqa: E402

    return extract_text_from_json


def _jsonl_factory():
    from worker.app.services.parse_json import extract_text_from_jsonl  # noqa: E402

    return extract_text_from_jsonl


def _docx_factory():
    if not _module_available("docx"):
        raise RuntimeError("python-docx not installed; pip install python-docx")
    from worker.app.services.parse_docx import extract_text_from_docx  # noqa: E402

    return extract_text_from_docx


def _pdf_factory():
    if not _module_available("pypdf"):
        raise RuntimeError("pypdf not installed; pip install pypdf")
    from worker.app.services.parse_pdf import extract_text_from_pdf  # noqa: E402

    return extract_text_from_pdf


def _audio_factory():
    from worker.app.services.parse_audio import transcribe_audio  # noqa: E402

    return transcribe_audio


REGISTRY: List[Tuple[set[str], Callable[[], Callable[[str], str]], Optional[str]]] = [
    ({"." + ext for ext in ("csv", "tsv")}, _csv_factory, None),
    ({".json"}, _json_factory, None),
    ({".jsonl"}, _jsonl_factory, None),
    ({".docx"}, _docx_factory, "python-docx"),
    ({".pdf"}, _pdf_factory, "pypdf"),
    (AUDIO_EXTS, _audio_factory, "faster-whisper (only for real STT; dev-mode works)"),
]


class SkipFile(RuntimeError):
    """Non-fatal: parsing skipped with a reason."""


def extract_text_auto(path: str, strict: bool = False) -> str:
    """Detect by extension and route to the correct parser; fallback to raw text."""
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

    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        if strict:
            raise
        raise SkipFile(f"could not read as text: {e}")


# ─── schema payload ───────────────────────────────────────────────────────────
@dataclass
class ChunkRecord:
    id: str
    document_id: str
    path: str
    kind: str
    idx: int
    text: str
    meta: Dict[str, Any]

    def payload(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "path": self.path,
            "kind": self.kind,
            "idx": self.idx,
            "text": self.text,
            "meta": self.meta,
        }


# ─── embeddings (dev-safe) ───────────────────────────────────────────────────
def _deterministic_vec(s: str, dim: int) -> List[float]:
    h = hashlib.sha256(s.encode("utf-8")).digest()
    return [((h[i % len(h)]) / 255.0) * 2 - 1 for i in range(dim)]


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


# ─── utils ───────────────────────────────────────────────────────────────────
def _iter_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*"):
        if p.is_file():
            yield p


def _document_id_for_file(fp: Path) -> str:
    data = fp.read_bytes()
    doc_hash = hashlib.sha256(data).hexdigest()
    return str(uuid.uuid5(settings.NAMESPACE_UUID, doc_hash))


# ─── qdrant ensure (signature-adaptive) ──────────────────────────────────────
def qdrant_preflight(client) -> None:
    """Fail fast if Qdrant is unreachable/misconfigured (clear message)."""
    try:
        client.get_collections()
    except Exception as e:
        raise SystemExit(f"[qdrant] unreachable or misconfigured: {e}")


def ensure_collection_compat(
    client, *, name: str, dim: int, distance: str, recreate_bad: bool
) -> None:
    """
    Call ensure_collection_minimal with *only* the parameters it supports.
    Handles:
      - keyword vs positional
      - missing params (e.g., no 'distance' or no 'dim')
      - functions that do not accept 'client'
    """
    func = ensure_collection_minimal
    sig = inspect.signature(func)

    # Map available values
    values = {
        "client": client,
        "name": name,
        "collection": name,  # some variants use 'collection'
        "collection_name": name,
        "dim": dim,
        "vector_size": dim,  # alt name in some helpers
        "distance": distance,
        "recreate_bad": recreate_bad,
        "recreate": recreate_bad,  # alt flag
    }

    # Build call respecting declared parameter order/kind
    args = []
    kwargs = {}
    for pname, p in sig.parameters.items():
        if pname in values:
            val = values[pname]
        else:
            # Unsupported/unrecognized param; skip by leaving default
            continue

        if (
            p.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
            and pname != "client"
        ):
            # Prefer positional for non-client params to satisfy older 2-arg helpers
            args.append(val)
        elif p.kind is inspect.Parameter.POSITIONAL_ONLY and pname == "client":
            args.insert(0, val)  # client first if required positionally
        else:
            kwargs[pname] = val

    try:
        func(*args, **kwargs)
    except TypeError as e:
        # Last resort: try the minimal shapes in descending richness
        tried = False
        for shape in (
            ("client", "name", "dim", "distance", "recreate_bad"),
            ("client", "name", "dim", "distance"),
            ("client", "name"),
            ("name", "dim", "distance", "recreate_bad"),
            ("name", "dim", "distance"),
            ("name",),
        ):
            try:
                call_args = [values[k] for k in shape if k in values]
                func(*call_args)
                tried = True
                break
            except Exception:
                continue
        if not tried:
            raise RuntimeError(
                f"ensure_collection_minimal incompatible signature: {e}"
            ) from e


# ─── orchestration ───────────────────────────────────────────────────────────
def ingest_dir(
    drop_dir: Path,
    export_jsonl: Path | None,
    strict: bool,
    recreate_bad: bool,
    replace_existing: bool,
    do_images: bool = False,
    limit_files: int = 0,
    candidates: Optional[List[Tuple[Path, str, str]]] = None,
) -> Dict[str, Any]:
    """
    Ingest all supported files:
      1) preflight Qdrant → 2) ensure collection(s) → 3) parse→chunk→embed→upsert
    """
    client = get_qdrant_client()
    qdrant_preflight(client)

    # Ensure canonical collection (via adaptive shim)
    ensure_collection_compat(
        client,
        name=CANONICAL_COLLECTION,
        dim=CANONICAL_DIM,
        distance=CANONICAL_DISTANCE,
        recreate_bad=recreate_bad,
    )

    # Optional image collection
    if do_images:
        ensure_collection_compat(
            client,
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
    seen_points: set[Tuple[str, int]] = set()
    points_skipped_dedupe = 0
    batch_size = int(getattr(settings, "QDRANT_UPSERT_BATCH_SIZE", 128))
    per_kind = {"text": 0, "pdf": 0, "image": 0, "audio": 0}

    # Use candidates if provided, otherwise scan drop_dir
    file_iter = candidates or discover_candidates(drop_dir, set(), None, limit_files)

    for fp, rel_path, kind in file_iter:
        ext = fp.suffix.lower()
        bytes_ = fp.read_bytes()
        content_sig = content_sig_bytes(bytes_)

        # Always use stable document ID based on path
        document_id = document_id_for_relpath(rel_path)

        total_files += 1
        per_kind[kind] += 1

        # images path (optional)
        if do_images and kind == "image":
            try:
                cap = caption_image(fp)
                vec = embed_texts([cap])[0]
                item = (
                    chunk_id_for(document_id, 0),
                    vec,
                    {
                        "document_id": document_id,
                        "path": rel_path,
                        "kind": "image",
                        "idx": 0,
                        "text": cap,
                        "meta": {
                            "source_ext": ext,
                            "caption_model": "blip",
                            "content_sig": content_sig,
                            "bytes": len(bytes_),
                            "mtime": fp.stat().st_mtime,
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
            except Exception as e:
                skipped.append(f"{fp.name}: image path failed ({e})")
            continue

        # parse text-like
        try:
            raw = extract_text_auto(str(fp), strict=strict)
        except SkipFile as e:
            skipped.append(f"{fp.name}: {e}")
            continue

        if not raw.strip():
            skipped.append(f"{fp.name}: empty content")
            continue

        # write policy (now with path-stable document_id)
        if replace_existing:
            try:
                delete_by_document_id(document_id, client=client)
            except Exception as e:
                skipped.append(f"{fp.name}: delete failed ({e})")

        # chunk & embed
        chunks = chunk_text(
            raw,
            size=int(getattr(settings, "CHUNK_SIZE", 800)),
            overlap=int(getattr(settings, "CHUNK_OVERLAP", 100)),
        )
        if not chunks:
            skipped.append(f"{fp.name}: no chunks")
            continue

        vecs = embed_texts(chunks)

        # build items
        items: List[Tuple[str, List[float], Dict[str, Any]]] = []
        for idx, (text, vec) in enumerate(zip(chunks, vecs)):
            key = (document_id, idx)
            if key in seen_points:
                points_skipped_dedupe += 1
                continue
            seen_points.add(key)
            rec = ChunkRecord(
                id=chunk_id_for(document_id, idx),
                document_id=document_id,
                path=rel_path,
                kind=kind,
                idx=idx,
                text=text,
                meta={
                    "source_ext": ext,
                    "content_sig": content_sig,
                    "bytes": len(bytes_),
                    "mtime": fp.stat().st_mtime,
                },
            )
            items.append((rec.id, vec, rec.payload()))
            if export_f:
                export_f.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")

        if items:
            total_chunks += upsert_points(
                items,
                collection_name=CANONICAL_COLLECTION,
                client=client,
                batch_size=batch_size,
                ensure=False,
            )

    if export_f:
        export_f.close()

    return {
        "ok": True,
        "files_scanned": total_files,
        "chunks_parsed": total_chunks,
        "points_upserted": total_chunks,
        "points_skipped_dedupe": points_skipped_dedupe,
        "per_kind": per_kind,
        "collection": CANONICAL_COLLECTION,
        "embed_dim": CANONICAL_DIM,
        "skipped": skipped,
    }


# ─── read-only ops ───────────────────────────────────────────────────────────
def _parse_filter_sugar(pairs: List[str] | None) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not pairs:
        return out
    allowed = {"document_id", "kind", "path"}
    for pair in pairs:
        if "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        k, v = k.strip(), v.strip()
        if k in allowed and v:
            out[k] = v
    return out


def do_stats(
    document_id: str | None, kind: str | None, path: str | None
) -> Dict[str, Any]:
    client = get_qdrant_client()
    total = q_count(collection_name=CANONICAL_COLLECTION, client=client)
    per_kind: Dict[str, int] = {}
    for k in ("text", "pdf", "audio", "image", "md"):
        per_kind[k] = q_count(
            collection_name=CANONICAL_COLLECTION,
            client=client,
            query_filter=build_filter(document_id=document_id, path=path, kind=k),
        )
    filtered = None
    if document_id or kind or path:
        filtered = q_count(
            collection_name=CANONICAL_COLLECTION,
            client=client,
            query_filter=build_filter(document_id=document_id, kind=kind, path=path),
        )
    return {
        "ok": True,
        "collection": CANONICAL_COLLECTION,
        "total": total,
        "per_kind": per_kind,
        "filtered": filtered,
        "filters": {"document_id": document_id, "kind": kind, "path": path},
    }


def do_list(
    document_id: str | None, kind: str | None, path: str | None, limit: int = 10
) -> Dict[str, Any]:
    client = get_qdrant_client()
    if qmodels is None:
        return {"ok": False, "error": "qdrant-client not available for scroll"}
    flt = build_filter(document_id=document_id, kind=kind, path=path)
    points, _ = client.scroll(
        collection_name=CANONICAL_COLLECTION,
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
                "path": (payload.get("path") or "").replace("\\", "/"),
                "kind": payload.get("kind"),
                "idx": payload.get("idx"),
                "text": textwrap.shorten(
                    (payload.get("text") or "").strip(), width=160, placeholder="…"
                ),
            }
        )
    return {
        "ok": True,
        "collection": CANONICAL_COLLECTION,
        "limit": limit,
        "rows": rows,
    }


# ─── CLI ─────────────────────────────────────────────────────────────────────
def main() -> None:
    p = argparse.ArgumentParser(
        description="Ingest dropzone → Qdrant (+ JSONL export) with stats/list utilities"
    )
    # ingest
    p.add_argument("--dir", default="data/dropzone")
    p.add_argument(
        "--export",
        default=os.getenv(
            "EXPORT_JSONL",
            getattr(settings, "EXPORT_JSONL", "data/exports/ingest.jsonl"),
        ),
    )
    p.add_argument("--strict", action="store_true")
    p.add_argument("--recreate-bad-collection", action="store_true")
    p.add_argument("--replace-existing", action="store_true")
    p.add_argument("--images", action="store_true")
    p.add_argument(
        "--once", action="store_true", help="Run one pass and exit (no loop)"
    )
    p.add_argument("--kinds", type=str, default=None)
    # read-only
    p.add_argument("--stats", action="store_true")
    p.add_argument("--list-files", action="store_true")
    p.add_argument("--list", action="store_true")
    p.add_argument("--list-collection", action="store_true")
    p.add_argument("--limit", type=int, default=20)
    # filters
    p.add_argument("--document-id", type=str, default=None)
    p.add_argument("--kind", type=str, default=None)
    p.add_argument("--path", type=str, default=None)
    p.add_argument("--filter-by", action="append", metavar="KEY=VALUE")
    # debug
    p.add_argument("--debug", action="store_true")
    p.add_argument("--dry-run", action="store_true")

    args = p.parse_args()

    # --once flag prevents looping but doesn't limit files
    limit_files = 0

    sugar = _parse_filter_sugar(args.filter_by)
    document_id = args.document_id or sugar.get("document_id")
    kind = args.kind or sugar.get("kind")
    path = args.path or sugar.get("path")

    kinds_set = set()
    if args.kinds:
        for k in args.kinds.replace(",", " ").split():
            if k:
                kinds_set.add(k.strip().lower())

    drop = Path(args.dir)
    explicit_path = Path(path) if path else None

    # Single source of truth for file discovery
    candidates = discover_candidates(
        root=drop,
        kinds_set=kinds_set,
        explicit_path=explicit_path,
        limit=args.limit if args.limit > 0 else 0,
    )

    if args.debug:
        qdrant_url = os.getenv(
            "QDRANT_URL", getattr(settings, "QDRANT_URL", "http://localhost:6333")
        )
        print(
            f"[debug] QDRANT_URL={qdrant_url} QDRANT_COLLECTION={CANONICAL_COLLECTION} EMBEDDINGS_MODEL={CANONICAL_MODEL} EMBEDDING_DIM={CANONICAL_DIM}"
        )
        print(
            f"[debug] candidate_files={len(candidates)} per_kind={{"
            f"'text': {sum(1 for _, _, k in candidates if k == 'text')}, "
            f"'pdf': {sum(1 for _, _, k in candidates if k == 'pdf')}, "
            f"'image': {sum(1 for _, _, k in candidates if k == 'image')}, "
            f"'audio': {sum(1 for _, _, k in candidates if k == 'audio')}}}"
        )

    if args.dry_run:
        per_kind = {"text": 0, "pdf": 0, "image": 0, "audio": 0}
        for _, _, k in candidates:
            if k in per_kind:
                per_kind[k] += 1
        summary = {
            "ok": True,
            "files_scanned": len(candidates),
            "chunks_parsed": 0,
            "points_upserted": 0,
            "points_skipped_dedupe": 0,
            "per_kind": per_kind,
            "collection": CANONICAL_COLLECTION,
            "embed_dim": CANONICAL_DIM,
            "elapsed_seconds": 0,
            "skipped": [],
        }
        print(json.dumps(summary, indent=2))
        return

    if args.list_files:
        print(
            json.dumps(
                {
                    "files": [{"path": rp, "kind": k} for _, rp, k in candidates],
                    "count": len(candidates),
                }
            )
        )
        return

    if args.list:
        out = do_list(document_id=document_id, kind=kind, path=path, limit=args.limit)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    if args.list_collection:
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
            rows.append(
                {
                    "id": str(getattr(p, "id", "")),
                    "document_id": payload.get("document_id"),
                    "path": (payload.get("path") or "").replace("\\", "/"),
                    "kind": payload.get("kind") or "text",
                    "idx": payload.get("idx"),
                }
            )
        print(json.dumps({"rows": rows, "count": len(rows)}))
        return

    # ingest execution
    t0 = time.time()
    export_path = Path(args.export) if args.export else None
    result = ingest_dir(
        drop_dir=drop,
        export_jsonl=export_path,
        strict=args.strict,
        recreate_bad=args.recreate_bad_collection,
        replace_existing=args.replace_existing,
        do_images=args.images,
        limit_files=limit_files,
        candidates=candidates,
    )

    # If --once flag is set, we're done after one pass
    if args.once:
        result["once_mode"] = True
    result["elapsed_seconds"] = time.time() - t0
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
