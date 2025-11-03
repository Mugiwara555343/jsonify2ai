#!/usr/bin/env python3
import os
import time
import json
import hashlib
import requests
import sys
import signal
from pathlib import Path
from datetime import datetime, timezone
import threading

# Environment variables with defaults
DROPZONE = os.getenv("WATCH_DIR", "data/dropzone")
WORKER_BASE = os.getenv("WORKER_BASE", "http://worker:8090")
STATE_FILE = os.getenv("WATCH_STATE", "data/.watcher_state.json")
INTERVAL = float(os.getenv("WATCH_INTERVAL_SEC", "2.0"))
STRIP_PREFIX = os.getenv("WATCH_STRIP_PREFIX", "")
REQUIRE_PREFIX = os.getenv("WATCH_REQUIRE_PREFIX", "data/")
STABLE_PASSES = int(os.getenv("WATCH_STABLE_PASSES", "2"))
STRIP_PREFIX = os.getenv("WATCH_STRIP_PREFIX", "")
REQUIRE_PREFIX = os.getenv("WATCH_REQUIRE_PREFIX", "data/")
LOG_MAX_MB = int(os.getenv("MAX_LOG_MB", os.getenv("WATCH_LOG_MAX_MB", "16")))

EXT_KIND = {
    ".txt": "text",
    ".md": "text",
    ".json": "text",
    ".csv": "text",
    ".pdf": "pdf",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".gif": "image",
    ".bmp": "image",
    ".wav": "audio",
    ".mp3": "audio",
    ".m4a": "audio",
    ".flac": "audio",
    ".ogg": "audio",
}


def kind_for(p: Path) -> str:
    """Get kind for file based on extension."""
    return EXT_KIND.get(p.suffix.lower(), "")


# Global state
retry_queue = []
log_lock = threading.Lock()
log_file = None


def should_ignore(path: Path) -> bool:
    """Check if path should be ignored based on patterns."""
    name = path.name
    # Hidden files
    if name.startswith("."):
        return True
    # Transient patterns
    transient_patterns = [
        "~$",
        "*.tmp",
        "*.part",
        "*.partial",
        "*.crdownload",
        ".DS_Store",
        "Thumbs.db",
    ]
    for pattern in transient_patterns:
        if pattern.startswith("*"):
            if name.endswith(pattern[1:]):
                return True
        elif name == pattern:
            return True
    return False


def normalize_path(path: str) -> str:
    """Normalize path for worker consumption."""
    # Convert to forward slashes
    normalized = path.replace("\\", "/")

    # Strip prefix if configured
    if STRIP_PREFIX and normalized.startswith(STRIP_PREFIX):
        normalized = normalized[len(STRIP_PREFIX) :]

    # Ensure it starts with required prefix
    if not normalized.startswith(REQUIRE_PREFIX):
        return None  # Reject this path

    return normalized


def file_sig(p: Path) -> str:
    """Generate file signature with optional content hash for small files."""
    try:
        st = p.stat()
        size = st.st_size
        mtime = int(st.st_mtime)

        # For small files (<4KB), include content hash
        if size < 4096:
            try:
                with open(p, "rb") as f:
                    content_hash = hashlib.md5(f.read()).hexdigest()[:8]
                return f"{size}:{mtime}:{content_hash}"
            except (OSError, IOError):
                pass

        return f"{size}:{mtime}"
    except FileNotFoundError:
        return ""


def log_event(event: str, level: str = "info", **kwargs):
    """Write structured JSON log entry."""
    global log_file

    try:
        with log_lock:
            if log_file is None:
                # Initialize log file
                log_dir = Path("data/logs")
                log_dir.mkdir(parents=True, exist_ok=True)
                log_file = log_dir / "watcher.jsonl"

            # Check if rotation needed (2-deep: .1, .2)
            if log_file.exists() and log_file.stat().st_size > (
                LOG_MAX_MB * 1024 * 1024
            ):
                log_file_2 = log_file.with_suffix(".jsonl.2")
                log_file_1 = log_file.with_suffix(".jsonl.1")

                # If .2 exists, delete it (oldest)
                if log_file_2.exists():
                    log_file_2.unlink()

                # If .1 exists, rename to .2
                if log_file_1.exists():
                    log_file_1.rename(log_file_2)

                # Rename current to .1
                log_file.rename(log_file_1)

                # Current file is now gone; next write will create a new one

            # Write log entry
            log_entry = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "level": level,
                "subsystem": "watcher",
                "event": event,
                **kwargs,
            }

            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    except Exception as e:
        print(f"[watcher] log error: {e}")


def trigger(kind: str, path: str):
    url = f"{WORKER_BASE}/process/{kind}"
    try:
        r = requests.post(
            url, json={"path": path}, timeout=30, headers={"X-From-Watcher": "1"}
        )
        ok = r.status_code == 200 and r.json().get("ok", True)
        print(f"[watcher] trigger {kind} -> {path} status={r.status_code} ok={ok}")
        return ok, r.status_code
    except Exception as e:
        print(f"[watcher] trigger failed {kind} -> {path} err={e}")
        return False, 0


def process_retry_queue():
    """Process retry queue with exponential backoff."""
    global retry_queue
    current_time = time.time()

    # Process items ready for retry
    ready_items = []
    remaining_items = []

    for item in retry_queue:
        if current_time >= item["next_retry_at"]:
            ready_items.append(item)
        else:
            remaining_items.append(item)

    retry_queue = remaining_items

    # Process ready items
    for item in ready_items:
        success, status = trigger(item["kind"], item["path"])

        if success:
            log_event(
                "retry_success",
                path=item["path"],
                kind=item["kind"],
                attempt=item["attempt"],
            )
        else:
            # Schedule next retry or mark as failed
            item["attempt"] += 1
            if item["attempt"] <= 5:
                # Exponential backoff: 1s, 4s, 10s, 30s (capped)
                delays = [1, 4, 10, 30, 30]
                delay = delays[min(item["attempt"] - 1, len(delays) - 1)]
                item["next_retry_at"] = current_time + delay
                retry_queue.append(item)

                log_event(
                    "retry_scheduled",
                    path=item["path"],
                    kind=item["kind"],
                    attempt=item["attempt"],
                    delay=delay,
                )
            else:
                log_event(
                    "retry_failed",
                    level="error",
                    path=item["path"],
                    kind=item["kind"],
                    attempt=item["attempt"],
                )


def load_state():
    """Load watcher state from file."""
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
        return state.get("seen", {}), state.get("retry_queue", [])
    except Exception:
        return {}, []


def save_state(seen, retry_queue):
    """Save watcher state to file."""
    try:
        Path(STATE_FILE).parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE + ".tmp"
        state = {"seen": seen, "retry_queue": retry_queue}
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        log_event("save_state_failed", level="error", error=str(e))


def main():
    """Main watcher loop with stability gate and retry logic."""
    global retry_queue

    seen, retry_queue = load_state()
    base = Path(DROPZONE)

    log_event(
        "watcher_start",
        level="info",
        dropzone=str(base.resolve()),
        worker_base=WORKER_BASE,
        stable_passes=STABLE_PASSES,
    )

    print(f"[watcher] watching {base.resolve()} -> {WORKER_BASE}")

    def handle_sig(*_):
        """Handle shutdown signals."""
        log_event("watcher_shutdown", level="info")
        save_state(seen, retry_queue)
        print("[watcher] saved state and exiting")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    while True:
        try:
            # Process retry queue
            process_retry_queue()

            # Scan for new/changed files
            for p in base.rglob("*"):
                if not p.is_file():
                    continue
                sig = file_sig(p)
                if not sig:
                    continue
                abs_path = str(p.resolve())
                rel_path = abs_path
                if STRIP_PREFIX and rel_path.startswith(STRIP_PREFIX):
                    rel_path = rel_path[len(STRIP_PREFIX) :]
                rel_norm = rel_path.replace("\\", "/")
                if REQUIRE_PREFIX and not rel_norm.startswith(REQUIRE_PREFIX):
                    print(
                        json.dumps(
                            {
                                "ts": time.strftime(
                                    "%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()
                                ),
                                "level": "warn",
                                "subsystem": "watcher",
                                "event": "path_rejected",
                                "path": abs_path,
                                "rel": rel_norm,
                                "reason": "prefix_mismatch",
                            }
                        )
                    )
                    # Do NOT enqueue retries for rejects
                    continue
                key = abs_path  # state key stays absolute
                if seen.get(key) == sig:
                    continue
                k = kind_for(p)
                seen[key] = sig
                if k:
                    ok, status = trigger(k, rel_norm)
                    if not ok:
                        # Only real failures should retry (existing backoff queue, if present).
                        pass
                else:
                    print(f"[watcher] skip (unknown kind): {key}")

            # Periodically save state
            save_state(seen, retry_queue)
            time.sleep(INTERVAL)

        except Exception as e:
            log_event("scan_error", level="error", error=str(e))
            time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
