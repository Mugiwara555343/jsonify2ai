#!/usr/bin/env python3
"""
memory_watcher.py (Demo Version)

Watches current folder for changes to `.md` files
→ Auto-triggers parser from memory_parser.py
→ Creates `.parsed.json` in same folder
"""

import json
import time
import logging
import threading
from hashlib import md5
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# === LOCAL CONFIG ===
PROJECT_ROOT = Path(__file__).parent
MEMORY_DIR = PROJECT_ROOT
CONFIG_PATH = PROJECT_ROOT / "watch_config.json"

# === LOAD WATCH CONFIG ===
if CONFIG_PATH.exists():
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        WATCH_PATHS = [PROJECT_ROOT / s for s in cfg.get("watch_subfolders", [])]
    except Exception as e:
        print(f"[WARN] Failed to read watch_config.json: {e}")
        WATCH_PATHS = [PROJECT_ROOT]
else:
    WATCH_PATHS = [PROJECT_ROOT]

# === LOGGING ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("MemoryWatcher")

# === DEBOUNCE SETTINGS ===
DEBOUNCE_DELAY = 0.8
FILE_EXTS = {".md"}
last_hash = {}  # path → hash

# === IMPORT PARSER ===
from memory_parser import parse_md_file


class DebouncedHandler(FileSystemEventHandler):
    def __init__(self):
        super().__init__()
        self.timers = {}

    def on_any_event(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() not in FILE_EXTS:
            return
        if path.name.startswith((".", "~")) or ".parsed" in path.stem:
            return

        # debounce multiple events
        if path in self.timers:
            self.timers[path].cancel()

        timer = threading.Timer(DEBOUNCE_DELAY, self._process, args=[path])
        self.timers[path] = timer
        timer.start()

    def _process(self, path: Path):
        try:
            content = path.read_bytes()
        except Exception as e:
            logger.error(f"Failed to read {path.name}: {e}")
            return

        h = md5(content).hexdigest()
        if last_hash.get(path) == h:
            logger.info(f"↔ No content change: {path.name}")
            return
        last_hash[path] = h

        logger.info(f"🔄 Detected update: {path.name}")
        try:
            parsed = parse_md_file(path)
            out = path.with_suffix(".parsed.json")
            out.write_text(
                json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            logger.info(f"✅ Parsed → {out.name}")
        except Exception as e:
            logger.error(f"❌ Error parsing {path.name}: {e}", exc_info=True)


# === MAIN ===
def main():
    logger.info("👁️  Memory Watcher Starting")
    for p in WATCH_PATHS:
        logger.info(f"  • Watching: {p.relative_to(PROJECT_ROOT)}")

    observer = Observer()
    handler = DebouncedHandler()
    for p in WATCH_PATHS:
        observer.schedule(handler, str(p), recursive=True)

    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        logger.info("👋 Memory Watcher Stopped")
    observer.join()


if __name__ == "__main__":
    main()
