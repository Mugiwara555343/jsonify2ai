#!/usr/bin/env python3
import os
import sys
import json
import time
import tarfile
import subprocess
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SNAP_ROOT = ROOT / "snapshots"
ENV_FILE = ROOT / ".env"
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333").rstrip("/")
COLLECTION = os.getenv("QDRANT_COLLECTION", "jsonify2ai_chunks_768")


def run(cmd, check=True):
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"cmd failed: {' '.join(cmd)}\n{p.stdout}\n{p.stderr}")
    return p


def read_env():
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if not line or line.strip().startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def git_info():
    def safe(cmd):
        try:
            return run(cmd, check=False).stdout.strip()
        except Exception:
            return ""

    return {
        "tag": safe(["git", "describe", "--tags", "--abbrev=0"]),
        "commit": safe(["git", "rev-parse", "--short", "HEAD"]),
        "branch": safe(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
        "status": safe(["git", "status", "--porcelain"]),
    }


def qdrant_brief(out_dir: pathlib.Path):
    import requests

    info = {}
    try:
        r = requests.get(f"{QDRANT_URL}/collections/{COLLECTION}", timeout=10)
        if r.ok:
            info["collection_info"] = r.json()
        r = requests.post(
            f"{QDRANT_URL}/collections/{COLLECTION}/points/count",
            json={"exact": False},
            timeout=15,
        )
        if r.ok:
            info["approx_count"] = r.json()
    except Exception as e:
        info["error"] = str(e)
    (out_dir / "qdrant.info.json").write_text(
        json.dumps(info, indent=2), encoding="utf-8"
    )


def tar_data(dst_tar: pathlib.Path):
    def excluded(p: pathlib.Path) -> bool:
        pp = str(p).replace("\\", "/")
        return "/logs/" in pp or pp.endswith(".jsonl") or "/tmp/" in pp

    with tarfile.open(dst_tar, "w:gz") as tar:
        for p in DATA_DIR.rglob("*"):
            if p.is_dir():
                continue
            if excluded(p):
                continue
            tar.add(p, arcname=str(p.relative_to(ROOT)))


def main():
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out = SNAP_ROOT / ts
    out.mkdir(parents=True, exist_ok=True)

    manifest = {
        "created_at": ts,
        "qdrant_url": QDRANT_URL,
        "collection": COLLECTION,
        "git": git_info(),
        "env_subset": {
            k: v
            for k, v in read_env().items()
            if k
            in [
                "QDRANT_URL",
                "QDRANT_COLLECTION",
                "EMBED_DEV_MODE",
                "LLM_PROVIDER",
                "EMBED_PROVIDER",
            ]
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    try:
        qdrant_brief(out)
    except Exception as e:
        (out / "qdrant_export_error.txt").write_text(str(e), encoding="utf-8")

    dst_tar = out / "data_snapshot.tar.gz"
    tar_data(dst_tar)

    print(f"[snapshot] wrote: {out}")
    for p in out.iterdir():
        print(" -", p.name)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("[snapshot:error]", e)
        sys.exit(1)
