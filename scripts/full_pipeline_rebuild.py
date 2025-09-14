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
import os
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

# ---------------- local imports ----------------
from worker.app.config import settings  # type: ignore
from worker.app.utils.docids import (  # single-source ID + path helpers
    canonicalize_relpath,
    document_id_for_relpath,
    chunk_id_for,
)
from worker.app.services.chunker import chunk_text  # type: ignore
from worker.app.services.embed_ollama import embed_texts  # type: ignore
from worker.app.services.qdrant_client import (  # type: ignore
    get_qdrant_client,
    upsert_points,
    delete_by_document_id,
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

# Optional centralized discovery helper
try:  # pragma: no cover
    from worker.app.services.discovery import discover_candidates as _discover  # type: ignore
except Exception:  # pragma: no cover
    _discover = None  # type: ignore


# ---------------- constants / env derived ----------------
AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}
CANONICAL_COLLECTION = os.getenv(
    "QDRANT_COLLECTION", getattr(settings, "QDRANT_COLLECTION", "jsonify2ai_chunks_768")
)
EMBED_DIM = int(os.getenv("EMBEDDING_DIM", getattr(settings, "EMBEDDING_DIM", 768)))
EMBED_DEV_MODE = os.getenv(
    "EMBED_DEV_MODE", str(getattr(settings, "EMBED_DEV_MODE", 0))
) in {"1", "true", "True"}
AUDIO_DEV_MODE = os.getenv(
    "AUDIO_DEV_MODE", str(getattr(settings, "AUDIO_DEV_MODE", 0))
).strip().lower() in {"1", "true", "yes", "on"}
QDRANT_URL = os.getenv(
    "QDRANT_URL", getattr(settings, "QDRANT_URL", "http://localhost:6333")
)


# ---------------- discovery fallback ----------------
def _fallback_discover_audio(root: pathlib.Path, limit: int) -> List[pathlib.Path]:
    out: List[pathlib.Path] = []
    for fp in root.rglob("*"):
        if not fp.is_file():
            continue
        if fp.suffix.lower() in AUDIO_EXTS:
            out.append(fp)
            if limit and len(out) >= limit:
                break
    out.sort()
    return out


def discover_audio_files(
    drop_dir: pathlib.Path, limit: int
) -> List[Tuple[pathlib.Path, str]]:
    """Return list of (absolute_path, canonical_relpath).

    Uses centralized discovery if available; otherwise a local glob.
    Only audio kind is returned.
    """
    paths: List[pathlib.Path]
    if _discover is not None:
        try:
            triples = _discover(drop_dir, {"audio"}, None, limit if limit > 0 else 0)
            # expected shape: (path, rel, kind)
            paths = [p for p, _rel, k in triples if k == "audio"]
        except Exception:
            paths = _fallback_discover_audio(drop_dir, limit)
    else:
        paths = _fallback_discover_audio(drop_dir, limit)

    results: List[Tuple[pathlib.Path, str]] = []
    for p in paths:
        try:
            rel = canonicalize_relpath(p, drop_dir)
        except Exception:
            continue  # safety: skip anything outside root
        results.append((p, rel))
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
        # minimal: delete & recreate empty collection
        try:
            client.delete_collection(collection_name=CANONICAL_COLLECTION)
        except Exception as e:  # pragma: no cover
            if debug:
                print(f"[debug] delete_collection (ignored): {e}")
        client.recreate_collection(
            collection_name=CANONICAL_COLLECTION,
            vectors_config={"size": EMBED_DIM, "distance": "Cosine"},
        )
        return {"ok": True, "reindexed": True, "exported": 0, "reinserted": 0}

    # export
    try:
        points = reindex_mod.export_points(client, CANONICAL_COLLECTION)  # type: ignore[attr-defined]
    except Exception as e:  # pragma: no cover
        return {"ok": False, "error": f"export failed: {e}"}
    if debug:
        print(f"[debug] reindex export count={len(points)}")

    # drop
    try:
        client.delete_collection(collection_name=CANONICAL_COLLECTION)
    except Exception as e:  # pragma: no cover
        if debug:
            print(f"[debug] delete_collection error (ignored): {e}")

    # recreate via private helper if present, else manual
    recreated = False
    if hasattr(reindex_mod, "_ensure_collection"):
        try:
            reindex_mod._ensure_collection(  # type: ignore[attr-defined]
                client,
                CANONICAL_COLLECTION,
                EMBED_DIM,
                "Cosine",
                recreate_bad=True,
                indexing_threshold=indexing_threshold,
            )
            recreated = True
        except Exception as e:  # pragma: no cover
            return {"ok": False, "error": f"recreate failed: {e}"}
    else:
        client.recreate_collection(
            collection_name=CANONICAL_COLLECTION,
            vectors_config={"size": EMBED_DIM, "distance": "Cosine"},
        )
        recreated = True

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
    args = ap.parse_args()

    drop_dir = pathlib.Path(args.dir)
    if not drop_dir.exists():
        print(json.dumps({"ok": False, "error": f"directory not found: {drop_dir}"}))
        sys.exit(1)

    # Discover
    audio_candidates = discover_audio_files(
        drop_dir, args.limit if args.limit > 0 else 0
    )

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
    ingest_result = _process_audio_files(
        audio_candidates if args.limit == 0 else audio_candidates[: args.limit],
        debug=args.debug,
        limit=args.limit,
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
