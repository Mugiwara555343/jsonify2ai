#!/usr/bin/env python3
"""
Archive Audit Utility for Massive Ingestion Phase.

Modes:
    default    - Full statistics report across all conversations.
    --preview  - Librarian Preview: mock file list for the first 10 conversations.

Scans data/raw_archives/conversations.json and produces a diagnostic report
without modifying core ingestion logic or creating any files.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# === Configuration ===
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent
ARCHIVE_PATH = PROJECT_ROOT / "data" / "raw_archives" / "conversations.json"
STAGED_DIR = PROJECT_ROOT / "data" / "staged"
MONSTER_THRESHOLD = 100_000  # chars — conversations above this get sharding flag
PREVIEW_COUNT = 10


class ConversationStats(NamedTuple):
    """Statistics for a single conversation."""

    title: str
    char_count: int
    create_time: float | None
    first_message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sanitize_title(title: str, max_len: int = 50) -> str:
    """Sanitize a conversation title for safe use as a filename component."""
    # Replace non-alphanumeric (except spaces/hyphens) with underscores
    safe = re.sub(r"[^\w\s\-]", "", title)
    # Collapse whitespace / hyphens into single underscore
    safe = re.sub(r"[\s\-]+", "_", safe).strip("_")
    return safe[:max_len] if safe else "Untitled"


def _extract_first_message(conversation: dict) -> str:
    """Extract the first non-empty user message text from a conversation."""
    mapping = conversation.get("mapping", {})
    for node in mapping.values():
        msg = node.get("message")
        if not msg or not msg.get("content"):
            continue
        if msg.get("author", {}).get("role") not in ("user",):
            continue
        for part in msg["content"].get("parts", []):
            if isinstance(part, str) and part.strip():
                return part.strip()
    return ""


def extract_char_count(conversation: dict) -> int:
    """Extract total character count from all message parts in a conversation."""
    total = 0
    mapping = conversation.get("mapping", {})
    for node in mapping.values():
        msg = node.get("message")
        if msg and msg.get("content"):
            parts = msg["content"].get("parts", [])
            for part in parts:
                if isinstance(part, str):
                    total += len(part)
    return total


def analyze_archive(filepath: Path) -> list[ConversationStats]:
    """Load and analyze all conversations from the archive."""
    print(f"Loading {filepath.name}...")
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    stats = []
    for conv in data:
        title = conv.get("title") or ""
        char_count = extract_char_count(conv)
        create_time = conv.get("create_time")
        first_msg = _extract_first_message(conv)
        stats.append(
            ConversationStats(
                title=title,
                char_count=char_count,
                create_time=create_time,
                first_message=first_msg,
            )
        )
    return stats


# ---------------------------------------------------------------------------
# Naming Convention
# ---------------------------------------------------------------------------


def propose_filename(stat: ConversationStats) -> str:
    """Generate YYYY-MM-DD_ChatTitle_Part1.md filename for a conversation."""
    # Date prefix
    if stat.create_time:
        dt = datetime.fromtimestamp(stat.create_time, tz=timezone.utc)
        date_str = dt.strftime("%Y-%m-%d")
    else:
        date_str = "0000-00-00"

    # Title component — fall back to truncated first message
    raw_title = stat.title.strip() if stat.title.strip() else ""
    if not raw_title:
        raw_title = stat.first_message[:40] if stat.first_message else "Untitled"
    safe_title = _sanitize_title(raw_title)

    return f"{date_str}_{safe_title}_Part1.md"


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


def format_number(n: int) -> str:
    return f"{n:,}"


def format_size_mb(bytes_count: int) -> str:
    return f"{bytes_count / (1024 * 1024):.1f} MB"


def print_report(stats: list[ConversationStats], file_size: int) -> None:
    """Print the full audit statistics report."""
    total_convos = len(stats)
    total_chars = sum(s.char_count for s in stats)
    avg_chars = total_chars // total_convos if total_convos > 0 else 0

    sorted_stats = sorted(stats, key=lambda s: s.char_count)
    shortest = sorted_stats[0] if sorted_stats else None
    longest = sorted_stats[-1] if sorted_stats else None

    staged_status = "EXISTS" if STAGED_DIR.exists() else "WILL BE CREATED"

    print()
    print("=" * 62)
    print("               ARCHIVE AUDIT REPORT")
    print("=" * 62)
    print(f"Source:              {ARCHIVE_PATH.relative_to(PROJECT_ROOT)}")
    print(f"File Size:           {format_size_mb(file_size)}")
    print()
    print("  STATISTICS")
    print("-" * 62)
    print(f"Total Conversations: {format_number(total_convos)}")
    print(f"Total Characters:    {format_number(total_chars)}")
    print(f"Avg Chars/Convo:     {format_number(avg_chars)}")
    print()
    print("  EXTREMES")
    print("-" * 62)
    if longest:
        t = longest.title[:50] or "(Untitled)"
        print(f'Longest:   "{t}" ({format_number(longest.char_count)} chars)')
    if shortest:
        t = shortest.title[:50] or "(Untitled)"
        print(f'Shortest:  "{t}" ({format_number(shortest.char_count)} chars)')
    print()
    print("  STAGING PREVIEW")
    print("-" * 62)
    print(f"Target Directory:    {STAGED_DIR.relative_to(PROJECT_ROOT)}")
    print(f"Status:              {staged_status}")
    print(f"Files to create:     {format_number(total_convos)} markdown files")
    print()
    print("=" * 62)
    print("[OK] Audit complete. No files were created or modified.")
    print("=" * 62)


def print_librarian_preview(stats: list[ConversationStats]) -> None:
    """Print the Librarian preview: mock file list for first N conversations."""
    preview = stats[:PREVIEW_COUNT]
    monsters = [s for s in preview if s.char_count >= MONSTER_THRESHOLD]

    print()
    print("=" * 62)
    print("          LIBRARIAN PREVIEW  (first 10)")
    print("=" * 62)
    print("Naming convention: YYYY-MM-DD_ChatTitle_PartX.md")
    print(f"Monster threshold: {format_number(MONSTER_THRESHOLD)} chars")
    print()

    for i, stat in enumerate(preview, 1):
        fname = propose_filename(stat)
        chars = format_number(stat.char_count)
        is_monster = stat.char_count >= MONSTER_THRESHOLD

        print(f"  {i:>2}. {fname}")
        print(f"      Chars: {chars}", end="")
        if is_monster:
            print("  [!] LARGE FILE - SHARDING REQUIRED", end="")
        print()

    # Summary
    print()
    print("-" * 62)
    print(f"  Previewed:  {len(preview)} / {len(stats)} conversations")
    print(
        f"  Monsters:   {len(monsters)} exceed {format_number(MONSTER_THRESHOLD)} chars"
    )
    print()

    # Ingestion discovery note
    print("  INGESTION VERIFICATION")
    print("-" * 62)
    print("  Watcher:    watch_dropzone.py uses watchdog on data/dropzone/")
    print("              Auto-detects new/modified files -> triggers ingest.")
    print("  Discovery:  discovery.py walks root via rglob, .md = text kind.")
    print()
    print("  [NOTE] The watcher monitors data/dropzone/, NOT data/staged/.")
    print("         Files placed in staged/ will NOT auto-ingest.")
    print("         To ingest, either:")
    print("           1. Copy staged .md files into data/dropzone/, or")
    print("           2. Run ingest_dropzone.py --dir data/staged/ manually.")
    print()
    print("=" * 62)
    print("[OK] Preview complete. No files were created.")
    print("=" * 62)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    if not ARCHIVE_PATH.exists():
        print(f"[ERROR] Archive not found at {ARCHIVE_PATH}")
        return

    preview_mode = "--preview" in sys.argv

    file_size = ARCHIVE_PATH.stat().st_size
    stats = analyze_archive(ARCHIVE_PATH)

    if preview_mode:
        print_librarian_preview(stats)
    else:
        print_report(stats, file_size)


if __name__ == "__main__":
    main()
