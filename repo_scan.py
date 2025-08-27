# scripts/repo_scan.py
# Scans a repo tree, builds a light-weight project map for quick context,
# and (NEW) emits an image candidate list to bootstrap the image pipeline.

import os
import json
import re
import hashlib
import sys

# --- CLI / root selection
# Accept a directory as the first argument (defaults to current working dir)
ROOT = sys.argv[1] if len(sys.argv) > 1 else "."

# --- Ignore rules
# Skip common heavy/noisy directories and system detritus
IGNORE = re.compile(r"(\.git|node_modules|__pycache__|dist|build|\.venv|env|.DS_Store)")

# --- ADDED: image extension set
# Minimal, broad coverage for common image types; easy to extend later.
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


# --- File signature helper
# Reads up to 128 KiB from the file head and returns a SHA1.
# This is stable and cheap, and lets us detect identical heads quickly.
def file_sig(p: str) -> str:
    try:
        with open(p, "rb") as f:
            data = f.read(1024 * 128)  # 128 KiB
        return hashlib.sha1(data).hexdigest()
    except Exception:
        return "ERR"


records = []  # all files (for project.map.json)
image_records = []  # --- ADDED: image-only view (for images.candidates.json)

# --- Walk the tree
for dp, dn, fn in os.walk(ROOT):
    # Skip ignored directories by path substring match
    if IGNORE.search(dp):
        continue

    for fname in fn:
        # Skip ignored files (by name)
        if IGNORE.search(fname):
            continue

        # Absolute and relative paths
        p = os.path.join(dp, fname)
        rel = os.path.relpath(p, ROOT)

        # Basic file attributes
        ext = os.path.splitext(fname)[1].lower()

        try:
            size = os.path.getsize(p)
        except OSError:
            # If size fails, skip the file safely
            size = -1

        # --- Classify and capture a "head" preview for text-like files only
        # Keep behavior: for "huge" files we avoid reading them as text.
        if size > 1024 * 1024 * 2:  # > 2 MiB considered "huge" here
            kind = "binary"
            head = ""
        else:
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                    # Keep the same compact preview window (8k chars)
                    head = fh.read(8000)
                kind = "text"
            except Exception:
                # Non-text (or unreadable) falls back to binary with no head
                kind = "binary"
                head = ""

        # --- Build the record for project.map.json
        rec = {
            "path": rel,
            "ext": ext,
            "size": size,
            "sig": file_sig(p),
            "head": head,
            "kind": kind,  # (text|binary) classification for quick triage
        }

        # --- ADDED: detect and queue image candidates
        # We don't need EXIF or MIME sniffing yet—extension + existence is enough.
        if ext in IMAGE_EXTS:
            # Promote kind to "image" in the main map for clarity
            rec["kind"] = "image"

            # Store a minimal, ingestion-ready view for the image pipeline.
            # This file is intentionally small and fast to parse later.
            image_records.append(
                {
                    "path": rel,
                    "ext": ext,
                    "size": size,
                    "sig": rec["sig"],  # re-use the head hash for dedupe checks
                    "kind": "image",
                }
            )

        records.append(rec)

# --- Write the full map (original behavior)
with open("project.map.json", "w", encoding="utf-8") as out:
    json.dump(records, out, indent=2)
print("Wrote project.map.json with", len(records), "files")

# --- ADDED: Write image candidate list
# This is the small, focused handoff we’ll use to seed /process/image.
with open("images.candidates.json", "w", encoding="utf-8") as imgs:
    json.dump(image_records, imgs, indent=2)
print("Wrote images.candidates.json with", len(image_records), "image files")
