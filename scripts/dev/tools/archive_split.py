#!/usr/bin/env python3
"""
Librarian Split - Archive Conversation Splitter.

Splits conversations from data/raw_archives/conversations.json into individual
.md files with metadata headers, sharding large conversations at ~50K character
boundaries (never mid-message).

Pipeline:  raw_archives/ -> staged/ -> dropzone/

Usage:
    python scripts/dev/tools/archive_split.py          # split first 10
    python scripts/dev/tools/archive_split.py --count 5 # split first 5
    python scripts/dev/tools/archive_split.py --dry-run  # preview only
"""

import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# === Configuration ===
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent
ARCHIVE_PATH = PROJECT_ROOT / "data" / "raw_archives" / "conversations.json"
STAGED_DIR = PROJECT_ROOT / "data" / "staged"
DROPZONE_DIR = PROJECT_ROOT / "data" / "dropzone"
MANIFEST_PATH = STAGED_DIR / "ingestion_manifest.json"

SHARD_THRESHOLD = 50_000  # chars per part
DEFAULT_COUNT = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sanitize_title(title: str, max_len: int = 50) -> str:
    """Sanitize a title for filesystem-safe filenames."""
    safe = re.sub(r"[^\w\s\-]", "", title)
    safe = re.sub(r"[\s\-]+", "_", safe).strip("_")
    return safe[:max_len] if safe else "Untitled"


def _extract_first_user_message(conversation: dict) -> str:
    """Get the first non-empty user message for fallback title."""
    mapping = conversation.get("mapping", {})
    for node in mapping.values():
        msg = node.get("message")
        if not msg or not msg.get("content"):
            continue
        if msg.get("author", {}).get("role") != "user":
            continue
        for part in msg["content"].get("parts", []):
            if isinstance(part, str) and part.strip():
                return part.strip()
    return ""


def _walk_messages(conversation: dict) -> list[dict]:
    """Walk the mapping tree root -> first-child chain, returning messages in order."""
    mapping = conversation.get("mapping", {})
    if not mapping:
        return []

    # Find root node (no parent)
    root_id = None
    for node_id, node in mapping.items():
        if node.get("parent") is None:
            root_id = node_id
            break
    if root_id is None:
        return []

    messages = []
    cur_id = root_id
    visited = set()
    while cur_id and cur_id not in visited:
        visited.add(cur_id)
        node = mapping.get(cur_id)
        if not node:
            break

        msg = node.get("message")
        if msg and msg.get("content"):
            role = msg.get("author", {}).get("role", "unknown")
            parts = msg["content"].get("parts", [])
            text_parts = [p for p in parts if isinstance(p, str)]
            text = "\n".join(text_parts).strip()
            if text:
                messages.append({"role": role, "text": text})

        children = node.get("children", [])
        cur_id = children[0] if children else None

    return messages


def _messages_to_markdown(messages: list[dict]) -> str:
    """Convert a list of messages to markdown text (no header)."""
    blocks = []
    for msg in messages:
        role_label = msg["role"].capitalize()
        blocks.append(f"## {role_label}\n\n{msg['text']}")
    return "\n\n".join(blocks)


def _build_header(
    title: str, conv_id: str, created: str, part: int, total_parts: int, char_count: int
) -> str:
    """Build the YAML front-matter metadata header."""
    return (
        f"---\n"
        f"Source: ChatGPT Export\n"
        f"Original Title: {title}\n"
        f"Conversation ID: {conv_id}\n"
        f"Created: {created}\n"
        f"Part: {part} of {total_parts}\n"
        f"Characters: {char_count:,}\n"
        f"---\n\n"
    )


# ---------------------------------------------------------------------------
# Sharding
# ---------------------------------------------------------------------------


def _shard_messages(messages: list[dict], threshold: int) -> list[list[dict]]:
    """Split messages into shards of approximately `threshold` chars each.

    Never splits mid-message — each shard boundary falls between messages.
    """
    if not messages:
        return [[]]

    shards = []
    current_shard: list[dict] = []
    current_chars = 0

    for msg in messages:
        msg_len = len(msg["text"])

        # If adding this message exceeds threshold AND shard is non-empty, start new shard
        if current_chars + msg_len > threshold and current_shard:
            shards.append(current_shard)
            current_shard = []
            current_chars = 0

        current_shard.append(msg)
        current_chars += msg_len

    # Don't forget the last shard
    if current_shard:
        shards.append(current_shard)

    return shards


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def _load_manifest() -> dict:
    """Load the ingestion manifest, or return a fresh one."""
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"created": datetime.now(timezone.utc).isoformat(), "entries": []}


def _save_manifest(manifest: dict) -> None:
    """Save the ingestion manifest."""
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _is_already_processed(manifest: dict, conv_id: str) -> bool:
    """Check if a conversation ID is already in the manifest."""
    return any(e["conversation_id"] == conv_id for e in manifest["entries"])


# ---------------------------------------------------------------------------
# Core Split
# ---------------------------------------------------------------------------


def split_conversation(conv: dict, manifest: dict, dry_run: bool) -> list[str]:
    """Split a single conversation into .md files. Returns list of filenames created."""
    conv_id = conv.get("id") or conv.get("conversation_id") or "unknown"
    title_raw = conv.get("title", "").strip()
    create_time = conv.get("create_time")

    # Dedup check
    if _is_already_processed(manifest, conv_id):
        print(f"  [SKIP] Already in manifest: {title_raw or conv_id}")
        return []

    # Date
    if create_time:
        dt = datetime.fromtimestamp(create_time, tz=timezone.utc)
        date_str = dt.strftime("%Y-%m-%d")
    else:
        date_str = "0000-00-00"

    # Title
    display_title = title_raw if title_raw else None
    if not display_title:
        first_msg = _extract_first_user_message(conv)
        display_title = first_msg[:40] if first_msg else "Untitled"
    safe_title = _sanitize_title(display_title)

    # Walk messages
    messages = _walk_messages(conv)
    if not messages:
        print(f"  [SKIP] No messages: {display_title}")
        return []

    total_chars = sum(len(m["text"]) for m in messages)

    # Shard if needed
    shards = _shard_messages(messages, SHARD_THRESHOLD)
    total_parts = len(shards)

    filenames = []
    for part_num, shard in enumerate(shards, 1):
        fname = f"{date_str}_{safe_title}_Part{part_num}.md"
        shard_chars = sum(len(m["text"]) for m in shard)

        body = _messages_to_markdown(shard)
        header = _build_header(
            title=display_title,
            conv_id=conv_id,
            created=date_str,
            part=part_num,
            total_parts=total_parts,
            char_count=shard_chars,
        )
        content = header + body + "\n"

        if not dry_run:
            out_path = STAGED_DIR / fname
            out_path.write_text(content, encoding="utf-8")

        filenames.append(fname)

    # Update manifest
    if not dry_run:
        manifest["entries"].append(
            {
                "conversation_id": conv_id,
                "original_title": display_title,
                "files": filenames,
                "total_chars": total_chars,
                "parts": total_parts,
            }
        )

    monster_tag = "  [!] MONSTER" if total_chars >= 100_000 else ""
    print(
        f"  [OK] {safe_title}: {total_parts} part(s), {total_chars:,} chars{monster_tag}"
    )

    return filenames


def copy_to_dropzone(filenames: list[str]) -> int:
    """Copy staged files to the dropzone. Returns count of files copied."""
    DROPZONE_DIR.mkdir(parents=True, exist_ok=True)
    copied = 0
    for fname in filenames:
        src = STAGED_DIR / fname
        dst = DROPZONE_DIR / fname
        if src.exists():
            shutil.copy2(src, dst)
            copied += 1
    return copied


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    if not ARCHIVE_PATH.exists():
        print(f"[ERROR] Archive not found: {ARCHIVE_PATH}")
        return

    dry_run = "--dry-run" in sys.argv
    count = DEFAULT_COUNT
    if "--count" in sys.argv:
        idx = sys.argv.index("--count")
        if idx + 1 < len(sys.argv):
            count = int(sys.argv[idx + 1])

    # Load archive
    print(f"Loading {ARCHIVE_PATH.name}...")
    with open(ARCHIVE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    conversations = data[:count]

    # Setup
    STAGED_DIR.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest()

    print()
    print("=" * 62)
    mode_label = "DRY RUN" if dry_run else "SPLITTING"
    print(f"    LIBRARIAN {mode_label}  ({count} conversations)")
    print("=" * 62)
    print()

    all_files: list[str] = []
    skipped = 0

    for i, conv in enumerate(conversations, 1):
        title = conv.get("title", "").strip() or "(Untitled)"
        print(f"  [{i}/{count}] {title[:50]}")
        files = split_conversation(conv, manifest, dry_run)
        if files:
            all_files.extend(files)
        else:
            skipped += 1

    # Save manifest
    if not dry_run:
        _save_manifest(manifest)

    # Summary
    print()
    print("-" * 62)
    print(f"  Staged:     {len(all_files)} files")
    print(f"  Skipped:    {skipped} (already in manifest or empty)")
    if not dry_run:
        print(f"  Manifest:   {MANIFEST_PATH.relative_to(PROJECT_ROOT)}")

    # Copy to dropzone
    if not dry_run and all_files:
        print()
        print("  Copying to dropzone...")
        copied = copy_to_dropzone(all_files)
        print(
            f"  Delivered:  {copied} files -> {DROPZONE_DIR.relative_to(PROJECT_ROOT)}"
        )

    print()
    print("=" * 62)
    if dry_run:
        print("[OK] Dry run complete. No files were created.")
    else:
        print("[OK] Split complete. Watcher should pick up new files shortly.")
    print("=" * 62)


if __name__ == "__main__":
    main()
