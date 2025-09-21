#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
cleanup_kind.py — delete Qdrant points by payload kind (safe by default)

Usage:
  # Dry-run (no deletion), show a sample of matches
  python scripts/cleanup_kind.py --kind md --sample 10

  # Actually delete all points where payload.kind == "md"
  python scripts/cleanup_kind.py --kind md --confirm

Options:
  --collection   Override collection (defaults to settings.QDRANT_COLLECTION)
  --sample N     How many example point IDs to print during dry-run [default: 10]
  --batch N      Delete batch size [default: 1024]
  --confirm      Perform deletion (omit for dry-run)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# --- bootstrap sys.path like other scripts ---
ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "worker", ROOT / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from worker.app.config import settings  # noqa: E402
from worker.app.services.qdrant_client import build_filter  # noqa: E402

try:
    from qdrant_client import QdrantClient  # third-party client
except Exception as e:
    raise RuntimeError("qdrant_client package is required for cleanup_kind.py") from e


def _make_client():
    # settings already loads .env; prefer URL/API key from there
    url = getattr(settings, "QDRANT_URL", None)
    api_key = getattr(settings, "QDRANT_API_KEY", None)
    if not url:
        raise RuntimeError(
            "QDRANT_URL is not set in settings; cannot connect to Qdrant"
        )
    # keep a conservative timeout; no vectors/payload in scroll anyway
    return QdrantClient(url=url, api_key=api_key, timeout=30.0)


def _iter_point_ids(client, collection: str, where, batch: int = 4096):
    """Yield point IDs matching filter using scroll pagination."""
    next_page = None
    while True:
        res = client.scroll(
            collection_name=collection,
            scroll_filter=where,
            limit=batch,
            with_payload=False,
            with_vectors=False,
            offset=next_page,
        )
        points, next_page = res
        if not points:
            break
        for p in points:
            yield p.id
        if next_page is None:
            break


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", required=True, help='payload "kind" to delete (e.g., md)')
    ap.add_argument(
        "--collection", default=None, help="Qdrant collection (defaults to settings)"
    )
    ap.add_argument(
        "--sample", type=int, default=10, help="sample size for dry-run printout"
    )
    ap.add_argument("--batch", type=int, default=1024, help="delete batch size")
    ap.add_argument("--confirm", action="store_true", help="perform deletion")
    args = ap.parse_args()

    collection = args.collection or settings.QDRANT_COLLECTION
    where = build_filter(kind=args.kind)

    client = _make_client()

    # Dry-run: count & sample
    sample_ids = []
    total = 0
    for pid in _iter_point_ids(client, collection, where, batch=4096):
        total += 1
        if len(sample_ids) < args.sample:
            sample_ids.append(pid)

    if not args.confirm:
        print(f"[cleanup] DRY-RUN — collection={collection!r} kind={args.kind!r}")
        print(f"[cleanup] would delete total points: {total}")
        if sample_ids:
            print(f"[cleanup] sample of {len(sample_ids)} point_ids:")
            for sid in sample_ids:
                print(f"  - {sid}")
        else:
            print("[cleanup] no matches")
        return 0

    # Confirmed deletion
    if total == 0:
        print(
            f"[cleanup] no matches to delete in collection={collection!r} for kind={args.kind!r}"
        )
        return 0

    print(
        f"[cleanup] CONFIRM — deleting {total} points from {collection!r} where kind=={args.kind!r}"
    )

    # Re-scan and delete in batches by point_id
    def _delete_ids(client: QdrantClient, collection_name: str, ids):
        """Compatibility wrapper: qdrant-client v1.x uses delete(),
        some older snippets used delete_points(). Prefer delete();
        fall back if needed."""
        if hasattr(client, "delete_points"):
            return client.delete_points(
                collection_name=collection_name, points_selector=ids
            )
        return client.delete(collection_name=collection_name, points_selector=ids)

    batch = []
    deleted = 0
    for pid in _iter_point_ids(client, collection, where, batch=4096):
        batch.append(pid)
        if len(batch) >= args.batch:
            _delete_ids(client, collection, batch)
            deleted += len(batch)
            batch.clear()
    if batch:
        _delete_ids(client, collection, batch)
        deleted += len(batch)

    print(f"[cleanup] deleted: {deleted} points")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
