#!/usr/bin/env python
import sys
import subprocess
import tempfile
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
INGEST = ROOT / "scripts" / "ingest_dropzone.py"
REBUILD = ROOT / "scripts" / "full_pipeline_rebuild.py"


def _run_ok(cmd):
    subprocess.run(cmd, check=True, cwd=ROOT)


def _assert_no(patterns, path):
    text = path.read_text(encoding="utf-8")
    for p in patterns:
        if p in text:
            print(f"[smoke] forbidden pattern '{p}' found in {path}")
            sys.exit(1)


def main():
    # import-time safety: these should not crash
    _run_ok([sys.executable, str(INGEST), "--help"])
    _run_ok([sys.executable, str(REBUILD), "--help"])

    # discovery-only path (no DB/network)
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        _run_ok(
            [
                sys.executable,
                str(INGEST),
                "--dir",
                str(tmp),
                "--list-files",
                "--limit",
                "1",
            ]
        )

    # static checks: settings precedence only
    _assert_no(['os.getenv("AUDIO_DEV_MODE")', "os.getenv('AUDIO_DEV_MODE')"], INGEST)
    _assert_no(['os.getenv("EMBED_DEV_MODE")', "os.getenv('EMBED_DEV_MODE')"], INGEST)
    _assert_no(['os.getenv("AUDIO_DEV_MODE")', "os.getenv('AUDIO_DEV_MODE')"], REBUILD)
    _assert_no(['os.getenv("EMBED_DEV_MODE")', "os.getenv('EMBED_DEV_MODE')"], REBUILD)

    print("[smoke] ok")


if __name__ == "__main__":
    main()
