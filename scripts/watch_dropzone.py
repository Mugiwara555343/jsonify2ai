#!/usr/bin/env python
import os
import time
import subprocess
import sys
from pathlib import Path

DEBOUNCE_SEC = float(os.getenv("WATCH_DEBOUNCE_SEC", "1.0"))
DROPZONE = Path(os.getenv("DROPZONE_DIR", "data/dropzone"))
EXPORT = Path(os.getenv("EXPORT_JSONL", "data/exports/ingest.jsonl"))
PYTHONPATH = os.getenv("PYTHONPATH", "worker")

# Ignore patterns for temp/noisy files
IGNORE_SUFFIXES = (".tmp", ".part", ".crdownload")
IGNORE_NAMES = {".DS_Store", "Thumbs.db"}
IGNORE_PREFIXES = ("~$",)  # Office temp files
_running = False


def _should_ignore(path: str) -> bool:
    name = os.path.basename(path)
    if name.startswith(".") or name in IGNORE_NAMES:
        return True
    if any(name.startswith(p) for p in IGNORE_PREFIXES):
        return True
    if any(name.endswith(s) for s in IGNORE_SUFFIXES):
        return True
    return False


def _ensure_dirs():
    DROPZONE.mkdir(parents=True, exist_ok=True)
    EXPORT.parent.mkdir(parents=True, exist_ok=True)


def _run_ingest():
    env = os.environ.copy()
    env["PYTHONPATH"] = PYTHONPATH
    cmd = [
        sys.executable,
        "scripts/ingest_dropzone.py",
        "--dir",
        str(DROPZONE),
        "--export",
        str(EXPORT),
    ]
    return subprocess.call(cmd, env=env)


def main():
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except Exception:
        print(
            "watchdrop: missing dependency 'watchdog'. Install with: pip install watchdog"
        )
        sys.exit(1)

    class Handler(FileSystemEventHandler):
        def __init__(self):
            self._last = 0.0

        def _maybe_ingest(self, p: str, kind: str):
            global _running
            if _should_ignore(p):
                return
            now = time.time()
            if now - self._last < DEBOUNCE_SEC:
                return
            if _running:
                return
            self._last = now
            _running = True
            try:
                print(f"[watch] change detected: {kind} -> {p}")
                rc = _run_ingest()
                print(f"[watch] ingest done rc={rc}")
            finally:
                _running = False

        def on_created(self, event):
            if not event.is_directory:
                self._maybe_ingest(event.src_path, "created")

        def on_modified(self, event):
            if not event.is_directory:
                self._maybe_ingest(event.src_path, "modified")

        def on_moved(self, event):
            if not event.is_directory:
                self._maybe_ingest(event.dest_path, "moved")

        # NOTE: intentionally ignore on_deleted

    _ensure_dirs()
    print(f"[watch] watching {DROPZONE.resolve()} (debounce={DEBOUNCE_SEC}s)")
    obs = Observer()
    obs.schedule(Handler(), str(DROPZONE), recursive=False)
    obs.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        obs.stop()
        obs.join()


if __name__ == "__main__":
    main()
