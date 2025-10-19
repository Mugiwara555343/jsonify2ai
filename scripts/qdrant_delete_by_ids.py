#!/usr/bin/env python3
"""
Delete Qdrant points by ID from a list file produced by qdrant_list_prefix.py.

Usage:
  python scripts/qdrant_delete_by_ids.py [--really] [--in=path]

Env:
  QDRANT_URL         (default: http://localhost:6333)
  QDRANT_COLLECTION  (default: jsonify2ai_chunks_768)

Input file format (default data/exports/dup_candidates.json):
[
  {"id": "<point-id>", "path": "data/dropzone/...."},
  ...
]
"""

import os
import sys
import json
import argparse
import requests

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333").rstrip("/")
COLLECTION = os.getenv("QDRANT_COLLECTION", "jsonify2ai_chunks_768")


def load_ids(path):
    with open(path, "r", encoding="utf-8") as f:
        items = json.load(f)
    ids = []
    for it in items:
        # Qdrant IDs may be int or string; keep as-is
        pid = it.get("id")
        if pid is not None:
            ids.append(pid)
    return ids, items


def delete_points(ids):
    url = f"{QDRANT_URL}/collections/{COLLECTION}/points/delete"
    body = {"points": ids}
    r = requests.post(url, json=body, timeout=60)
    r.raise_for_status()
    return r.json()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--really",
        action="store_true",
        help="Actually perform the delete. Without this flag, just show a summary.",
    )
    ap.add_argument(
        "--in",
        dest="infile",
        default="data/exports/dup_candidates.json",
        help="Path to dup list JSON (default: data/exports/dup_candidates.json)",
    )
    args = ap.parse_args()

    ids, items = load_ids(args.infile)
    print(f"[plan] loaded {len(items)} candidates from {args.infile}")
    if not ids:
        print("[plan] no IDs found; exiting")
        return

    # Preview first few
    preview = items[:5]
    print("[plan] preview (first 5):")
    for it in preview:
        print(f"  id={it.get('id')} path={it.get('path')}")

    if not args.really:
        print(
            f"[dry-run] would delete {len(ids)} points from collection '{COLLECTION}' at {QDRANT_URL}"
        )
        print("[dry-run] re-run with --really to execute.")
        return

    # Execute
    res = delete_points(ids)
    print("[done] delete request accepted by Qdrant")
    print(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as e:
        print(f"[error] HTTP {e.response.status_code}: {e.response.text[:500]}")
        sys.exit(2)
    except Exception as e:
        print(f"[error] {e}")
        sys.exit(1)
