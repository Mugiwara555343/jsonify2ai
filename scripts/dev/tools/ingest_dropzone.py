#!/usr/bin/env python3
"""
ingest_dropzone.py

Batch-ingest a "drop zone" folder into Qdrant using the unified chunk schema.
Also provides read-only utilities: --stats, --list-files, --list, --list-collection.

Notes (to prevent regressions):
- Imports: stdlib → repo-root bootstrap → local imports with # noqa: E402.
- Idempotence: deterministic document_id (from canonical POSIX relpath); --replace-existing re-writes.
- Dev mode: settings.EMBED_DEV_MODE returns deterministic fake vectors (keeps pipeline alive).
"""

from __future__ import annotations


# ─── stdlib ───────────────────────────────────────────────────────────────────
import argparse
import hashlib
import importlib.util
import json
import os
import sys
import textwrap
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple


# --- repo-root bootstrap (after stdlib imports; before local imports) ---
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
# ----------------------------------------------------------------------

## Discovery helpers removed; now using centralized worker.app.services.discovery


# === BEGIN id helpers (moved to worker.app.utils.docids) ===
def content_sig_bytes(b: bytes) -> str:  # retained local helper for hashing bytes
    return hashlib.sha256(b).hexdigest()


# === END id helpers ===


# Load .env so entrypoint processes see repository defaults early (no-op if python-dotenv missing)
try:
    from dotenv import load_dotenv  # type: ignore

    dotenv_path = REPO_ROOT.joinpath(".env")
    if dotenv_path.exists():
        load_dotenv(dotenv_path=str(dotenv_path))
except Exception:
    # If python-dotenv isn't installed or load fails, fall back to system env (no crash)
    pass

# ─── third-party imports ──────────────────────────────────────────────────────────
try:
    from qdrant_client import models as qmodels  # type: ignore
except Exception:  # pragma: no cover
    qmodels = None  # type: ignore

# Optional Distance enum (prefer enum if available)
try:  # pragma: no cover
    from qdrant_client.models import Distance as _QD_Distance  # type: ignore
except Exception:  # pragma: no cover
    _QD_Distance = None  # type: ignore

# ─── local imports (after bootstrap; silenced for E402) ──────────────────────
from worker.app.config import settings  # noqa: E402
from worker.app.services.chunker import chunk_text  # noqa: E402
import worker.app.services.embed_ollama as _embed_mod  # noqa: E402
from worker.app.services.discovery import discover_candidates  # noqa: E402

# Lazy image caption import performed in the images branch to avoid hard dependency.
from worker.app.utils.docids import (  # noqa: E402
    canonicalize_relpath,
    document_id_for_relpath,
    chunk_id_for,
)

# Local alias to keep call sites unchanged after module import above
embed_texts_real = _embed_mod.embed_texts

try:
    from worker.app.services.qdrant_client import (  # noqa: E402
        get_qdrant_client,
        upsert_points,
        delete_by_document_id,
        count as q_count,
        build_filter,
        ensure_collection,
    )
except ImportError:
    from worker.app.services.qdrant_client import (  # noqa: E402
        get_qdrant_client,
        upsert_points,
        delete_by_document_id,
        count as q_count,
        build_filter,
        ensure_collection,
    )

    def ensure_collection(*a, **kw):  # type: ignore  # noqa: F811
        raise RuntimeError("ensure_collection not available")


# ─── config/constants ─────────────────────────────────────────────────────────
CANONICAL_COLLECTION = settings.QDRANT_COLLECTION
CANONICAL_IMAGES_COLLECTION = (
    getattr(settings, "QDRANT_COLLECTION_IMAGES", None)
    or f"{CANONICAL_COLLECTION}_images"
)
CANONICAL_DIM = settings.EMBEDDING_DIM
CANONICAL_MODEL = settings.EMBEDDINGS_MODEL
if _QD_Distance is not None:
    CANONICAL_DISTANCE = _QD_Distance.COSINE  # type: ignore[attr-defined]
else:
    CANONICAL_DISTANCE = "Cosine"
EMBED_DEV_MODE = str(getattr(settings, "EMBED_DEV_MODE", 0)).strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}
# Images are ingested via the dedicated image path; don't classify them as ignored
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
# Only non-image junk belongs here (archives, binaries, temp, etc.)
IGNORED_EXTS = {
    ".zip",
    ".7z",
    ".rar",
    ".tar",
    ".gz",
    ".exe",
    ".dll",
    ".so",
    ".bin",
    ".class",
    ".obj",
    ".o",
    ".log",
}


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
    # Don't ignore image files here; they are handled by the image branch in ingest
    if (ext in IGNORED_EXTS) and (ext not in IMAGE_EXTS):
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
    """Standard embedding adapter (settings-only; deterministic dev mode)."""
    dim = CANONICAL_DIM
    if EMBED_DEV_MODE:
        return [_deterministic_vec(t, dim) for t in texts]
    vecs = embed_texts_real(
        texts,
        model=CANONICAL_MODEL,
        base_url=getattr(settings, "OLLAMA_URL", None),
        dim=dim,
    )
    if not vecs or len(vecs[0]) != dim:
        raise RuntimeError(
            f"embedding dimension mismatch: expected {dim}, got {len(vecs[0]) if vecs else 'none'}"
        )
    return vecs


# ─── utils ───────────────────────────────────────────────────────────────────
def _iter_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*"):
        if p.is_file():
            yield p


# removed unused helper


# ─── qdrant ensure (signature-adaptive) ──────────────────────────────────────
def qdrant_preflight(client) -> None:
    """Fail fast if Qdrant is unreachable/misconfigured (clear message)."""
    try:
        client.get_collections()
    except Exception as e:
        raise SystemExit(f"[qdrant] unreachable or misconfigured: {e}")


## ensure_collection_compat removed; using ensure_collection directly


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

    # Ensure canonical collection
    ensure_collection(
        client=client,
        name=CANONICAL_COLLECTION,
        dim=CANONICAL_DIM,
        distance=CANONICAL_DISTANCE,
        recreate_bad=recreate_bad,
    )

    # Optional image collection
    if do_images:
        ensure_collection(
            client=client,
            name=CANONICAL_IMAGES_COLLECTION,
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

    # Use candidates if provided, otherwise scan drop_dir (ingest path ignores limit)
    file_iter = candidates or discover_candidates(drop_dir, set(), None, 0)

    for fp, rel_path, kind in file_iter:
        # Canonicalize rel path to enforce single-source path (prevents duplicates)
        try:
            rel_path = canonicalize_relpath(fp, drop_dir)
        except ValueError as e:
            skipped.append(f"{fp.name}: {e}")
            continue
        ext = fp.suffix.lower()
        bytes_ = fp.read_bytes()
        content_sig = content_sig_bytes(bytes_)
        document_uuid = document_id_for_relpath(rel_path)
        document_id = str(document_uuid)

        total_files += 1
        per_kind[kind] += 1

        # images path (optional)
        if do_images and kind == "image":
            try:
                try:
                    from worker.app.services.image_caption import caption_image  # type: ignore
                except Exception:
                    caption_image = None  # type: ignore
                    try:
                        import logging as _logging

                        _logging.getLogger(__name__).warning(
                            "image_caption module not available; proceeding without captions."
                        )
                    except Exception:
                        pass
                cap = caption_image(fp) if caption_image else ""
                vec = embed_texts([cap])[0]
                if replace_existing:
                    try:  # enforce replace semantics only when requested
                        delete_by_document_id(document_id, client=client)
                    except Exception:
                        pass
                item = (
                    str(chunk_id_for(document_uuid, 0)),
                    vec,
                    {
                        "document_id": document_id,
                        "path": rel_path,
                        "kind": "image",
                        "idx": 0,
                        **({"text": cap} if cap else {}),
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
                    collection_name=CANONICAL_IMAGES_COLLECTION,
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

        # Delete existing points only when --replace-existing
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
        # Validate each embedding vector length; continue in dev mode, error otherwise
        bad_dims = []
        for i, v in enumerate(vecs):
            if len(v) != CANONICAL_DIM:
                bad_dims.append((i, len(v)))
        if bad_dims:
            for idx_bad, got_len in bad_dims:
                print(
                    f"[error] vector dim mismatch file={rel_path} chunk_idx={idx_bad} expected={CANONICAL_DIM} got={got_len}",
                    file=sys.stderr,
                )
            if not EMBED_DEV_MODE:
                raise RuntimeError(
                    f"Aborting ingest due to {len(bad_dims)} malformed vectors (see errors above)."
                )

        # build items
        items: List[Tuple[str, List[float], Dict[str, Any]]] = []
        for idx, (text, vec) in enumerate(zip(chunks, vecs)):
            key = (document_id, idx)
            if key in seen_points:
                points_skipped_dedupe += 1
                continue
            seen_points.add(key)
            rec = ChunkRecord(
                id=str(chunk_id_for(document_uuid, idx)),
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
                rec_dict = asdict(rec)
                rec_dict["vec_len"] = len(vec)
                export_f.write(json.dumps(rec_dict, ensure_ascii=False) + "\n")

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
    for k in ("text", "pdf", "audio", "image"):
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
                    (payload.get("text") or "").strip(), width=160, placeholder="..."
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
        description="Ingest dropzone -> Qdrant (+ JSONL export) with stats/list utilities"
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
    p.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Limit rows for --list / --list-collection (not used for ingestion)",
    )
    p.add_argument(
        "--allow-audio-with-dev-mode",
        action="store_true",
        help="Override AUDIO_DEV_MODE safeguard for explicit testing",
    )
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
    # Determine read-only mode early to decide whether to narrow discovery by --path
    read_only_mode = (
        args.stats
        or args.list
        or args.list_files
        or args.list_collection
        or args.dry_run
    )
    # Only pass explicit_path for ingestion flows; keep full listing for read-only
    explicit_path = Path(path) if (path and not read_only_mode) else None

    # Single source of truth for file discovery (apply limit only for read-only listing modes)
    discovery_limit = (
        args.limit
        if (args.list or args.list_files or args.list_collection) and args.limit > 0
        else 0
    )
    candidates = discover_candidates(
        root=drop,
        kinds_set=kinds_set,
        explicit_path=explicit_path,
        limit=discovery_limit,
    )

    # Safety net: when --path is set for ingestion, ensure only that POSIX relpath remains
    if path and not read_only_mode:
        candidates = [c for c in candidates if c[1] == path]

    if args.debug:
        qdrant_url = getattr(settings, "QDRANT_URL", "http://localhost:6333")
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

    # --- Narrow AUDIO_DEV_MODE guard ---
    # Only enforce when the operation will perform real ingestion (parse/embed/upsert)
    # Allow purely read-only modes: --stats, --list, --list-files, --list-collection, dry-run listing paths, etc.
    AUDIO_DEV_MODE = bool(getattr(settings, "AUDIO_DEV_MODE", False))
    # read_only_mode already computed above
    requested_audio = any(k == "audio" for _f, _r, k in candidates)
    will_ingest = not read_only_mode  # ingest path executes later in script
    if (
        AUDIO_DEV_MODE
        and will_ingest
        and requested_audio
        and not args.allow_audio_with_dev_mode
    ):
        print(
            "[error] AUDIO_DEV_MODE=1 — refusing to run real STT. Set AUDIO_DEV_MODE=0 in this shell or pass --allow-audio-with-dev-mode to override."
        )
        raise SystemExit(2)

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
        collection_name = (
            CANONICAL_IMAGES_COLLECTION if args.images else CANONICAL_COLLECTION
        )
        points, _ = client.scroll(
            collection_name=collection_name,
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
    print(json.dumps({"rows": rows, "count": len(rows), "collection": collection_name}))
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
