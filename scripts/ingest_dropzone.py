#!/usr/bin/env python3
"""
Batch-ingest a 'drop zone' folder into JSON+Qdrant.

Usage:
  PYTHONPATH=worker python scripts/ingest_dropzone.py \
    --dir data/dropzone --export data/exports/ingest.jsonl
  # optional hard-fail on missing optional deps:
  PYTHONPATH=worker python scripts/ingest_dropzone.py --strict
  # optional fix when an old collection has wrong vector size:
  PYTHONPATH=worker python scripts/ingest_dropzone.py --reset-collection
"""

from __future__ import annotations
import argparse
import importlib.util
import json
import os
import sys
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List, Dict, Any, Tuple, Callable, Optional

# --- allow "from app..." imports when running from repo root
REPO_ROOT = Path(__file__).resolve().parents[1]
WORKER_DIR = REPO_ROOT / "worker"
if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))

# --- worker imports
from app.config import settings
from app.services.chunker import chunk_text
from app.services.qdrant_minimal import ensure_collection_minimal  # supports SDK/HTTP variants


# ===================== Parser registry (lazy + optional) =====================

def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None

# Each factory returns a callable (path: str) -> str
def _csv_factory():
    from app.services.parse_csv import extract_text_from_csv
    return extract_text_from_csv

def _json_factory():
    from app.services.parse_json import extract_text_from_json
    return extract_text_from_json

def _jsonl_factory():
    from app.services.parse_json import extract_text_from_jsonl
    return extract_text_from_jsonl

def _docx_factory():
    if not _module_available("docx"):
        raise RuntimeError("python-docx not installed; install with: pip install python-docx")
    from app.services.parse_docx import extract_text_from_docx
    return extract_text_from_docx

def _pdf_factory():
    if not _module_available("pypdf"):
        raise RuntimeError("pypdf not installed; install with: pip install pypdf")
    from app.services.parse_pdf import extract_text_from_pdf
    return extract_text_from_pdf

def _audio_factory():
    # dev-mode works without faster-whisper; real STT requires it (+ ffmpeg)
    from app.services.parse_audio import transcribe_audio
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

# Ignore images for now (we’ll add captioning later)
IGNORED_EXTS = {
    ".jsonl", ".zip", ".tar", ".gz", ".rar", ".7z",
    ".exe", ".dll", ".so", ".dylib", ".bin",
    ".png", ".jpg", ".jpeg", ".webp",
}

class SkipFile(RuntimeError):
    """Non-fatal: skip this file with a message."""

def extract_text_auto(path: str, strict: bool = False) -> str:
    p = Path(path)
    ext = p.suffix.lower()

    if ext in IGNORED_EXTS:
        raise SkipFile(f"ignored extension: {ext}")

    for exts, factory, need in REGISTRY:
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


# ============================== Qdrant helpers ==============================

@dataclass
class ChunkRecord:
    id: str              # MUST be unsigned int or UUID **string** for Qdrant
    document_id: str     # we keep doc grouping in payload
    path: str
    idx: int
    text: str
    meta: Dict[str, Any]

    def payload(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "path": self.path,
            "idx": self.idx,
            "text": self.text,
            **self.meta,
        }

def upsert_points_min(client, name: str,
                      items: Iterable[Tuple[str, List[float], Dict[str, Any]]]) -> int:
    """
    Minimal inline upsert to avoid importing helper variants.
    items = [(point_id: str|int, vector: list[float], payload: dict), ...]
    """
    from qdrant_client.conversions.common_types import PointStruct
    points = [PointStruct(id=i, vector=v, payload=p) for (i, v, p) in items]
    client.upsert(collection_name=name, points=points)
    return len(points)


# ============================== Embeddings ==================================

def _deterministic_vec(s: str, dim: int) -> List[float]:
    import hashlib
    h = hashlib.sha256(s.encode("utf-8")).digest()
    out: List[float] = []
    for i in range(dim):
        out.append(((h[i % len(h)]) / 255.0) * 2 - 1)  # [-1, 1]
    return out

def _embed_texts(texts: List[str]) -> List[List[float]]:
    dim = int(settings.EMBEDDING_DIM)
    if str(getattr(settings, "EMBED_DEV_MODE", 0)) == "1" or os.getenv("EMBED_DEV_MODE") == "1":
        return [_deterministic_vec(t, dim) for t in texts]
    try:
        from app.services.embed_ollama import embed_texts as embed_texts_real  # type: ignore
    except Exception:
        raise RuntimeError(
            "No embedder available. Either set EMBED_DEV_MODE=1 or install/run an embedding backend."
        )
    vecs = embed_texts_real(texts)
    if not vecs or len(vecs[0]) != dim:
        raise RuntimeError(f"Embedding dimension mismatch: expected {dim}, got {len(vecs[0]) if vecs else 'none'}")
    return vecs


# ============================== Orchestration ===============================

def _iter_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*"):
        if p.is_file():
            yield p

def ingest_dir(drop_dir: Path, export_jsonl: Path | None, strict: bool,
               reset_collection: bool) -> Dict[str, Any]:
    """Core ingest routine."""
    # Ensure collection exists (handle both bool and (ok,err) tuple variants)
    ensured = ensure_collection_minimal(name=settings.QDRANT_COLLECTION,
                                        dim=int(settings.EMBEDDING_DIM))
    if isinstance(ensured, tuple):
        ok, err = ensured
        if not ok:
            # Helpful auto-recovery: allow drop & recreate on dim mismatch
            if reset_collection and isinstance(err, str) and "dimension" in err.lower():
                from qdrant_client import QdrantClient
                c = QdrantClient(url=settings.QDRANT_URL)
                c.delete_collection(settings.QDRANT_COLLECTION)
                ensured2 = ensure_collection_minimal(name=settings.QDRANT_COLLECTION,
                                                     dim=int(settings.EMBEDDING_DIM))
                if isinstance(ensured2, tuple) and not ensured2[0]:
                    raise RuntimeError(f"Failed to re-create collection: {ensured2[1]}")
            else:
                raise RuntimeError(f"Failed to ensure collection: {err}")

    export_f = None
    if export_jsonl:
        export_jsonl.parent.mkdir(parents=True, exist_ok=True)
        export_f = export_jsonl.open("w", encoding="utf-8")

    from qdrant_client import QdrantClient
    client = QdrantClient(url=settings.QDRANT_URL)

    total_files = 0
    total_chunks = 0
    skipped: List[str] = []

    for fp in _iter_files(drop_dir):
        total_files += 1
        try:
            raw = extract_text_auto(str(fp), strict=strict)
        except SkipFile as e:
            skipped.append(f"{fp.name}: {e}")
            continue

        if not raw.strip():
            skipped.append(f"{fp.name}: empty content")
            continue

        chunks = list(chunk_text(raw, size=int(settings.CHUNK_SIZE),
                                 overlap=int(settings.CHUNK_OVERLAP)))
        if not chunks:
            skipped.append(f"{fp.name}: no chunks")
            continue

        vecs = _embed_texts(chunks)

        # One UUID per DOCUMENT for grouping + one UUID per POINT for Qdrant id
        doc_id = str(uuid.uuid4())
        items: List[Tuple[str, List[float], Dict[str, Any]]] = []

        for idx, (text, vec) in enumerate(zip(chunks, vecs)):
            point_id = str(uuid.uuid4())  # <-- valid Qdrant id
            rec = ChunkRecord(
                id=point_id,
                document_id=doc_id,
                path=str(fp),
                idx=idx,
                text=text,
                meta={"source_ext": fp.suffix.lower()},
            )
            items.append((rec.id, vec, rec.payload()))
            if export_f:
                export_f.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")

        total_chunks += upsert_points_min(client, settings.QDRANT_COLLECTION, items)

    if export_f:
        export_f.close()

    return {
        "files_seen": total_files,
        "chunks_upserted": total_chunks,
        "collection": settings.QDRANT_COLLECTION,
        "skipped": skipped,
    }


def main():
    p = argparse.ArgumentParser(description="Ingest a drop-zone folder into Qdrant + JSONL export")
    p.add_argument("--dir", default=os.getenv("DROPZONE_DIR", "data/dropzone"))
    p.add_argument("--export", default=os.getenv("EXPORT_JSONL", "data/exports/ingest.jsonl"))
    p.add_argument("--strict", action="store_true", help="fail on missing optional deps instead of skipping")
    p.add_argument("--reset-collection", action="store_true",
                   help="if collection dim mismatches, drop & recreate it automatically")
    args = p.parse_args()

    drop = Path(args.dir)
    if not drop.exists():
        raise SystemExit(f"Drop zone not found: {drop}")

    res = ingest_dir(drop_dir=drop,
                     export_jsonl=Path(args.export) if args.export else None,
                     strict=args.strict,
                     reset_collection=args.reset_collection)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
