# worker/app/telemetry.py
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

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


# Singleton instance
telemetry = Telemetry()
