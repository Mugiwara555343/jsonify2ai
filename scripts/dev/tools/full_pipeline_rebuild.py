#!/usr/bin/env python3
# ruff: noqa: E402
"""full_pipeline_rebuild.py

Thin maintenance wrapper: re-ingest AUDIO files (fresh STT) with TRUE replace
semantics and optionally reindex the Qdrant collection. All heavy lifting is
delegated to shared helpers; this file contains no bespoke ID/path logic.

Key behaviors:
  * Dry-run by default (requires --confirm for any writes)
  * Canonical POSIX relpaths + deterministic IDs via worker.app.utils.docids
  * Delete existing document_id before upserting (idempotent replace)
  * Audio dev-mode guard (AUDIO_DEV_MODE=1) unless explicitly overridden
  * Optional reindex step (--reindex + --confirm) leveraging existing helper

Outputs:
  * A discovery summary (human-readable)
  * One final single-line JSON summary containing core counters

Exit codes:
  0 success
  1 unexpected error
  2 refused due to AUDIO_DEV_MODE safeguard
"""

from __future__ import annotations

# ---------------- stdlib imports ----------------
import argparse
import json
import sys
import time
import pathlib
from typing import List, Tuple, Dict, Any

# ---------------- repo-root bootstrap ----------------
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ---------------- early .env load ----------------
try:  # pragma: no cover
    from dotenv import load_dotenv  # type: ignore

    dotenv_path = REPO_ROOT / ".env"
    if dotenv_path.exists():
        load_dotenv(dotenv_path=str(dotenv_path))
except Exception:  # pragma: no cover
    pass

# ---------------- third-party (none new) ----------------
try:  # pragma: no cover
    from qdrant_client.models import Distance as _QD_Distance  # type: ignore
except Exception:  # pragma: no cover
    _QD_Distance = None  # type: ignore

# ---------------- local imports ----------------
from worker.app.config import settings  # type: ignore
from worker.app.utils.docids import (  # single-source ID + path helpers
    canonicalize_relpath,
    document_id_for_relpath,
    chunk_id_for,
)
from worker.app.services.chunker import chunk_text  # type: ignore
from worker.app.services.embed_ollama import embed_texts as embed_texts_real  # type: ignore
from worker.app.services.qdrant_client import (  # type: ignore
    get_qdrant_client,
    upsert_points,
    delete_by_document_id,
    ensure_collection,
)

# Audio parsing helpers (prefer richer auto extractor if present)
try:  # pragma: no cover
    from worker.app.services.parse_audio import extract_text_auto as _extract_audio  # type: ignore
except Exception:  # pragma: no cover
    try:
        from worker.app.services.parse_audio import transcribe_audio as _extract_audio  # type: ignore
    except Exception:  # pragma: no cover
        _extract_audio = None  # type: ignore

# Optional reindex helper
try:  # pragma: no cover
    import scripts.reindex_collection as reindex_mod  # type: ignore
except Exception:  # pragma: no cover
    reindex_mod = None  # type: ignore

from worker.app.services.discovery import discover_candidates  # centralized


# ---------------- constants (settings only) ----------------
AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}
CANONICAL_COLLECTION = settings.QDRANT_COLLECTION
EMBED_DIM = settings.EMBEDDING_DIM
EMBED_DEV_MODE = str(getattr(settings, "EMBED_DEV_MODE", 0)) in {
    "1",
    "true",
    "True",
    "yes",
}
AUDIO_DEV_MODE = bool(getattr(settings, "AUDIO_DEV_MODE", False))
QDRANT_URL = getattr(settings, "QDRANT_URL", "http://localhost:6333")
if _QD_Distance is not None:
    CANONICAL_DISTANCE = _QD_Distance.COSINE  # type: ignore[attr-defined]
else:
    CANONICAL_DISTANCE = "Cosine"


# ---------------- embeddings adapter ----------------
def _deterministic_vec(s: str, dim: int) -> List[float]:
    import hashlib as _hashlib

    h = _hashlib.sha256(s.encode("utf-8")).digest()
    return [((h[i % len(h)]) / 255.0) * 2 - 1 for i in range(dim)]


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Standard embedding adapter using settings.* only.

    Provides deterministic vectors in dev mode; otherwise delegates to real embed implementation
    with explicit model, base_url and dimension enforcement.
    """
    if EMBED_DEV_MODE:
        return [_deterministic_vec(t, EMBED_DIM) for t in texts]
    vecs = embed_texts_real(
        texts,
        model=getattr(settings, "EMBEDDINGS_MODEL", None),
        base_url=getattr(settings, "OLLAMA_URL", None),
        dim=EMBED_DIM,
    )
    if not vecs or len(vecs[0]) != EMBED_DIM:
        raise RuntimeError(
            f"embedding dimension mismatch: expected {EMBED_DIM}, got {len(vecs[0]) if vecs else 'none'}"
        )
    return vecs


# ---------------- discovery fallback ----------------
def discover_audio_files(
    drop_dir: pathlib.Path, limit: int
) -> List[Tuple[pathlib.Path, str]]:
    """Centralized audio discovery via shared discover_candidates."""
    triples = discover_candidates(drop_dir, {"audio"}, None, limit if limit > 0 else 0)
    results: List[Tuple[pathlib.Path, str]] = []
    for p, rel, k in triples:
        if k != "audio":
            continue
        try:
            rel_canon = canonicalize_relpath(p, drop_dir)
        except Exception:
            continue
        results.append((p, rel_canon))
    return results


# ---------------- reindex wrapper ----------------
def _reindex(indexing_threshold: int, debug: bool) -> Dict[str, Any]:
    """Programmatic reindex leveraging existing helper module when possible.

    Strategy:
      * export existing points (id, payload, vector)
      * drop & recreate (respecting indexing_threshold if helper supports)
      * reinsert in batches
    """
    client = get_qdrant_client()

    if reindex_mod is None:
        # minimal: ensure (recreate when bad) empty collection
        try:
            ensure_collection(
                client=client,
                name=CANONICAL_COLLECTION,
                dim=EMBED_DIM,
                distance=CANONICAL_DISTANCE,
                recreate_bad=True,
            )
        except Exception as e:  # pragma: no cover
            return {"ok": False, "error": f"ensure failed: {e}"}
        return {"ok": True, "reindexed": True, "exported": 0, "reinserted": 0}

    # export
    try:
        points = reindex_mod.export_points(client, CANONICAL_COLLECTION)  # type: ignore[attr-defined]
    except Exception as e:  # pragma: no cover
        return {"ok": False, "error": f"export failed: {e}"}
    if debug:
        print(f"[debug] reindex export count={len(points)}")

    # ensure via wrapper (drop/recreate if mismatched)
    try:
        ensure_collection(
            client=client,
            name=CANONICAL_COLLECTION,
            dim=EMBED_DIM,
            distance=CANONICAL_DISTANCE,
            recreate_bad=True,
        )
        recreated = True
    except Exception as e:  # pragma: no cover
        return {"ok": False, "error": f"ensure failed: {e}"}

    # reinsert
    inserted = 0
    batch: List[Tuple[str, List[float], Dict[str, Any]]] = []
    for pid, payload, vec in points:
        batch.append((pid, vec, payload))
        if len(batch) >= 128:
            upsert_points(
                batch,
                collection_name=CANONICAL_COLLECTION,
                client=client,
                batch_size=len(batch),
                ensure=False,
            )
            inserted += len(batch)
            batch.clear()
    if batch:
        upsert_points(
            batch,
            collection_name=CANONICAL_COLLECTION,
            client=client,
            batch_size=len(batch),
            ensure=False,
        )
        inserted += len(batch)
    return {
        "ok": True,
        "reindexed": recreated,
        "exported": len(points),
        "reinserted": inserted,
    }


# ---------------- ingestion core ----------------
def _process_audio_files(
    items: List[Tuple[pathlib.Path, str]], *, debug: bool, limit: int
) -> Dict[str, Any]:
    client = get_qdrant_client()
    # Ensure target collection exists before any upsert
    try:
        ensure_collection(
            client=client,
            name=CANONICAL_COLLECTION,
            dim=EMBED_DIM,
            distance=CANONICAL_DISTANCE,
            recreate_bad=False,
        )
    except Exception as e:  # pragma: no cover
        raise RuntimeError(f"qdrant ensure failed: {e}")
    files_processed = 0
    files_skipped = 0
    chunks_upserted = 0

    for fp, rel in items:
        if limit and files_processed >= limit:
            break
        if debug:
            print(f"[file] {rel}")

        if _extract_audio is None:
            if debug:
                print(f"[skip] {rel} (audio parser unavailable)")
            files_skipped += 1
            continue

        try:
            transcript = _extract_audio(str(fp), strict=True)  # type: ignore[arg-type]
        except TypeError:
            # fallback if underlying function is transcribe_audio without 'strict'
            try:
                transcript = _extract_audio(str(fp))  # type: ignore[arg-type]
            except Exception as e:  # pragma: no cover
                if debug:
                    print(f"[skip] {rel} transcription error: {e}")
                files_skipped += 1
                continue
        except Exception as e:  # pragma: no cover
            if debug:
                print(f"[skip] {rel} transcription error: {e}")
            files_skipped += 1
            continue

        if not transcript or len(transcript.strip()) < 5:
            if debug:
                print(f"[skip] {rel} empty/short transcript")
            files_skipped += 1
            continue

        # chunk
        raw_chunks = chunk_text(
            transcript,
            size=int(getattr(settings, "CHUNK_SIZE", 800)),
            overlap=int(getattr(settings, "CHUNK_OVERLAP", 100)),
        )
        if not raw_chunks:
            if debug:
                print(f"[skip] {rel} produced no chunks")
            files_skipped += 1
            continue

        vectors = embed_texts(raw_chunks)
        dims = [len(v) for v in vectors]
        if any(d != EMBED_DIM for d in dims):
            if EMBED_DEV_MODE:
                print(
                    f"[warn] dim mismatch (dev mode skip) file={rel} dims={dims} expected={EMBED_DIM}",
                    file=sys.stderr,
                )
                files_skipped += 1
                continue
            raise RuntimeError(
                f"embedding dimension mismatch file={rel} dims={dims} expected={EMBED_DIM}"
            )

        doc_id = document_id_for_relpath(rel)
        # true replace semantics
        try:
            delete_by_document_id(str(doc_id), client=client)
        except Exception as e:  # pragma: no cover
            if debug:
                print(f"[debug] delete_by_document_id failed {rel}: {e}")

        payload_items: List[Tuple[str, List[float], Dict[str, Any]]] = []
        for idx, (chunk_text_str, vec) in enumerate(zip(raw_chunks, vectors)):
            payload = {
                "document_id": str(doc_id),
                "path": rel,  # canonical POSIX relpath
                "kind": "audio",
                "idx": idx,
                "text": chunk_text_str,
                "meta": {
                    "source_ext": fp.suffix.lower(),
                    "bytes": fp.stat().st_size,
                    "mtime": fp.stat().st_mtime,
                },
            }
            payload_items.append((str(chunk_id_for(doc_id, idx)), vec, payload))

        inserted = upsert_points(
            payload_items,
            collection_name=CANONICAL_COLLECTION,
            client=client,
            batch_size=len(payload_items),
            ensure=False,
        )
        chunks_upserted += inserted
        files_processed += 1
        if debug:
            print(f"[debug] file={rel} chunks={len(payload_items)} dims={dims}")

    return {
        "files_processed": files_processed,
        "files_skipped": files_skipped,
        "chunks_upserted": chunks_upserted,
    }


# ---------------- main entrypoint ----------------
def main() -> None:  # noqa: C901 - complexity acceptable for thin orchestration
    ap = argparse.ArgumentParser(
        description="Re-ingest audio files with replace semantics and optional reindex"
    )
    ap.add_argument("--dir", default="data/dropzone")
    ap.add_argument("--dry-run", action="store_true", default=False)
    ap.add_argument(
        "--confirm",
        action="store_true",
        default=False,
        help="Required to perform writes",
    )
    ap.add_argument(
        "--reindex",
        action="store_true",
        default=False,
        help="Drop & rebuild collection (with export/import) when confirmed",
    )
    ap.add_argument("--indexing-threshold", type=int, default=100)
    ap.add_argument(
        "--limit", type=int, default=0, help="Limit number of audio files processed"
    )
    ap.add_argument("--debug", action="store_true", default=False)
    ap.add_argument(
        "--allow-audio-with-dev-mode",
        action="store_true",
        default=False,
        help="Override safety when AUDIO_DEV_MODE=1 to run real pipeline",
    )
    ap.add_argument(
        "--only",
        type=str,
        default=None,
        help="Re-ingest only a single POSIX relative path within --dir (audio file)",
    )
    args = ap.parse_args()

    # Resolve drop_dir relative to repo root (mirrors ingest pattern) for --only handling
    drop_dir = pathlib.Path(args.dir)
    if not drop_dir.is_absolute():
        drop_dir = (REPO_ROOT / args.dir).resolve()
    if not drop_dir.exists():
        print(json.dumps({"ok": False, "error": f"directory not found: {drop_dir}"}))
        sys.exit(1)

    # Discover (supports --only override)
    audio_candidates: List[Tuple[pathlib.Path, str]]
    if args.only:
        target_path = (drop_dir / args.only).resolve()
        if not target_path.exists() or not target_path.is_file():
            print(
                f"[error] --only path not found or not a file: {args.only}",
                file=sys.stderr,
            )
            sys.exit(2)
        if target_path.suffix.lower() not in AUDIO_EXTS:
            print(
                f"[error] --only path is not an audio file (ext must be one of {sorted(AUDIO_EXTS)}): {args.only}",
                file=sys.stderr,
            )
            sys.exit(2)
        try:
            rel = canonicalize_relpath(target_path, drop_dir)
        except Exception as e:
            print(
                f"[error] canonicalize failed for --only path: {args.only} ({e})",
                file=sys.stderr,
            )
            sys.exit(2)
        audio_candidates = [(target_path, rel)]
        effective_limit = 0  # ignore --limit when --only is specified
    else:
        audio_candidates = discover_audio_files(
            drop_dir, args.limit if args.limit > 0 else 0
        )
        effective_limit = args.limit

    if args.debug:
        print(
            f"[debug] QDRANT_URL={QDRANT_URL} COLLECTION={CANONICAL_COLLECTION} EMBEDDINGS_MODEL={getattr(settings,'EMBEDDINGS_MODEL','')} EMBEDDING_DIM={EMBED_DIM}"
        )
        print(f"[debug] candidates={len(audio_candidates)}")

    # Human-readable discovery summary
    sample = [rel for _fp, rel in audio_candidates[:10]]
    print(
        f"[plan] mode={'execute' if (args.confirm and not args.dry_run) else 'dry-run'}"
    )
    print(f"[plan] audio_files_found={len(audio_candidates)} sample={sample}")
    if args.reindex:
        print("[plan] will_reindex=TRUE (only if execute mode)")

    execute_mode = args.confirm and not args.dry_run

    # Safety: audio dev-mode guard (only matters if we would execute real pipeline)
    if (
        execute_mode
        and audio_candidates
        and AUDIO_DEV_MODE
        and not args.allow_audio_with_dev_mode
    ):
        print(
            "[error] AUDIO_DEV_MODE=1 — refusing to run real STT. Set AUDIO_DEV_MODE=0 in this shell or pass --allow-audio-with-dev-mode to override.",
            file=sys.stderr,
        )
        sys.exit(2)

    if not execute_mode:
        # Final JSON summary (dry-run)
        summary = {
            "ok": True,
            "mode": "dry-run",
            "audio_files_found": len(audio_candidates),
            "files_processed": 0,
            "files_skipped": 0,
            "chunks_upserted": 0,
            "will_reindex": bool(args.reindex and args.confirm),
        }
        print(json.dumps(summary, ensure_ascii=False))
        return

    # Execute ingestion
    if args.only:
        # Always process exactly that one file; ignore slicing & limit enforcement
        ingest_result = _process_audio_files(
            audio_candidates,
            debug=args.debug,
            limit=0,
        )
    else:
        ingest_result = _process_audio_files(
            (
                audio_candidates
                if effective_limit == 0
                else audio_candidates[:effective_limit]
            ),
            debug=args.debug,
            limit=effective_limit,
        )

    # Optional reindex (after ingestion to reflect fresh data)
    summary = {
        "ok": True,
        "mode": "execute",
        "audio_files_found": len(audio_candidates),
        **ingest_result,
        "will_reindex": bool(args.reindex and args.confirm),
    }
    if args.reindex and args.confirm:
        # Execute reindex AFTER ingestion but do not embed details in summary (schema contract)
        _reindex(args.indexing_threshold, args.debug)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":  # pragma: no cover
    t0 = time.time()
    try:
        main()
    finally:
        dt = time.time() - t0
        print(f"\n[done in {dt:.2f}s]")
