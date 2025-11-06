import os
import time
import json
from pathlib import Path
import requests


def read_env(path: str = ".env"):
    env = {}
    if not os.path.exists(path):
        return env
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def mask(token: str | None):
    if not token:
        return ""
    return token[:4] + "..." + token[-4:]


def main():
    env = read_env()
    api_base = os.getenv("API_BASE", "http://localhost:8082")
    worker_base = os.getenv("WORKER_URL", "http://localhost:8090")
    api_token = env.get("API_AUTH_TOKEN", os.getenv("API_AUTH_TOKEN", ""))
    worker_token = env.get("WORKER_AUTH_TOKEN", os.getenv("WORKER_AUTH_TOKEN", ""))
    qdrant_url = env.get("QDRANT_URL", os.getenv("QDRANT_URL", "http://localhost:6333"))

    drop = Path("data/dropzone")
    drop.mkdir(parents=True, exist_ok=True)
    test_path = drop / "diag_upload.md"
    test_path.write_text(
        "diagnose upload\nvector manifest.json EMBED_DEV_MODE\n", encoding="utf-8"
    )

    summary = {
        "api_upload_ok": False,
        "worker_process_ok": False,
        "status_counts": None,
        "search_hits": {
            "vector": False,
            "manifest.json": False,
            "EMBED_DEV_MODE": False,
        },
        "qdrant_points_count": None,
        "inferred_issue": None,
    }

    # 1) API upload (multipart)
    try:
        files = {"file": (test_path.name, open(test_path, "rb"), "text/markdown")}
        headers = {"Authorization": f"Bearer {api_token}"} if api_token else {}
        r = requests.post(
            f"{api_base}/upload", files=files, headers=headers, timeout=30
        )
        if r.status_code in (401, 403):
            summary["inferred_issue"] = "missing_api_token"
        r.raise_for_status()
        summary["api_upload_ok"] = True
    except Exception:
        pass

    # 2) Worker process fallback
    try:
        headers = (
            {
                "Authorization": f"Bearer {worker_token}",
                "Content-Type": "application/json",
            }
            if worker_token
            else {"Content-Type": "application/json"}
        )
        body = {
            "kind": "text",
            "path": str(test_path),
            "text": test_path.read_text(encoding="utf-8"),
        }
        r = requests.post(
            f"{worker_base}/process/text",
            data=json.dumps(body),
            headers=headers,
            timeout=30,
        )
        if r.status_code in (401, 403) and not summary.get("inferred_issue"):
            summary["inferred_issue"] = "auth_worker_missing"
        if r.ok:
            summary["worker_process_ok"] = True
    except Exception:
        pass

    # 3) Poll worker status for counts increase
    counts = None
    try:
        t0 = time.time()
        while time.time() - t0 < 20:
            s = requests.get(f"{worker_base}/status", timeout=5).json()
            counts = s.get("counts")
            if counts and counts.get("total", 0) > 0:
                break
            time.sleep(2)
    except Exception:
        pass
    summary["status_counts"] = counts or {}

    # 4) API searches (require token)
    try:
        headers = {"Authorization": f"Bearer {api_token}"} if api_token else {}
        for term in ["vector", "manifest.json", "EMBED_DEV_MODE"]:
            rr = requests.get(
                f"{api_base}/search",
                params={"kind": "text", "q": term, "limit": 1},
                headers=headers,
                timeout=15,
            )
            if rr.status_code in (401, 403) and not summary.get("inferred_issue"):
                summary["inferred_issue"] = "search_auth_missing"
            if rr.ok:
                data = rr.json()
                summary["search_hits"][term] = bool(data.get("results"))
    except Exception:
        pass

    # 5) Qdrant points count (best-effort)
    try:
        qq = requests.get(f"{qdrant_url}/collections/jsonify2ai_chunks_768", timeout=5)
        if qq.ok:
            summary["qdrant_points_count"] = (
                qq.json().get("result", {}).get("points_count")
            )
    except Exception:
        pass

    # 6) Infer final issue if unset
    if not summary.get("inferred_issue"):
        if not api_token and not summary["api_upload_ok"]:
            summary["inferred_issue"] = "missing_api_token"
        elif (counts or {}).get("total", 0) == 0 and not summary["worker_process_ok"]:
            summary["inferred_issue"] = "qdrant_empty"
        elif any(summary["search_hits"].values()):
            summary["inferred_issue"] = "ok"
        else:
            summary["inferred_issue"] = "unknown"

    print(json.dumps(summary))


if __name__ == "__main__":
    main()
