#!/usr/bin/env python3
"""
jsonify2ai control panel (local CLI)

Goals:
- One entrypoint for the common flows:
    (A) ingest drop-zone -> JSONL + Qdrant
    (B) ask -> retrieval (+ optional LLM via Ollama)
    (C) peek -> sample vectors & payloads
    (D) reset -> recreate or rename collection safely

Requirements:
- `qdrant-client` installed
- Working .env or process env with the fields below
"""

from __future__ import annotations
import argparse
import json
import os
import sys
import uuid
import textwrap
from pathlib import Path
from typing import Optional

# Local imports from the repo
# Allow running from repo root or examples/
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "worker") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "worker"))

# Import after path manipulation
try:
    from app.config import settings  # type: ignore
    from qdrant_client import QdrantClient, models  # type: ignore
except ImportError:
    # Fallback if imports fail
    settings = None
    QdrantClient = None
    models = None

# Script paths
INGEST_SCRIPT = REPO_ROOT / "scripts" / "ingest_dropzone.py"
ASK_SCRIPT = REPO_ROOT / "examples" / "ask_local.py"


def _print_header(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def _ensure_paths() -> None:
    (REPO_ROOT / "data" / "dropzone").mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / "data" / "exports").mkdir(parents=True, exist_ok=True)


def _env(k: str, default: Optional[str] = None) -> str:
    return os.getenv(k, default or "")


def _dev_flags() -> dict[str, str]:
    # Respect current .env/dev toggles
    return {
        "EMBED_DEV_MODE": _env("EMBED_DEV_MODE", "1"),
        "AUDIO_DEV_MODE": _env("AUDIO_DEV_MODE", "1"),
        "EMBEDDING_DIM": _env("EMBEDDING_DIM", "768"),
        "QDRANT_URL": _env("QDRANT_URL", settings.QDRANT_URL),
        "OLLAMA_URL": _env("OLLAMA_URL", settings.OLLAMA_URL),
        "QDRANT_COLLECTION": _env("QDRANT_COLLECTION", settings.QDRANT_COLLECTION),
    }


def _run_py(cmd: list[str]) -> int:
    """Run a python module/script through current interpreter."""
    import subprocess

    proc = subprocess.Popen(cmd, cwd=str(REPO_ROOT))
    return proc.wait()


# ------------------------ Actions ------------------------


def action_ingest(args: argparse.Namespace) -> None:
    _print_header("Ingest → embed → upsert")
    _ensure_paths()
    drop = args.dir or "data/dropzone"
    out = args.export or "data/exports/ingest.jsonl"
    reset = args.reset

    env = os.environ.copy()
    env.update(_dev_flags())  # keep your dev-mode defaults

    # Build command
    cmd = [
        sys.executable,
        str(INGEST_SCRIPT),
        "--dir",
        drop,
        "--export",
        out,
    ]
    if reset:
        cmd += ["--reset-collection"]
    if getattr(args, "recreate_bad_collection", False):
        cmd += ["--recreate-bad-collection"]

    print(
        "Env:",
        {
            k: env[k]
            for k in [
                "QDRANT_URL",
                "QDRANT_COLLECTION",
                "EMBED_DEV_MODE",
                "AUDIO_DEV_MODE",
                "EMBEDDING_DIM",
            ]
        },
    )
    print("Cmd:", " ".join(cmd))
    rc = _run_py(cmd)
    if rc != 0:
        sys.exit(rc)

    # Quick summary
    p = Path(out)
    if p.exists():
        import collections

        cnt_by_path = collections.Counter()
        with p.open("r", encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                cnt_by_path[rec["path"]] += 1
        print("\nTop files:")
        for path, n in cnt_by_path.most_common(10):
            print(f"  {path} -> {n}")
    else:
        print("No JSONL found (nothing to ingest?).")


def action_ask(args: argparse.Namespace) -> None:
    _print_header("Ask (retrieval ± LLM)")
    q = args.query
    if not q:
        print("Provide a question with --q '...'.")
        sys.exit(2)

    env = os.environ.copy()
    env.update(_dev_flags())

    # Always run retrieval; optionally add LLM
    cmd = [
        sys.executable,
        str(ASK_SCRIPT),
        "--q",
        q,
        "--k",
        str(args.k),
    ]
    if args.llm:
        cmd += ["--llm", "--model", args.model]

    if args.show_sources:
        cmd += ["--show-sources"]

    print("Cmd:", " ".join(cmd))
    rc = _run_py(cmd)
    sys.exit(rc)


def action_peek(_: argparse.Namespace) -> None:
    _print_header("Peek (Qdrant sample)")
    env = _dev_flags()
    c = QdrantClient(url=env["QDRANT_URL"])
    col = env["QDRANT_COLLECTION"]
    try:
        pts, _ = c.scroll(col, limit=5)
    except Exception as e:
        print("Scroll failed:", e)
        sys.exit(1)

    print(f"Collection: {col}")
    print(f"Sample count: {len(pts)}")
    for p in pts:
        pay = getattr(p, "payload", {}) or {}
        print("-", {k: pay.get(k) for k in ("path", "idx", "text", "source_ext")})


def action_reset(args: argparse.Namespace) -> None:
    _print_header("Reset collection")
    env = _dev_flags()
    c = QdrantClient(url=env["QDRANT_URL"])
    col = env["QDRANT_COLLECTION"]
    dim = int(env["EMBEDDING_DIM"])

    if args.rename:
        new_name = f"{col}_{uuid.uuid4().hex[:6]}"
        print(f"Renaming collection: {col} → {new_name}")
        try:
            c.rename_collection(col, new_name)
            # then create fresh
            c.create_collection(
                collection_name=col,
                vectors_config=models.VectorParams(
                    size=dim, distance=models.Distance.COSINE
                ),
            )
            print("Fresh collection created.")
        except Exception as e:
            print("Reset (rename) failed:", e)
            sys.exit(1)
    else:
        ans = input(f"Type the collection name '{col}' to confirm deletion: ").strip()
        if ans != col:
            print("Aborted.")
            return
        try:
            c.delete_collection(col)
            c.create_collection(
                collection_name=col,
                vectors_config=models.VectorParams(
                    size=dim, distance=models.Distance.COSINE
                ),
            )
            print("Collection recreated.")
        except Exception as e:
            print("Reset failed:", e)
            sys.exit(1)


def action_watch(args: argparse.Namespace) -> None:
    _print_header("Watch dropzone for changes")
    _ensure_paths()
    drop = args.dir or "data/dropzone"
    out = args.export or "data/exports/ingest.jsonl"

    env = os.environ.copy()
    env.update(_dev_flags())  # keep your dev-mode defaults
    env["PYTHONPATH"] = str(REPO_ROOT / "worker")

    # Build command
    cmd = [sys.executable, str(REPO_ROOT / "scripts" / "watch_dropzone.py")]

    print(
        "Env:",
        {
            k: env[k]
            for k in [
                "QDRANT_URL",
                "QDRANT_COLLECTION",
                "EMBED_DEV_MODE",
                "AUDIO_DEV_MODE",
                "EMBEDDING_DIM",
            ]
        },
    )
    print("Cmd:", " ".join(cmd))
    print(f"Watching: {drop} -> {out}")
    print("Press Ctrl+C to stop watching")

    rc = _run_py(cmd)
    if rc != 0:
        sys.exit(rc)


# ------------------------ CLI ------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="control_panel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent(
            """
        jsonify2ai: local control panel

        Examples:
          # ingest the drop-zone
          python examples/control_panel.py ingest --dir data/dropzone --export data/exports/ingest.jsonl

          # ask (retrieval only)
          python examples/control_panel.py ask --q "what's in the pdf?" --k 6 --show-sources

          # ask with LLM via Ollama (if available)
          python examples/control_panel.py ask --q "summarize the resume" --llm --model llama3.1 --k 6 --show-sources

          # peek into stored payloads
          python examples/control_panel.py peek

          # reset collection (with rename safety)
          python examples/control_panel.py reset --rename

          # watch dropzone for changes
          python examples/control_panel.py watch --dir data/dropzone --export data/exports/ingest.jsonl
        """
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("ingest", help="Ingest drop-zone")
    sp.add_argument("--dir", default="data/dropzone")
    sp.add_argument("--export", default="data/exports/ingest.jsonl")
    sp.add_argument(
        "--reset", action="store_true", help="Recreate collection before ingest"
    )
    sp.add_argument(
        "--recreate-bad-collection",
        action="store_true",
        help="If Qdrant collection has wrong/missing dim, drop & recreate it.",
    )
    sp.set_defaults(func=action_ingest)

    sp = sub.add_parser("ask", help="Ask a question")
    sp.add_argument("--q", dest="query", required=True)
    sp.add_argument("--k", type=int, default=6)
    sp.add_argument("--llm", action="store_true")
    sp.add_argument("--model", default="llama3.1")
    sp.add_argument("--show-sources", action="store_true")
    sp.set_defaults(func=action_ask)

    sp = sub.add_parser("peek", help="Sample stored payloads")
    sp.set_defaults(func=action_peek)

    sp = sub.add_parser("reset", help="Reset/rename the Qdrant collection")
    sp.add_argument(
        "--rename",
        action="store_true",
        help="Rename old collection then recreate fresh",
    )
    sp.set_defaults(func=action_reset)

    sp = sub.add_parser("watch", help="Watch dropzone for changes and auto-ingest")
    sp.add_argument("--dir", default="data/dropzone")
    sp.add_argument("--export", default="data/exports/ingest.jsonl")
    sp.set_defaults(func=action_watch)
    return p


def main() -> None:
    p = build_parser()
    args = p.parse_args()
    # Make PYTHONPATH=worker behavior implicit
    if str(REPO_ROOT / "worker") not in sys.path:
        sys.path.insert(0, str(REPO_ROOT / "worker"))
    args.func(args)


if __name__ == "__main__":
    main()
