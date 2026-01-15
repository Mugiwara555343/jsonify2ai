#!/usr/bin/env python3
"""
Dry-run: list Qdrant point IDs whose payload.path starts with a given prefix.
Writes JSON to data/exports/dup_candidates.json:
[
  {"id": "<point-id>", "path": "data/dropzone/...."},
  ...
]
Env:
  QDRANT_URL           (default: http://localhost:6333)
  QDRANT_COLLECTION    (default: jsonify2ai_chunks_768)
  PREFIX               (default: data/dropzone/)
  MAX_POINTS           (default: 20000) # safety cap
  PAGE_LIMIT           (default: 256)   # per scroll page
"""

import os
import sys
import json
import requests

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333").rstrip("/")
COLLECTION = os.getenv("QDRANT_COLLECTION", "jsonify2ai_chunks_768")
PREFIX = os.getenv("PREFIX", "data/dropzone/")
MAX_POINTS = int(os.getenv("MAX_POINTS", "20000"))
PAGE_LIMIT = int(os.getenv("PAGE_LIMIT", "256"))

OUT_DIR = "data/exports"
OUT_FILE = f"{OUT_DIR}/dup_candidates.json"


def scroll(offset=None):
    url = f"{QDRANT_URL}/collections/{COLLECTION}/points/scroll"
    body = {"limit": PAGE_LIMIT, "with_payload": True}
    if offset is not None:
        body["offset"] = offset
    r = requests.post(url, json=body, timeout=30)
    r.raise_for_status()
    return r.json()


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    out = []
    seen = 0
    offset = None
    while True:
        data = scroll(offset)
        pts = data.get("result", {}).get("points", [])
        offset = data.get("result", {}).get("next_page_offset")
        for p in pts:
            seen += 1
            pl = p.get("payload", {})
            path = pl.get("path")
            if isinstance(path, list):  # sometimes payload values are arrays
                # pick first string path if present
                path = next((x for x in path if isinstance(x, str)), None)
            if isinstance(path, str) and path.startswith(PREFIX):
                out.append({"id": p.get("id"), "path": path})
        # stop conditions
        if not offset or seen >= MAX_POINTS:
            break
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[dry-run] scanned={seen} matched={len(out)} prefix={PREFIX}")
    print(f"[dry-run] wrote: {OUT_FILE}")


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as e:
        print(f"[error] HTTP {e.response.status_code}: {e.response.text[:500]}")
        sys.exit(2)
    except Exception as e:
        print(f"[error] {e}")
        sys.exit(1)
