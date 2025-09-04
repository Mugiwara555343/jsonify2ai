# worker/tests/conftest.py
from __future__ import annotations

# Import/bootstrap so "import app" works when running pytest from repo root
import os
import sys
import socket
from pathlib import Path
import pytest

TESTS_DIR = Path(__file__).resolve().parent  # .../worker/tests
WORKER_DIR = TESTS_DIR.parent  # .../worker
REPO_ROOT = WORKER_DIR.parent  # repo root

# Put worker dir first so "import app" resolves to worker/app
for p in (str(WORKER_DIR), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Fast, deterministic test defaults (keep heavy deps off the hot path)
# Your current effective env had EMBED_DEV_MODE=0 and AUDIO_DEV_MODE=1; force both to 1 for tests.
# QDRANT/OLLAMA default to localhost to avoid surprises.
os.environ.setdefault("EMBED_DEV_MODE", "1")
os.environ.setdefault("AUDIO_DEV_MODE", "1")
os.environ.setdefault("QDRANT_URL", os.getenv("QDRANT_URL", "http://localhost:6333"))
os.environ.setdefault("OLLAMA_URL", os.getenv("OLLAMA_URL", "http://localhost:11434"))


def _port_open(host: str, port: int, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _is_qdrant_up() -> bool:
    # Cheap reachability check to decide whether to collect Qdrant-dependent tests
    from urllib.parse import urlparse

    u = urlparse(os.environ.get("QDRANT_URL", "http://localhost:6333"))
    host = u.hostname or "localhost"
    port = u.port or (443 if u.scheme == "https" else 80)
    return _port_open(host, port)


QDRANT_AVAILABLE = _is_qdrant_up()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "qdrant: hits a running Qdrant instance")


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    # Auto-skip any tests that mention 'qdrant' in their nodeid if Qdrant isn't reachable.
    # Keeps local runs green without requiring the service, while still allowing them to run when up.
    if QDRANT_AVAILABLE:
        return
    skip = pytest.mark.skip(
        reason="Qdrant not reachable; set QDRANT_URL and start the service to run these tests"
    )
    for item in items:
        if "qdrant" in item.nodeid.lower():
            item.add_marker(skip)
