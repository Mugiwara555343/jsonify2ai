#!/usr/bin/env python3
"""
Snapshot the current jsonify2ai repo state into ./snapshots and generate STATE.md.

Run hints:
    PowerShell: python scripts\snapshot_state.py
    Git Bash : python scripts/snapshot_state.py

What it does (read-only, idempotent):
    1) Create ./snapshots/
         - git_files.txt, git_status.txt (if git present)
         - tree_full.txt (files), tree_dirs.txt (dirs-only)
         - python_probe.txt (cwd, PYTHONPATH, import resolution)
         - env_effective.json (merge of .env + current process env)
         - qdrant.collections.json (list)
         - qdrant.collection_info.json (schema/vectors for target collection)
         - qdrant.counts.json (per-kind counts: text/pdf/docx/audio/image/email if available)
         - qdrant.sample.json (a few points with id, path, kind, idx)
    2) Project maps at repo root:
         - project.map.json (all files with small text head + 128KiB head SHA1)
         - images.candidates.json (image-only subset)
    3) Generate/overwrite STATE.md from the actual snapshot (no hand edits required)

Notes:
    - No dependencies beyond the stdlib + 'requests' (install if needed).
    - If a subsystem is unreachable (git, qdrant), we capture the error and continue.
"""

from __future__ import annotations

import os
import sys
import io
import json
import re
import hashlib
import pathlib
import subprocess
import datetime as dt
from typing import Dict, Any, List, Tuple

# ---- soft dep: requests (used only for Qdrant)
try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None  # we will handle gracefully

# ---------- Paths / setup
ROOT = pathlib.Path(__file__).resolve().parents[1]  # repo root (../ from scripts/)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SNAP = ROOT / "snapshots"
SNAP.mkdir(parents=True, exist_ok=True)

# Alias for consistency with other entrypoints
REPO_ROOT = ROOT

# Load .env so entrypoint processes see repository defaults early (no-op if python-dotenv missing)
try:
    from dotenv import load_dotenv  # type: ignore

    dotenv_path = REPO_ROOT.joinpath(".env")
    if dotenv_path.exists():
        load_dotenv(dotenv_path=str(dotenv_path))
except Exception:
    # If python-dotenv isn't installed or load fails, fall back to system env (no crash)
    pass


# ---------- Helpers
def _now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _write_text(path: pathlib.Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _write_json(path: pathlib.Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def _run(
    cmd: List[str], cwd: pathlib.Path | None = None, timeout: int = 20
) -> Tuple[int, str, str]:
    """Run a command; return (code, stdout, stderr)."""
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            text=True,
            encoding="utf-8",
        )
        return proc.returncode, proc.stdout, proc.stderr
    except Exception as e:
        return 127, "", f"{type(e).__name__}: {e}"


# ---------- .env parsing (tiny, robust)
_ENV_LINE = re.compile(r"""^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$""")


def load_env_file(env_path: pathlib.Path) -> Dict[str, str]:
    env: Dict[str, str] = {}
    if not env_path.exists():
        return env
    for raw in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        m = _ENV_LINE.match(s)
        if not m:
            continue
        k, v = m.group(1), m.group(2)
        # strip surrounding quotes if present
        if (len(v) >= 2) and ((v[0] == v[-1] == '"') or (v[0] == v[-1] == "'")):
            v = v[1:-1]
        env[k] = v
    return env


def effective_env() -> Dict[str, str]:
    file_env = load_env_file(ROOT / ".env")
    eff = dict(file_env)
    # Overlay with the current process environment (session overrides .env)
    for k, v in os.environ.items():
        if k:
            eff[k] = v
    return eff


# ---------- Lightweight repo map (lifts approach from your repo scan utility)
IGNORE = re.compile(
    r"(\.git|node_modules|__pycache__|dist|build|\.venv|env|\.DS_Store)"
)
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
IS_WINDOWS = os.name == "nt"
RESERVED_WIN_BASENAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}


def is_reserved_windows_name(path_str: str) -> bool:
    if not IS_WINDOWS:
        return False
    stem = pathlib.Path(path_str).name.split(".")[0]
    return stem.upper() in RESERVED_WIN_BASENAMES


def posix_rel(p: pathlib.Path, start: pathlib.Path) -> str:
    try:
        rel = os.path.relpath(str(p), str(start))
    except ValueError:
        rel = str(p.resolve())
    return rel.replace("\\", "/")


def sha1_head(p: pathlib.Path, head_bytes: int = 128 * 1024) -> str:
    try:
        with p.open("rb") as f:
            data = f.read(head_bytes)
        return hashlib.sha1(data).hexdigest()
    except Exception:
        return "ERR"


def build_project_maps() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    records: List[Dict[str, Any]] = []
    image_records: List[Dict[str, Any]] = []

    for dp, dn, fn in os.walk(ROOT):
        if IGNORE.search(dp):
            continue
        dpp = pathlib.Path(dp)
        for name in fn:
            if IGNORE.search(name):
                continue
            p = dpp / name
            if is_reserved_windows_name(str(p)):
                continue

            try:
                size = p.stat().st_size
            except OSError:
                size = -1

            ext = p.suffix.lower()
            kind = "unknown"
            head = ""

            # Probe small files as text
            if size >= 0 and size <= 2 * 1024 * 1024:  # <= 2 MiB → try read as text
                try:
                    head = p.read_text(encoding="utf-8", errors="ignore")[:8000]
                    kind = "text" if head else "binary"
                except Exception:
                    kind = "binary"
                    head = ""

            # Extension-based override for images
            if ext in IMAGE_EXTS:
                kind = "image"

            rec = {
                "path": posix_rel(p.resolve(), ROOT),
                "ext": ext,
                "size": size,
                "sig": sha1_head(p),
                "head": head,
                "kind": kind,  # ← use computed kind directly (fixes F841 and is more explicit)
            }

            if kind == "image":
                image_records.append(
                    {
                        "path": rec["path"],
                        "ext": ext,
                        "size": size,
                        "sig": rec["sig"],
                        "kind": "image",
                    }
                )

            records.append(rec)

    return records, image_records


# ---------- Directory trees (portable)
def render_tree(root: pathlib.Path, files: bool = True) -> str:
    lines: List[str] = []
    prefix_stack: List[str] = []

    def walk(dir_path: pathlib.Path):
        # filter children
        children_dirs = sorted(
            [p for p in dir_path.iterdir() if p.is_dir() and not IGNORE.search(str(p))],
            key=lambda x: x.name.lower(),
        )
        children_files = sorted(
            [
                p
                for p in dir_path.iterdir()
                if p.is_file() and not IGNORE.search(p.name)
            ],
            key=lambda x: x.name.lower(),
        )

        entries = children_dirs + (children_files if files else [])
        for idx, entry in enumerate(entries):
            is_last = idx == len(entries) - 1
            branch = "└── " if is_last else "├── "
            lines.append("".join(prefix_stack) + branch + entry.name)
            if entry.is_dir():
                prefix_stack.append("    " if is_last else "│   ")
                walk(entry)
                prefix_stack.pop()

    lines.append(root.name)
    walk(root)
    return "\n".join(lines)


# ---------- Git snapshot (optional)
def snapshot_git():
    code, out, err = _run(["git", "ls-files"], cwd=ROOT)
    if code == 0:
        _write_text(SNAP / "git_files.txt", out)
    else:
        _write_text(SNAP / "git_files.txt", f"# git ls-files failed ({code})\n{err}")

    code, out, err = _run(["git", "status", "-sb"], cwd=ROOT)
    if code == 0:
        _write_text(SNAP / "git_status.txt", out)
    else:
        _write_text(SNAP / "git_status.txt", f"# git status -sb failed ({code})\n{err}")


# ---------- Python probe
def python_probe():
    import importlib.util  # local import

    buf = io.StringIO()
    buf.write(f"time: { _now_iso() }\n")
    buf.write(f"cwd: {str(ROOT)}\n")
    buf.write(f"PYTHONPATH: {os.environ.get('PYTHONPATH')}\n")
    buf.write(f"sys.executable: {sys.executable}\n")
    buf.write(f"sys.version: {sys.version}\n")
    buf.write("sys.path[:8]:\n")
    for p in sys.path[:8]:
        buf.write(f"  - {p}\n")
    try:
        spec = importlib.util.find_spec("worker.app.config")
        found = bool(spec)
        origin = getattr(spec, "origin", None) if spec else None
        buf.write(f"worker.app.config found?: {found} origin: {origin}\n")
    except Exception as e:
        buf.write(f"worker.app.config find_spec error: {type(e).__name__}: {e}\n")
    _write_text(SNAP / "python_probe.txt", buf.getvalue())


# ---------- Qdrant snapshot (optional, non-fatal)
def qdrant_snapshot(eff: Dict[str, str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"ok": False, "error": None}
    if requests is None:
        out["error"] = "requests not installed"
        return out

    base = eff.get("QDRANT_URL", "http://localhost:6333").rstrip("/")
    coll = eff.get("QDRANT_COLLECTION", "jsonify2ai_chunks")
    headers = {"Content-Type": "application/json"}

    try:
        r = requests.get(f"{base}/collections", timeout=8)
        r.raise_for_status()
        collections = r.json()
        _write_json(SNAP / "qdrant.collections.json", collections)
    except Exception as e:
        out["error"] = f"collections: {e}"
        _write_json(SNAP / "qdrant.collections.json", {"error": str(e)})
        return out

    try:
        r = requests.get(f"{base}/collections/{coll}", timeout=8)
        r.raise_for_status()
        coll_info = r.json()
        _write_json(SNAP / "qdrant.collection_info.json", coll_info)
    except Exception as e:
        _write_json(SNAP / "qdrant.collection_info.json", {"error": str(e)})

    # counts by kind (best-effort for common kinds)
    kinds = ["text", "pdf", "docx", "audio", "image", "email"]
    counts: Dict[str, Any] = {"collection": coll, "counts": {}, "errors": {}}
    for k in kinds:
        try:
            r = requests.post(
                f"{base}/collections/{coll}/points/count",
                json={
                    "exact": True,
                    "filter": {"must": [{"key": "kind", "match": {"value": k}}]},
                },
                headers=headers,
                timeout=8,
            )
            if r.ok:
                counts["counts"][k] = r.json().get("result", {}).get("count", 0)
            else:
                counts["errors"][k] = f"HTTP {r.status_code}"
        except Exception as e:
            counts["errors"][k] = str(e)

    # total count
    try:
        r = requests.post(
            f"{base}/collections/{coll}/points/count",
            json={"exact": True},
            headers=headers,
            timeout=8,
        )
        total = r.json().get("result", {}).get("count", 0) if r.ok else None
    except Exception as e:
        total = None
        counts["errors"]["_total"] = str(e)
    counts["total"] = total
    _write_json(SNAP / "qdrant.counts.json", counts)

    # sample a few points (id, path, kind, idx)
    try:
        r = requests.post(
            f"{base}/collections/{coll}/points/scroll",
            json={"limit": 5, "with_payload": True, "with_vectors": False},
            headers=headers,
            timeout=8,
        )
        sample = []
        if r.ok:
            res = r.json().get("result", {})
            for pt in res.get("points", []):
                payload = pt.get("payload", {}) or {}
                sample.append(
                    {
                        "id": pt.get("id"),
                        "path": payload.get("path"),
                        "kind": payload.get("kind"),
                        "idx": payload.get("idx"),
                        "document_id": payload.get("document_id"),
                        "meta_keys": sorted(list((payload.get("meta") or {}).keys())),
                    }
                )
        _write_json(SNAP / "qdrant.sample.json", {"collection": coll, "points": sample})
    except Exception as e:
        _write_json(SNAP / "qdrant.sample.json", {"error": str(e), "collection": coll})

    out["ok"] = True
    return out


# ---------- STATE.md generation (from snapshot & env)
def generate_state_md(eff: Dict[str, str]) -> str:
    coll = eff.get("QDRANT_COLLECTION", "jsonify2ai_chunks")
    embed_dim = eff.get("EMBEDDING_DIM") or eff.get("EMBED_DIM") or "768"
    embed_model = eff.get("EMBEDDINGS_MODEL", "nomic-embed-text")
    ask_mode = eff.get("ASK_MODE", "llm")
    ask_model = eff.get("ASK_MODEL", "")

    counts_path = SNAP / "qdrant.counts.json"
    counts = {}
    if counts_path.exists():
        try:
            counts = json.loads(counts_path.read_text(encoding="utf-8"))
        except Exception:
            counts = {}

    total = counts.get("total", "n/a")
    per_kind = counts.get("counts", {})

    # Known optional deps (quick heuristic: check importability)
    opt_deps = {
        "pypdf": _try_import("pypdf"),
        "python-docx": _try_import("docx"),
        "Pillow": _try_import("PIL"),
        "whisper / stt": _try_import("whisper") or _try_import("faster_whisper"),
    }

    lines = []
    lines.append(f"# STATE.md — {_now_iso()}")
    lines.append("")
    lines.append("## Scope today")
    active = []
    if opt_deps["pypdf"]:
        active.append("PDF")
    active.append("TXT/MD")
    if _truthy(eff.get("AUDIO_DEV_MODE")):
        lines.append("- Audio: dev-mode (skip or stub)")
    lines.append(f"- Active kinds: {', '.join(active)}")
    lines.append("")
    lines.append("## Models / Embedding")
    lines.append(f"- EMBEDDINGS_MODEL: `{embed_model}`")
    lines.append(f"- EMBEDDING_DIM: `{embed_dim}`")
    lines.append(f"- QDRANT_COLLECTION: `{coll}`")
    lines.append("")
    lines.append("## LLM Ask")
    lines.append(f"- ASK_MODE: `{ask_mode}`")
    lines.append(f"- ASK_MODEL: `{ask_model}`")
    lines.append(f"- OLLAMA_URL: `{eff.get('OLLAMA_URL', '')}`")
    lines.append("")
    lines.append("## Qdrant")
    lines.append(f"- Total points: **{total}**")
    if per_kind:
        pretty_kinds = ", ".join(f"{k}:{v}" for k, v in per_kind.items())
        lines.append(f"- Per kind: {pretty_kinds}")
    lines.append("")
    lines.append("## One-step smoke (host shell)")
    smoke_q = "Summarize Mauricio A Ventura's resume focus and strengths."
    smoke_cmd = (
        f'python examples\\ask_local.py --q "{smoke_q}" --k 6 --show-sources'
        + (" --llm" if ask_mode == "llm" else "")
    )
    if ask_model:
        smoke_cmd += f" --model {ask_model}"
    lines.append("```powershell")
    lines.append(smoke_cmd)
    lines.append("```")
    lines.append("")
    lines.append("## Known optional deps (import check)")
    for k, ok in opt_deps.items():
        lines.append(f"- {k}: {'OK' if ok else 'missing'}")
    lines.append("")
    lines.append(
        "> This file is auto-generated by scripts/snapshot_state.py — do not hand-edit."
    )
    return "\n".join(lines)


def _truthy(val: Any) -> bool:
    if isinstance(val, str):
        return val.strip().lower() in {"1", "true", "yes", "on"}
    return bool(val)


def _try_import(mod: str) -> bool:
    try:
        __import__(mod)
        return True
    except Exception:
        return False


# ---------- Main
def main() -> None:
    print(f"[snapshot] start @ {ROOT}")
    # 1) git snapshot
    snapshot_git()

    # 2) directory trees (portable)
    _write_text(SNAP / "tree_full.txt", render_tree(ROOT, files=True))
    _write_text(SNAP / "tree_dirs.txt", render_tree(ROOT, files=False))

    # 3) python probe
    try:
        python_probe()
    except Exception as e:
        _write_text(
            SNAP / "python_probe.txt", f"probe failed: {type(e).__name__}: {e}\n"
        )

    # 4) effective env (merge .env + session)
    eff = effective_env()
    _write_json(SNAP / "env_effective.json", {"generated_at": _now_iso(), "env": eff})

    # 5) qdrant snapshot (best-effort)
    qdr = qdrant_snapshot(eff)
    _write_json(SNAP / "qdrant.status.json", qdr)

    # 6) project maps at repo root (full + images subset)
    records, image_records = build_project_maps()
    _write_json(ROOT / "project.map.json", records)
    _write_json(ROOT / "images.candidates.json", image_records)

    # 7) generate STATE.md (root)
    state_md = generate_state_md(eff)
    _write_text(ROOT / "STATE.md", state_md)

    print("[snapshot] wrote:")
    print("  - snapshots/git_files.txt")
    print("  - snapshots/git_status.txt")
    print("  - snapshots/tree_full.txt")
    print("  - snapshots/tree_dirs.txt")
    print("  - snapshots/python_probe.txt")
    print("  - snapshots/env_effective.json")
    print("  - snapshots/qdrant.collections.json")
    print("  - snapshots/qdrant.collection_info.json")
    print("  - snapshots/qdrant.counts.json")
    print("  - snapshots/qdrant.sample.json")
    print("  - snapshots/qdrant.status.json")
    print("  - project.map.json")
    print("  - images.candidates.json")
    print("  - STATE.md")
    print("[snapshot] done.")


if __name__ == "__main__":
    main()
