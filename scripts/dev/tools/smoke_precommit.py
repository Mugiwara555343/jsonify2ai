#!/usr/bin/env python3
"""Canonical dev smoke test - validates repo health with pre-commit and unit tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


# This file lives at: repo/scripts/dev/tools/smoke_precommit.py
# Repo root is therefore parents[3]: tools -> dev -> scripts -> repo
ROOT = Path(__file__).resolve().parents[3]

# Timeout for subprocess commands (seconds) to prevent indefinite hangs
SUBPROCESS_TIMEOUT = 120


def in_precommit() -> bool:
    """Check if we are running inside a pre-commit hook."""
    return os.environ.get("PRE_COMMIT") == "1"


def run_check(cmd: list[str], description: str) -> dict[str, str | bool]:
    """Run a command and return result summary."""
    print(f"\n{'=' * 60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'=' * 60}")

    try:
        subprocess.run(cmd, check=True, cwd=str(ROOT), timeout=SUBPROCESS_TIMEOUT)
        print(f"[PASS] {description}")
        return {"check": description, "status": "PASS", "passed": True}
    except subprocess.CalledProcessError as e:
        print(f"[FAIL] {description} (exit code {e.returncode})")
        return {"check": description, "status": "FAIL", "passed": False}
    except subprocess.TimeoutExpired:
        print(f"[FAIL] {description} (timeout after {SUBPROCESS_TIMEOUT}s)")
        return {"check": description, "status": "FAIL", "passed": False}


def main() -> None:
    """Run canonical smoke checks and output JSON summary."""
    print("=" * 60)
    print("CANONICAL DEV SMOKE TEST")
    print("=" * 60)

    results = []

    # 1. Run pre-commit on all files (skip if already inside pre-commit to avoid recursion)
    if in_precommit():
        print(f"\n{'=' * 60}")
        print("Running: pre-commit run --all-files")
        print("- SKIPPED: running inside pre-commit hook (avoiding recursion)")
        print(f"{'=' * 60}")
        results.append(
            {
                "check": "pre-commit run --all-files",
                "status": "SKIP",
                "passed": True,
                "message": "skipped: running inside pre-commit",
            }
        )
    else:
        results.append(
            run_check(
                ["pre-commit", "run", "--all-files"], "pre-commit run --all-files"
            )
        )

    # 2. Run basic unit test
    results.append(
        run_check(
            [
                "pytest",
                "-q",
                "worker/tests/test_parse_transcript_unit.py::TestParseTranscript::test_parse_transcript_basic",
            ],
            "pytest (basic unit test)",
        )
    )

    # Output JSON summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    summary = {
        "checks": results,
        "total": len(results),
        "passed": sum(1 for r in results if r["passed"]),
        "failed": sum(1 for r in results if not r["passed"]),
    }
    print(json.dumps(summary, indent=2))

    # Exit with failure if any check failed
    if summary["failed"] > 0:
        sys.exit(1)

    print("\n[OK] All smoke checks passed!")


if __name__ == "__main__":
    main()
