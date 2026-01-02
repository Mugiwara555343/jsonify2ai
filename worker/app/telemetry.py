# worker/app/telemetry.py
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import logging

log = logging.getLogger(__name__)


class Telemetry:
    """
    Thread-safe telemetry singleton for worker service.

    Provides in-memory counters and structured JSON logging to data/logs/worker.jsonl.
    All operations are wrapped in try/except to ensure telemetry failures never crash the app.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._uptime_start = time.time()
        self._ingest_total = 0
        self._ingest_failed = 0
        self._watcher_triggers_total = 0
        self._export_total = 0
        self._ask_synth_total = 0
        self._last_error: Optional[str] = None

        # Log file configuration
        self._log_dir = Path("data/logs")
        self._log_file = self._log_dir / "worker.jsonl"
        self._max_log_mb = int(
            os.getenv("MAX_LOG_MB", os.getenv("WORKER_LOG_MAX_MB", "16"))
        )
        self._max_log_bytes = self._max_log_mb * 1024 * 1024

        # Ingest activity tracking
        self._ingest_activity_buffer: deque = deque(maxlen=100)  # Ring buffer
        self._ingest_activity_file = self._log_dir / "ingest_activity.jsonl"
        self._ingest_activity_max_bytes = self._max_log_bytes  # Same size limit

        # Ensure log directory exists
        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            log.warning(f"Failed to create log directory {self._log_dir}: {e}")

    def increment(self, counter_name: str) -> None:
        """Thread-safe counter increment."""
        try:
            with self._lock:
                if counter_name == "ingest_total":
                    self._ingest_total += 1
                elif counter_name == "ingest_failed":
                    self._ingest_failed += 1
                elif counter_name == "watcher_triggers_total":
                    self._watcher_triggers_total += 1
                elif counter_name == "export_total":
                    self._export_total += 1
                elif counter_name == "ask_synth_total":
                    self._ask_synth_total += 1
        except Exception as e:
            log.debug(f"Telemetry increment failed for {counter_name}: {e}")

    def set_error(self, error: str) -> None:
        """Set the last error message."""
        try:
            with self._lock:
                self._last_error = str(error)
        except Exception as e:
            log.debug(f"Telemetry set_error failed: {e}")

    def log_json(self, event: str, level: str = "info", **fields: Any) -> None:
        """
        Write structured JSON log entry to worker.jsonl.

        Fields: ts, level, subsystem="worker", event, request_id, status, plus any kwargs.
        """
        try:
            # Prepare log entry
            log_entry = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "level": level,
                "subsystem": "worker",
                "event": event,
                **fields,
            }

            # Check if log rotation is needed
            self._maybe_rotate_log()

            # Write to log file
            with self._lock:
                with open(self._log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

        except Exception as e:
            log.debug(f"Telemetry log_json failed: {e}")

    def _maybe_rotate_log(self) -> None:
        """Rotate log file if it exceeds size limit (2-deep: .1, .2)."""
        try:
            if (
                self._log_file.exists()
                and self._log_file.stat().st_size > self._max_log_bytes
            ):
                log_file_2 = self._log_file.with_suffix(".jsonl.2")
                log_file_1 = self._log_file.with_suffix(".jsonl.1")

                # If .2 exists, delete it (oldest)
                if log_file_2.exists():
                    log_file_2.unlink()

                # If .1 exists, rename to .2
                if log_file_1.exists():
                    log_file_1.rename(log_file_2)

                # Rename current to .1
                self._log_file.rename(log_file_1)

                # Current file is now gone; next write will create a new one
        except Exception as e:
            log.warning(f"Log rotation failed: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get current telemetry statistics."""
        try:
            with self._lock:
                return {
                    "uptime_s": int(time.time() - self._uptime_start),
                    "ingest_total": self._ingest_total,
                    "ingest_failed": self._ingest_failed,
                    "watcher_triggers_total": self._watcher_triggers_total,
                    "export_total": self._export_total,
                    "ask_synth_total": self._ask_synth_total,
                    "last_error": self._last_error,
                }
        except Exception as e:
            log.debug(f"Telemetry get_stats failed: {e}")
            return {
                "uptime_s": 0,
                "ingest_total": 0,
                "ingest_failed": 0,
                "watcher_triggers_total": 0,
                "export_total": 0,
                "ask_synth_total": 0,
                "last_error": None,
            }

    def record_ingest_activity(
        self,
        *,
        path: str,
        filename: str,
        kind: str,
        status: str,
        reason: str,
        chunks: int = 0,
        images: int = 0,
        bytes: int = 0,
        started_at: Optional[str] = None,
        finished_at: Optional[str] = None,
        activity_id: Optional[str] = None,
    ) -> str:
        """
        Record an ingest activity event.

        Returns the activity_id (newly generated if not provided).
        """
        try:
            activity_id = activity_id or str(uuid.uuid4())
            now_iso = datetime.now(timezone.utc).isoformat()

            record = {
                "id": activity_id,
                "path": path,
                "filename": filename,
                "kind": kind,
                "status": status,
                "reason": reason,
                "chunks": chunks,
                "images": images,
                "bytes": bytes,
                "started_at": started_at or now_iso,
                "finished_at": finished_at
                or (now_iso if status != "processing" else None),
            }

            # Add to ring buffer
            with self._lock:
                self._ingest_activity_buffer.append(record)

            # Append to JSONL file
            self._maybe_rotate_ingest_activity_log()
            try:
                with self._lock:
                    with open(self._ingest_activity_file, "a", encoding="utf-8") as f:
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
            except Exception as e:
                log.debug(f"Failed to write ingest activity to JSONL: {e}")

            return activity_id
        except Exception as e:
            log.debug(f"Telemetry record_ingest_activity failed: {e}")
            return activity_id or str(uuid.uuid4())

    def _maybe_rotate_ingest_activity_log(self) -> None:
        """Rotate ingest activity log file if it exceeds size limit (2-deep: .1, .2)."""
        try:
            if (
                self._ingest_activity_file.exists()
                and self._ingest_activity_file.stat().st_size
                > self._ingest_activity_max_bytes
            ):
                log_file_2 = self._ingest_activity_file.with_suffix(".jsonl.2")
                log_file_1 = self._ingest_activity_file.with_suffix(".jsonl.1")

                # If .2 exists, delete it (oldest)
                if log_file_2.exists():
                    log_file_2.unlink()

                # If .1 exists, rename to .2
                if log_file_1.exists():
                    log_file_1.rename(log_file_2)

                # Rename current to .1
                self._ingest_activity_file.rename(log_file_1)

                # Current file is now gone; next write will create a new one
        except Exception as e:
            log.warning(f"Ingest activity log rotation failed: {e}")

    def get_recent_activity(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent ingest activity records (trimmed for API response).

        Returns list of records with: id, filename, status, reason, chunks, images,
        started_at, finished_at, kind, path.
        """
        try:
            with self._lock:
                # Get latest N records (most recent last in deque)
                recent = list(self._ingest_activity_buffer)[-limit:]
                # Reverse to show most recent first
                recent.reverse()

                # Trim to essential fields
                trimmed = []
                for record in recent:
                    trimmed.append(
                        {
                            "id": record.get("id"),
                            "filename": record.get("filename"),
                            "status": record.get("status"),
                            "reason": record.get("reason"),
                            "chunks": record.get("chunks", 0),
                            "images": record.get("images", 0),
                            "started_at": record.get("started_at"),
                            "finished_at": record.get("finished_at"),
                            "kind": record.get("kind"),
                            "path": record.get("path"),
                        }
                    )
                return trimmed
        except Exception as e:
            log.debug(f"Telemetry get_recent_activity failed: {e}")
            return []


# Singleton instance
telemetry = Telemetry()
