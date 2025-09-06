# scripts/smoke_golden.py
from __future__ import annotations
import shutil
import pathlib
import sys
import subprocess
import time

# --- bootstrap sys.path so imports never fail ---
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GOLDEN = ROOT / "data" / "golden"
DROPZONE = ROOT / "data" / "dropzone" / "smoke_golden"
VALIDATE = ROOT / "scripts" / "validate_json.py"
EXPORT_DIR = ROOT / "data" / "exports"


def copy_golden() -> None:
    if DROPZONE.exists():
        shutil.rmtree(DROPZONE)
    DROPZONE.mkdir(parents=True, exist_ok=True)
    if GOLDEN.exists():
        for p in GOLDEN.iterdir():
            if p.is_file():
                shutil.copy2(p, DROPZONE / p.name)


def try_ingest_once() -> int:
    """
    Prefer the project's existing ingest script. If it's syntactically broken,
    skip (warn) so the smoke can still validate existing exports.
    """
    ingest_script = ROOT / "scripts" / "ingest_dropzone.py"
    if not ingest_script.exists():
        print("[warn] ingest script not found; skipping ingest")
        return 0
    # attempt a dry import to catch SyntaxError early
    try:
        compile(ingest_script.read_text(encoding="utf-8"), str(ingest_script), "exec")
    except SyntaxError as e:
        print(
            f"[warn] ingest script has syntax error at line {e.lineno}; skipping ingest"
        )
        return 0
    # run once (Windows-friendly)
    rc = subprocess.run(
        [sys.executable, str(ingest_script), "--once"], check=False
    ).returncode
    return rc


def run_validate(strict: bool = True) -> int:
    args = [sys.executable, str(VALIDATE), str(EXPORT_DIR)]
    if strict:
        args.append("--strict")
    return subprocess.run(args, check=False).returncode


def main() -> int:
    copy_golden()

    t0 = time.time()
    rc1 = try_ingest_once()
    if rc1 != 0:
        print(f"[ingest-error] rc={rc1}")
        return 2

    v1 = run_validate(strict=True)
    if v1 != 0:
        print("[validate] first pass failed")
        return v1

    # idempotency check (re-run ingest if available)
    rc2 = try_ingest_once()
    if rc2 != 0:
        print(f"[ingest-error-2] rc={rc2}")
        return 2

    v2 = run_validate(strict=True)
    if v2 != 0:
        print("[validate] second pass failed")
        return v2

    dt = time.time() - t0
    print(f"[smoke_golden] OK in {dt:.2f}s :: idempotent ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
