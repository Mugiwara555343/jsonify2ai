from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


# This file lives at: repo/scripts/dev/tools/smoke_precommit.py
# Repo root is therefore parents[3]:
# tools -> dev -> scripts -> repo
ROOT = Path(__file__).resolve().parents[3]

TOOLS = ROOT / "scripts" / "dev" / "tools"
INGEST = TOOLS / "ingest_dropzone.py"
DIAGNOSE = TOOLS / "ingest_diagnose.py"


def _run_ok(cmd: list[str]) -> None:
    env = os.environ.copy()
    subprocess.run(cmd, check=True, cwd=str(ROOT), env=env)


def main() -> None:
    # basic "help + discovery" smoke for canonical dev scripts
    _run_ok([sys.executable, str(INGEST), "--help"])
    _run_ok([sys.executable, str(DIAGNOSE), "--help"])
    print("smoke_precommit OK")


if __name__ == "__main__":
    main()
