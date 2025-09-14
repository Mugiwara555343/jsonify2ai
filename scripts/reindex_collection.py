#!/usr/bin/env python3
"""reindex_collection.py

Maintenance helper to export, optionally drop/recreate, and bulk reinsert a Qdrant collection.
Safe defaults; designed to be idempotent.

Steps:
 1. Scroll entire collection → write JSONL (id, payload, vector)
 2. If --drop-and-recreate: delete and recreate with canonical dim/distance (and indexing_threshold if supported)
 3. Reinsert points in batches

Environment precedence: CLI flags > env vars > settings.
"""

from __future__ import annotations

# stdlib
import argparse
import json
import os
import sys
import time
import pathlib
from typing import Any, Dict, List, Tuple

# repo-root bootstrap
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# dotenv early (optional)
try:  # pragma: no cover
    from dotenv import load_dotenv  # type: ignore

    dotenv_path = REPO_ROOT.joinpath(".env")
    if dotenv_path.exists():
        load_dotenv(dotenv_path=str(dotenv_path))
except Exception:
    pass

# local imports
from worker.app.config import settings  # noqa: E402
from worker.app.services.qdrant_client import (  # noqa: E402
    get_qdrant_client,
    upsert_points,
)

try:  # noqa: E402
    from worker.app.services.qdrant_minimal import ensure_collection_minimal  # type: ignore
except Exception:  # pragma: no cover
    ensure_collection_minimal = None  # type: ignore

CANONICAL_COLLECTION = os.getenv(
    "QDRANT_COLLECTION", getattr(settings, "QDRANT_COLLECTION", "jsonify2ai_chunks_768")
)
CANONICAL_DIM = int(os.getenv("EMBEDDING_DIM", getattr(settings, "EMBEDDING_DIM", 768)))
CANONICAL_DISTANCE = "Cosine"


def _ensure_collection(
    client,
    name: str,
    dim: int,
    distance: str,
    recreate_bad: bool,
    indexing_threshold: int | None,
):
    """Invoke ensure_collection_minimal with graceful fallback if signature differs.
    Allows optional indexing_threshold if supported; otherwise ignored.
    """
    if ensure_collection_minimal is None:
        # minimal manual create if helper missing
        try:
            client.get_collection(name)
            return
        except Exception:
            vectors_config = {"size": dim, "distance": distance}
            client.recreate_collection(
                collection_name=name, vectors_config=vectors_config
            )
            return

    import inspect

    sig = inspect.signature(ensure_collection_minimal)  # type: ignore
    kwargs = {}
    if "client" in sig.parameters:
        kwargs["client"] = client
    if "name" in sig.parameters:
        kwargs["name"] = name
    if "collection" in sig.parameters:
        kwargs["collection"] = name
    if "collection_name" in sig.parameters:
        kwargs["collection_name"] = name
    if "dim" in sig.parameters:
        kwargs["dim"] = dim
    if "vector_size" in sig.parameters:
        kwargs["vector_size"] = dim
    if "distance" in sig.parameters:
        kwargs["distance"] = distance
    if "recreate_bad" in sig.parameters:
        kwargs["recreate_bad"] = recreate_bad
    if "recreate" in sig.parameters and "recreate_bad" not in kwargs:
        kwargs["recreate"] = recreate_bad
    if indexing_threshold is not None and "indexing_threshold" in sig.parameters:
        kwargs["indexing_threshold"] = indexing_threshold
    try:
        ensure_collection_minimal(**kwargs)  # type: ignore
    except TypeError as e:  # pragma: no cover
        raise RuntimeError(f"ensure_collection_minimal incompatible: {e}") from e


def export_points(
    client, collection: str
) -> List[Tuple[str, Dict[str, Any], List[float]]]:
    points: List[Tuple[str, Dict[str, Any], List[float]]] = []
    next_offset = None
    while True:
        batch, next_offset = client.scroll(
            collection_name=collection,
            scroll_filter=None,
            with_payload=True,
            with_vectors=True,
            limit=256,
            offset=next_offset,
        )
        if not batch:
            break
        for p in batch:
            payload = getattr(p, "payload", {}) or {}
            vec = getattr(p, "vector", None)
            # qdrant-client normalization: might expose vectors or vector
            if vec is None and hasattr(p, "vectors"):
                vectors_attr = getattr(p, "vectors")
                if isinstance(vectors_attr, dict):
                    # unnamed vector -> first value
                    if vectors_attr:
                        vec = list(vectors_attr.values())[0]
                else:
                    vec = vectors_attr
            pid = str(getattr(p, "id", ""))
            if vec is None:
                continue
            points.append((pid, payload, vec))
        if next_offset is None:
            break
    return points


def main():
    ap = argparse.ArgumentParser(
        description="Reindex (export + optional rebuild) a Qdrant collection"
    )
    ap.add_argument("--collection", default=CANONICAL_COLLECTION)
    ap.add_argument("--export", default="data/exports/reindex.jsonl")
    ap.add_argument("--drop-and-recreate", action="store_true")
    ap.add_argument("--indexing_threshold", type=int, default=1)
    ap.add_argument("--batch-size", type=int, default=128)
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    collection = args.collection or CANONICAL_COLLECTION
    client = get_qdrant_client()

    if args.debug:
        print(
            f"[debug] collection={collection} export={args.export} drop={args.drop_and_recreate} indexing_threshold={args.indexing_threshold}"
        )

    # 1) Export existing points
    points = export_points(client, collection)
    if args.debug:
        print(f"[debug] exported_points={len(points)}")

    # Write export JSONL
    export_path = pathlib.Path(args.export)
    export_path.parent.mkdir(parents=True, exist_ok=True)
    with export_path.open("w", encoding="utf-8") as f:
        for pid, payload, vec in points:
            f.write(
                json.dumps(
                    {"id": pid, "payload": payload, "vector": vec}, ensure_ascii=False
                )
                + "\n"
            )

    if args.dry_run:
        print(
            json.dumps(
                {
                    "ok": True,
                    "exported": len(points),
                    "dry_run": True,
                    "collection": collection,
                },
                indent=2,
            )
        )
        return

    # 2) Drop & recreate if requested
    if args.drop_and_recreate:
        try:
            client.delete_collection(collection_name=collection)
        except Exception as e:
            if args.debug:
                print(f"[debug] delete_collection error (ignored if not exists): {e}")
        _ensure_collection(
            client,
            collection,
            CANONICAL_DIM,
            CANONICAL_DISTANCE,
            recreate_bad=True,
            indexing_threshold=args.indexing_threshold,
        )

    # 3) Reinsert
    if points:
        batch: List[Tuple[str, List[float], Dict[str, Any]]] = []
        inserted = 0
        for pid, payload, vec in points:
            batch.append((pid, vec, payload))
            if len(batch) >= args.batch_size:
                upsert_points(
                    batch,
                    collection_name=collection,
                    client=client,
                    batch_size=len(batch),
                    ensure=False,
                )
                inserted += len(batch)
                batch.clear()
        if batch:
            upsert_points(
                batch,
                collection_name=collection,
                client=client,
                batch_size=len(batch),
                ensure=False,
            )
            inserted += len(batch)
        print(
            json.dumps(
                {
                    "ok": True,
                    "exported": len(points),
                    "reinserted": inserted,
                    "collection": collection,
                },
                indent=2,
            )
        )
    else:
        print(
            json.dumps(
                {"ok": True, "exported": 0, "reinserted": 0, "collection": collection},
                indent=2,
            )
        )


if __name__ == "__main__":  # pragma: no cover
    t0 = time.time()
    try:
        main()
    finally:
        dt = time.time() - t0
        print(f"\n[done in {dt:.2f}s]")
