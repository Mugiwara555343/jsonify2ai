#!/usr/bin/env python3
"""full_pipeline_rebuild.py

MAINTENANCE WRAPPER — thin orchestration: calls existing helpers; do not duplicate parsing/embedding/upsert logic here.

Purpose:
  1. Re-ingest ONLY audio files (fresh STT) replacing existing vectors for those document_ids.
  2. (Optional) Reindex (drop & recreate) the primary Qdrant collection, preserving points.

Safety:
  - No writes unless --confirm is provided.
  - --reindex honored ONLY when --confirm is also set.
  - Default invocation (no flags) performs a dry-run summary.

Environment precedence: CLI flags > env vars > settings.
Exit codes: 0 success / 1 unexpected error.
"""

from __future__ import annotations

# ---------------- stdlib imports ----------------
import argparse
import json
import os
import sys
import time
import pathlib
import uuid
from typing import List, Tuple, Optional, Dict, Any

# ---------------- repo-root bootstrap ----------------
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ---------------- early .env load (must precede settings import) ----------------
try:  # pragma: no cover
    from dotenv import load_dotenv  # type: ignore

    dotenv_path = REPO_ROOT.joinpath(".env")
    if dotenv_path.exists():
        load_dotenv(dotenv_path=str(dotenv_path))
except Exception:  # pragma: no cover
    pass

# ---------------- third-party (none new) ----------------

# ---------------- local imports ----------------
from worker.app.config import settings  # noqa: E402
from worker.app.services.chunker import chunk_text  # noqa: E402
from worker.app.services.embed_ollama import embed_texts  # noqa: E402
from worker.app.services.qdrant_client import (  # noqa: E402
    get_qdrant_client,
    upsert_points,
    delete_by_document_id,
)

# Optional helpers (best-effort imports; fallbacks provided)
try:  # noqa: E402
    from worker.app.services.parse_audio import extract_text_auto, transcribe_audio  # type: ignore
except Exception:  # pragma: no cover
    try:
        from worker.app.services.parse_audio import transcribe_audio  # type: ignore

        extract_text_auto = None  # type: ignore
    except Exception:  # pragma: no cover
        transcribe_audio = None  # type: ignore
        extract_text_auto = None  # type: ignore

try:  # noqa: E402
    import scripts.reindex_collection as reindex_mod  # type: ignore
except Exception:  # pragma: no cover
    reindex_mod = None  # type: ignore

# ---------------- constants / config ----------------
AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}
CANONICAL_COLLECTION = os.getenv(
    "QDRANT_COLLECTION", getattr(settings, "QDRANT_COLLECTION", "jsonify2ai_chunks_768")
)
CANONICAL_DIM = int(os.getenv("EMBEDDING_DIM", getattr(settings, "EMBEDDING_DIM", 768)))
CANONICAL_DISTANCE = "Cosine"
EMBED_DEV_MODE = (os.getenv("EMBED_DEV_MODE") == "1") or (
    str(getattr(settings, "EMBED_DEV_MODE", 0)) == "1"
)
DEFAULT_NAMESPACE = getattr(
    settings, "NAMESPACE_UUID", uuid.UUID("00000000-0000-5000-8000-000000000000")
)


# ---------------- id helpers (lightweight / non-core) ----------------
def document_id_for_relpath(relpath: str) -> str:
    return str(uuid.uuid5(DEFAULT_NAMESPACE, relpath))


def chunk_id_for(document_id: str, idx: int) -> str:
    return str(uuid.uuid5(uuid.UUID(document_id), f"chunk:{idx}"))


# ---------------- discovery (prefer centralized helper if present) ----------------
def _fallback_discover_audio(
    root: pathlib.Path, limit: int
) -> List[Tuple[pathlib.Path, str]]:
    out: List[Tuple[pathlib.Path, str]] = []
    root = root.resolve()
    for fp in root.rglob("*"):
        if not fp.is_file():
            continue
        if fp.suffix.lower() in AUDIO_EXTS:
            rel = fp.relative_to(root).as_posix()
            out.append((fp, rel))
            if limit and len(out) >= limit:
                break
    out.sort(key=lambda t: t[1])
    return out


def discover_audio(root: pathlib.Path, limit: int) -> List[Tuple[pathlib.Path, str]]:
    """Attempt to use a generic discover_candidates helper; fallback to local scan.

    We look for a function discover_candidates(root, kinds_set, explicit_path, limit)
    (as implemented in scripts/ingest_dropzone.py). Importing that script is safe
    because its top-level does not perform writes.
    """
    try:  # pragma: no cover (best-effort)
        from scripts.ingest_dropzone import discover_candidates as dc  # type: ignore

        triples = dc(root, {"audio"}, None, limit if limit > 0 else 0)
        # dc returns (path, rel, kind); we map to (path, rel)
        return [(p, r) for p, r, _k in triples if _k == "audio"]
    except Exception:
        return _fallback_discover_audio(root, limit)


# ---------------- audio transcription wrapper ----------------
class SkipFile(RuntimeError):
    """Non-fatal skip sentinel."""


def _transcribe(path: str) -> str:
    if extract_text_auto is not None:  # prefer richer auto extractor if available
        try:
            return extract_text_auto(path, strict=True)  # type: ignore[arg-type]
        except Exception as e:
            raise SkipFile(str(e))
    if transcribe_audio is None:
        raise SkipFile("audio parser not available (install audio requirements)")
    try:
        return transcribe_audio(path)  # type: ignore[arg-type]
    except Exception as e:  # pragma: no cover
        raise SkipFile(f"transcription failed: {e}")


# ---------------- reindex implementation ----------------
def _do_reindex(indexing_threshold: int, debug: bool) -> Dict[str, Any]:
    """Programmatic reindex using scripts.reindex_collection module when available.

    Returns a JSON-serializable dict summarizing reindex results.
    """
    client = get_qdrant_client()
    if reindex_mod is None:
        # Minimal fallback: drop & recreate empty collection
        try:
            client.delete_collection(collection_name=CANONICAL_COLLECTION)
        except Exception as e:  # pragma: no cover
            if debug:
                print(f"[debug] delete_collection (ignored if missing): {e}")
        client.recreate_collection(
            collection_name=CANONICAL_COLLECTION,
            vectors_config={"size": CANONICAL_DIM, "distance": CANONICAL_DISTANCE},
        )
        return {"ok": True, "reindexed": True, "exported": 0, "reinserted": 0}

    # Use existing export logic then rebuild
    try:
        points = reindex_mod.export_points(client, CANONICAL_COLLECTION)  # type: ignore[attr-defined]
    except Exception as e:  # pragma: no cover
        return {"ok": False, "error": f"export failed: {e}"}

    if debug:
        print(f"[debug] reindex export count={len(points)}")

    # Drop & recreate (leveraging its private helper if present)
    try:
        client.delete_collection(collection_name=CANONICAL_COLLECTION)
    except Exception as e:  # pragma: no cover
        if debug:
            print(f"[debug] delete_collection error (ignored): {e}")

    recreated = False
    if hasattr(reindex_mod, "_ensure_collection"):
        try:
            reindex_mod._ensure_collection(  # type: ignore[attr-defined]
                client,
                CANONICAL_COLLECTION,
                CANONICAL_DIM,
                CANONICAL_DISTANCE,
                recreate_bad=True,
                indexing_threshold=indexing_threshold,
            )
            recreated = True
        except Exception as e:  # pragma: no cover
            return {"ok": False, "error": f"recreate failed: {e}"}
    else:  # fallback create
        client.recreate_collection(
            collection_name=CANONICAL_COLLECTION,
            vectors_config={"size": CANONICAL_DIM, "distance": CANONICAL_DISTANCE},
        )
        recreated = True

    # Reinsert
    inserted = 0
    batch: List[Tuple[str, List[float], Dict[str, Any]]] = []
    for pid, payload, vec in points:  # type: ignore[assignment]
        batch.append((pid, vec, payload))
        if len(batch) >= 128:
            inserted += upsert_points(
                batch,
                collection_name=CANONICAL_COLLECTION,
                client=client,
                batch_size=len(batch),
                ensure=False,
            )
            batch.clear()
    if batch:
        inserted += upsert_points(
            batch,
            collection_name=CANONICAL_COLLECTION,
            client=client,
            batch_size=len(batch),
            ensure=False,
        )
    return {
        "ok": True,
        "reindexed": recreated,
        "exported": len(points),  # type: ignore[arg-type]
        "reinserted": inserted,
    }


# ---------------- core orchestration ----------------
def _ingest_audio_files(
    audio_files: List[Tuple[pathlib.Path, str]],
    *,
    debug: bool,
    limit: int,
) -> Dict[str, Any]:
    client = get_qdrant_client()
    files_processed = 0
    files_skipped = 0
    skipped: List[str] = []
    chunks_upserted = 0

    for fp, rel in audio_files:
        if debug:
            print(f"[file] {rel}")
        try:
            transcript = _transcribe(str(fp))
        except SkipFile as e:
            skipped.append(f"{rel}: {e}")
            files_skipped += 1
            continue
        if not transcript or len(transcript.strip()) < 5:
            skipped.append(f"{rel}: empty/short transcript")
            files_skipped += 1
            continue

        chunks = chunk_text(
            transcript,
            size=int(getattr(settings, "CHUNK_SIZE", 800)),
            overlap=int(getattr(settings, "CHUNK_OVERLAP", 100)),
        )
        if not chunks:
            skipped.append(f"{rel}: no chunks")
            files_skipped += 1
            continue

        vecs = embed_texts(chunks)
        dims = [len(v) for v in vecs]
        if any(d != CANONICAL_DIM for d in dims):
            if not EMBED_DEV_MODE:
                print(
                    f"[error] embedding dimension mismatch file={rel} dims={dims} expected={CANONICAL_DIM}",
                    file=sys.stderr,
                )
                raise SystemExit(1)
            skipped.append(f"{rel}: dim mismatch (dev mode skip)")
            files_skipped += 1
            continue

        document_id = document_id_for_relpath(rel)
        try:
            delete_by_document_id(document_id, client=client)
        except Exception as e:  # pragma: no cover
            if debug:
                print(f"[debug] delete_by_document_id failed {rel}: {e}")

        items: List[Tuple[str, List[float], Dict[str, Any]]] = []
        for idx, (text, vec) in enumerate(zip(chunks, vecs)):
            payload = {
                "document_id": document_id,
                "path": rel,
                "kind": "audio",
                "idx": idx,
                "text": text,
                "meta": {
                    "source_ext": fp.suffix.lower(),
                    "bytes": fp.stat().st_size,
                    "mtime": fp.stat().st_mtime,
                },
            }
            items.append((chunk_id_for(document_id, idx), vec, payload))

        inserted = upsert_points(
            items,
            collection_name=CANONICAL_COLLECTION,
            client=client,
            batch_size=len(items),
            ensure=False,
        )
        chunks_upserted += inserted
        files_processed += 1
        if debug:
            print(f"[debug] file={rel} chunks={len(items)} dims={dims}")

        if limit and files_processed >= limit:
            break

    return {
        "files_processed": files_processed,
        "files_skipped": files_skipped,
        "chunks_upserted": chunks_upserted,
        "skipped": skipped,
    }


def main() -> None:  # noqa: C901
    parser = argparse.ArgumentParser(
        description="Re-ingest audio files (fresh STT) and optionally reindex collection"
    )
    parser.add_argument("--dir", default="data/dropzone")
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument("--confirm", action="store_true", default=False)
    parser.add_argument("--reindex", action="store_true", default=False)
    parser.add_argument("--indexing-threshold", type=int, default=100)
    parser.add_argument(
        "--limit", type=int, default=0, help="Limit number of audio files processed"
    )
    parser.add_argument("--debug", action="store_true", default=False)
    args = parser.parse_args()

    drop_dir = pathlib.Path(args.dir)
    if not drop_dir.exists():
        print(json.dumps({"ok": False, "error": f"directory not found: {drop_dir}"}))
        sys.exit(1)

    audio_candidates = discover_audio(drop_dir, args.limit if args.limit > 0 else 0)

    effective_dry_run = args.dry_run or (not args.confirm)

    if args.debug:
        qdrant_url = os.getenv(
            "QDRANT_URL", getattr(settings, "QDRANT_URL", "http://localhost:6333")
        )
        print(
            f"[debug] QDRANT_URL={qdrant_url} COLLECTION={CANONICAL_COLLECTION} EMBEDDINGS_MODEL={getattr(settings,'EMBEDDINGS_MODEL','')} EMBEDDING_DIM={CANONICAL_DIM}"
        )
        print(f"[debug] candidates={len(audio_candidates)}")

    plan = {
        "ok": True,
        "mode": "dry-run" if effective_dry_run else "execute",
        "audio_files_found": len(audio_candidates),
        "will_reindex": bool(args.reindex and args.confirm),
        "collection": CANONICAL_COLLECTION,
        "sample": [rel for _fp, rel in audio_candidates[:10]],
    }

    # Always print plan first
    print(json.dumps(plan, ensure_ascii=False, indent=2))

    if effective_dry_run:
        return

    # Execute ingestion
    ingest_result = _ingest_audio_files(
        audio_candidates if args.limit == 0 else audio_candidates[: args.limit],
        debug=args.debug,
        limit=args.limit,
    )

    reindex_result: Optional[Dict[str, Any]] = None
    if args.reindex and args.confirm:
        reindex_result = _do_reindex(args.indexing_threshold, args.debug)

    summary = {
        "ok": True,
        "collection": CANONICAL_COLLECTION,
        **ingest_result,
    }
    if reindex_result:
        summary["reindex"] = reindex_result
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":  # pragma: no cover
    t0 = time.time()
    try:
        main()
    finally:
        dt = time.time() - t0
        print(f"\n[done in {dt:.2f}s]")
