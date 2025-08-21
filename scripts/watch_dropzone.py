#!/usr/bin/env python
import os, time, subprocess, sys
from pathlib import Path

DEBOUNCE_SEC = float(os.getenv("WATCH_DEBOUNCE_SEC", "1.0"))
DROPZONE = Path(os.getenv("DROPZONE_DIR", "data/dropzone"))
EXPORT = Path(os.getenv("EXPORT_JSONL", "data/exports/ingest.jsonl"))
PYTHONPATH = os.getenv("PYTHONPATH", "worker")

def _ensure_dirs():
    DROPZONE.mkdir(parents=True, exist_ok=True)
    EXPORT.parent.mkdir(parents=True, exist_ok=True)

def _run_ingest():
    env = os.environ.copy()
    env["PYTHONPATH"] = PYTHONPATH
    cmd = [sys.executable, "scripts/ingest_dropzone.py", "--dir", str(DROPZONE), "--export", str(EXPORT)]
    return subprocess.call(cmd, env=env)

def main():
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except Exception:
        print("watchdrop: missing dependency 'watchdog'. Install with: pip install watchdog")
        sys.exit(1)

    class Handler(FileSystemEventHandler):
        def __init__(self):
            self._last = 0.0
        def on_any_event(self, event):
            now = time.time()
            if now - self._last < DEBOUNCE_SEC:  # simple debounce
                return
            self._last = now
            print(f"[watch] change detected: {event.event_type} -> {event.src_path}")
            rc = _run_ingest()
            print(f"[watch] ingest done rc={rc}")

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
        obs.stop(); obs.join()

if __name__ == "__main__":
    main()
