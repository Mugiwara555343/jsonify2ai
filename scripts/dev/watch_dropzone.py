# scripts/watch_dropzone.py (top-of-file only)
from __future__ import annotations

import json
import os
import sys
import time
import hashlib
import threading
from pathlib import Path
from subprocess import CalledProcessError, run

# sys.path bootstrap must come AFTER __future__ and BEFORE local imports
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# --- Tunables (env overrides) -----------------------------------------------
DEBOUNCE_SEC = float(os.getenv("WATCH_DEBOUNCE_SEC", "0.6"))  # min gap between runs
STABLE_PROBE_MS = int(os.getenv("WATCH_STABLE_PROBE_MS", "300"))  # size-stability probe
STABLE_TRIES = int(os.getenv("WATCH_STABLE_TRIES", "3"))  # consecutive matches

DROPZONE = Path(os.getenv("DROPZONE_DIR", "data/dropzone"))
EXPORT = Path(os.getenv("EXPORT_JSONL", "data/exports/ingest.jsonl"))
PYTHONPATH = os.getenv("PYTHONPATH", "worker")

STATE_FILE = Path(os.getenv("WATCH_STATE_FILE", "data/.ingest_state.json"))

IGNORE_SUFFIXES = (".tmp", ".part", ".crdownload")
IGNORE_NAMES = {".DS_Store", "Thumbs.db"}
IGNORE_PREFIXES = ("~$",)


# --- Qdrant helpers ----------------------------------------------------------
def _qdrant_delete_by_doc_id(document_id: str) -> bool:
    """
    Best-effort deletion using our worker services directly (no HTTP).
    """
    try:
        # Lazy imports so watcher runs even if worker isn't on PYTHONPATH yet
        from worker.app.services.qdrant_client import (
            get_qdrant_client,
            delete_by_document_id,
        )

        client = get_qdrant_client()
        _ = delete_by_document_id(document_id, client=client)
        return True
    except Exception as e:
        print(f"[watch] delete failed for doc={document_id}: {e}")
        return False


# --- State (path -> {document_id, last_hash}) --------------------------------
def _load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _sha256_bytes(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _document_id_for_file(p: Path) -> str:
    # deterministic, rename-proof: uuid5(NAMESPACE, sha256(file_bytes))
    from uuid import uuid5

    try:
        from worker.app.config import settings

        namespace = settings.NAMESPACE_UUID
    except Exception:
        from uuid import UUID

        # fallback seed; consider setting NAMESPACE_SEED in .env for determinism
        namespace = UUID("2b00c5a8-0ec2-4f1f-9c7e-3f7b7c0f8a77")
    return str(uuid5(namespace, _sha256_bytes(p)))


def _rebuild_state_from_fs() -> dict:
    state: dict = {}
    if not DROPZONE.exists():
        return state
    for fp in DROPZONE.rglob("*"):
        if not fp.is_file():
            continue
        if _should_ignore(str(fp)):
            continue
        try:
            h = _sha256_bytes(fp)
            state[str(fp)] = {"document_id": _doc_id_from_hash(h), "last_hash": h}
        except Exception:
            # best effort
            pass
    _save_state(state)
    return state


def _doc_id_from_hash(h: str) -> str:
    from uuid import uuid5, UUID

    try:
        from worker.app.config import settings

        ns = settings.NAMESPACE_UUID
    except Exception:
        ns = UUID("2b00c5a8-0ec2-4f1f-9c7e-3f7b7c0f8a77")
    return str(uuid5(ns, h))


# --- Utilities ---------------------------------------------------------------
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
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)


def _is_stable(p: Path) -> bool:
    """
    A file is 'stable' when its size stays unchanged for STABLE_TRIES probes.
    """
    last = -1
    for _ in range(STABLE_TRIES):
        try:
            cur = p.stat().st_size
        except FileNotFoundError:
            return False
        if cur == last:
            pass_count = _ + 1
        else:
            pass_count = 1
        last = cur
        if pass_count >= STABLE_TRIES:
            return True
        time.sleep(STABLE_PROBE_MS / 1000.0)
    return False


_ingest_lock = threading.Lock()
_last_run = 0.0


def _run_ingest_full() -> int:
    """
    Call scripts/dev/ingest_dropzone.py for the entire folder (simple & consistent).
    """
    env = os.environ.copy()
    env["PYTHONPATH"] = PYTHONPATH
    cmd = [
        sys.executable,
        "scripts/dev/ingest_dropzone.py",
        "--dir",
        str(DROPZONE),
        "--export",
        str(EXPORT),
        "--replace-existing",
    ]
    try:
        cp = run(cmd, env=env, check=False)
        return cp.returncode
    except CalledProcessError as e:
        print(f"[watch] ingest error: {e}")
        return e.returncode


def _throttled_ingest():
    global _last_run
    now = time.time()
    if now - _last_run < DEBOUNCE_SEC:
        return
    if not _ingest_lock.acquire(blocking=False):
        return
    try:
        print("[watch] ingest starting …")
        rc = _run_ingest_full()
        print(f"[watch] ingest done rc={rc}")
        _last_run = time.time()
        # After a full ingest, refresh state map based on current files
        _rebuild_state_from_fs()
    finally:
        _ingest_lock.release()


def _handle_delete(path: str, state: dict):
    """
    On delete, remove the document's points from Qdrant using the last known mapping.
    """
    entry = state.pop(path, None)
    if not entry:
        # Unknown path: nothing to do
        return
    doc_id = entry.get("document_id")
    if not doc_id:
        return
    ok = _qdrant_delete_by_doc_id(doc_id)
    if ok:
        print(f"[watch] deleted index for doc={doc_id} (path was {path})")
    _save_state(state)


# --- Watch loop --------------------------------------------------------------
def _watch_with_watchdog():
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
            self.state = _load_state()

        def _on_change(self, p: str, kind: str):
            if _should_ignore(p):
                return
            fp = Path(p)
            if kind in ("created", "modified", "moved"):
                if fp.exists() and _is_stable(fp):
                    print(f"[watch] change detected: {kind} -> {p}")
                    _throttled_ingest()
            elif kind == "deleted":
                print(f"[watch] change detected: {kind} -> {p}")
                _handle_delete(p, self.state)

        def on_created(self, event):
            if not event.is_directory:
                self._on_change(event.src_path, "created")

        def on_modified(self, event):
            if not event.is_directory:
                self._on_change(event.src_path, "modified")

        def on_moved(self, event):
            if not event.is_directory:
                # treat as a change (ingest) and also remove old mapping
                self._on_change(event.dest_path, "moved")
                _handle_delete(event.src_path, self.state)

        def on_deleted(self, event):
            if not event.is_directory:
                self._on_change(event.src_path, "deleted")

    _ensure_dirs()
    print(
        f"[watch] watching {DROPZONE.resolve()} (debounce={DEBOUNCE_SEC}s, stable={STABLE_TRIES}x{STABLE_PROBE_MS}ms)"
    )
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


def main():
    # Prefer watchfiles if you ever want to switch; for now we keep watchdog to match your env.
    _watch_with_watchdog()


if __name__ == "__main__":
    main()
