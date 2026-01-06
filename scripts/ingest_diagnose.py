import os
import sys
import time
import json
from pathlib import Path
import requests


def read_env(path: str = ".env") -> dict:
    env: dict[str, str] = {}
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


def mask(token: str | None) -> str:
    if not token:
        return ""
    if len(token) <= 8:
        return token
    return token[:4] + "..." + token[-4:]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"} if token else {}


def _json_headers(token: str) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def main() -> None:
    env = read_env()
    api_base = os.getenv("API_BASE", "http://localhost:8082")
    worker_base = os.getenv("WORKER_URL", "http://localhost:8090")
    api_token = env.get("API_AUTH_TOKEN", os.getenv("API_AUTH_TOKEN", ""))
    worker_token = env.get("WORKER_AUTH_TOKEN", os.getenv("WORKER_AUTH_TOKEN", ""))
    qdrant_url = env.get("QDRANT_URL", os.getenv("QDRANT_URL", "http://localhost:6333"))
    upload_fixtures = os.getenv("DIAGNOSE_UPLOAD_FIXTURES", "1") == "1"

    drop = Path("data/dropzone")
    drop.mkdir(parents=True, exist_ok=True)
    test_path = drop / "diag_upload.md"
    test_path.write_text(
        "diagnose upload\nvector manifest.json EMBED_DEV_MODE\n", encoding="utf-8"
    )

    summary: dict = {
        "api_upload_ok": False,
        "worker_process_ok": False,
        "status_counts": None,
        "search_hits": {
            "vector": False,
            "manifest.json": False,
            "EMBED_DEV_MODE": False,
        },
        "qdrant_points_count": None,
        "fixtures_uploaded": False,
        "inferred_issue": None,
    }

    # 1) API upload (multipart)
    try:
        with open(test_path, "rb") as f:
            files = {"file": (test_path.name, f, "text/markdown")}
            r = requests.post(
                f"{api_base}/upload",
                files=files,
                headers=_auth_headers(api_token),
                timeout=30,
            )
        if r.status_code in (401, 403):
            summary["inferred_issue"] = "missing_api_token"
            summary["api_upload_status"] = r.status_code
            try:
                error_data = r.json()
                if "detail" in error_data and isinstance(error_data["detail"], dict):
                    summary["api_upload_error_snippet"] = error_data["detail"].get(
                        "error", "unknown"
                    )
                else:
                    summary["api_upload_error_snippet"] = error_data.get(
                        "error", "unknown"
                    )
            except Exception:
                summary["api_upload_error_snippet"] = "no_json_response"
            summary["used_token_prefix"] = mask(api_token)
        elif r.status_code == 200:
            summary["api_upload_ok"] = True
        else:
            r.raise_for_status()
    except requests.exceptions.HTTPError as e:
        resp = getattr(e, "response", None)
        if resp is not None and resp.status_code in (401, 403):
            summary["api_upload_status"] = resp.status_code
            try:
                error_data = resp.json()
                if "detail" in error_data and isinstance(error_data["detail"], dict):
                    summary["api_upload_error_snippet"] = error_data["detail"].get(
                        "error", "unknown"
                    )
                else:
                    summary["api_upload_error_snippet"] = error_data.get(
                        "error", "unknown"
                    )
            except Exception:
                summary["api_upload_error_snippet"] = "no_json_response"
            summary["used_token_prefix"] = mask(api_token)
            if not summary.get("inferred_issue"):
                summary["inferred_issue"] = "missing_api_token"
    except Exception:
        # Best-effort script; don't crash on network issues
        pass

    # 2) Worker process fallback
    try:
        body = {
            "kind": "text",
            "path": str(test_path),
            "text": test_path.read_text(encoding="utf-8"),
        }
        r = requests.post(
            f"{worker_base}/process/text",
            data=json.dumps(body),
            headers=_json_headers(worker_token),
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
        headers = _auth_headers(api_token)
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

    # 6) ChatGPT export test (if fixture exists AND upload_fixtures enabled)
    chatgpt_fixture = Path("scripts/fixtures/chatgpt_conversations_min.json")
    if upload_fixtures and chatgpt_fixture.exists():
        summary["fixtures_uploaded"] = True
        summary["chatgpt_test"] = {
            "fixture_exists": True,
            "upload_ok": False,
            "documents_created": None,
            "has_chatgpt_doc": False,
            "has_source_system": False,
            "has_logical_path": False,
            "has_chat_kind": False,
            "has_conversation_id": False,
            "chunks_created": 0,
        }
        try:
            with open(chatgpt_fixture, "rb") as f:
                files = {"file": (chatgpt_fixture.name, f, "application/json")}
                r = requests.post(
                    f"{api_base}/upload",
                    files=files,
                    headers=_auth_headers(api_token),
                    timeout=30,
                )
            if r.ok:
                data = r.json()
                summary["chatgpt_test"]["upload_ok"] = True
                summary["chatgpt_test"]["documents_created"] = data.get(
                    "documents_created", 1
                )

                # Wait a bit for processing
                time.sleep(3)

                docs_r = requests.get(
                    f"{api_base}/documents",
                    headers=_auth_headers(api_token),
                    timeout=10,
                )
                if docs_r.ok:
                    docs = docs_r.json() or []
                    chatgpt_docs = [
                        d
                        for d in docs
                        if (d.get("meta", {}) or {}).get("source_system") == "chatgpt"
                        or "chat" in (d.get("kinds") or [])
                        or str(d.get("document_id", "")).startswith("chatgpt:")
                    ]
                    if chatgpt_docs:
                        summary["chatgpt_test"]["has_chatgpt_doc"] = True
                        first_doc = chatgpt_docs[0]
                        meta = first_doc.get("meta", {}) or {}

                        summary["chatgpt_test"]["has_source_system"] = (
                            meta.get("source_system") == "chatgpt"
                        )
                        lp = meta.get("logical_path", "")
                        summary["chatgpt_test"]["has_logical_path"] = isinstance(
                            lp, str
                        ) and lp.startswith("chatgpt/")
                        summary["chatgpt_test"]["has_chat_kind"] = "chat" in (
                            first_doc.get("kinds") or []
                        )
                        summary["chatgpt_test"]["has_conversation_id"] = str(
                            first_doc.get("document_id", "")
                        ).startswith("chatgpt:")

                        # Prefer chat counts; fall back to chunks/json if older schema
                        def _doc_chunk_count(d: dict) -> int:
                            c = d.get("counts", {}) or {}
                            return int(
                                c.get("chat", 0)
                                or c.get("chunks", 0)
                                or c.get("json", 0)
                                or 0
                            )

                        summary["chatgpt_test"]["chunks_created"] = sum(
                            _doc_chunk_count(d) for d in chatgpt_docs
                        )
        except Exception as e:
            summary["chatgpt_test"]["error"] = str(e)[:100]

    # 7) Negative test: generic JSON should NOT be treated as ChatGPT
    generic_json_fixture = Path("scripts/fixtures/generic_array.json")
    if not generic_json_fixture.exists():
        try:
            generic_json_fixture.parent.mkdir(parents=True, exist_ok=True)
            with open(generic_json_fixture, "w", encoding="utf-8") as f:
                json.dump(
                    [
                        {"id": 1, "name": "Item 1", "value": 100},
                        {"id": 2, "name": "Item 2", "value": 200},
                    ],
                    f,
                )
        except Exception:
            pass

    if upload_fixtures and generic_json_fixture.exists():
        summary["fixtures_uploaded"] = True
        summary["generic_json_test"] = {
            "fixture_exists": True,
            "upload_ok": False,
            "treated_as_chatgpt": None,
            "has_json_kind": False,
        }
        try:
            with open(generic_json_fixture, "rb") as f:
                files = {"file": (generic_json_fixture.name, f, "application/json")}
                r = requests.post(
                    f"{api_base}/upload",
                    files=files,
                    headers=_auth_headers(api_token),
                    timeout=30,
                )
            if r.ok:
                summary["generic_json_test"]["upload_ok"] = True
                time.sleep(3)
                docs_r = requests.get(
                    f"{api_base}/documents",
                    headers=_auth_headers(api_token),
                    timeout=10,
                )
                if docs_r.ok:
                    docs = docs_r.json() or []
                    generic_docs = [
                        d
                        for d in docs
                        if generic_json_fixture.name in str(d.get("paths", []))
                    ]
                    if generic_docs:
                        first_doc = generic_docs[0]
                        meta = first_doc.get("meta", {}) or {}
                        treated_as_chatgpt = (
                            meta.get("source_system") == "chatgpt"
                            or "chat" in (first_doc.get("kinds") or [])
                            or str(first_doc.get("document_id", "")).startswith(
                                "chatgpt:"
                            )
                        )
                        summary["generic_json_test"]["treated_as_chatgpt"] = (
                            treated_as_chatgpt
                        )
                        summary["generic_json_test"]["has_json_kind"] = "json" in (
                            first_doc.get("kinds") or []
                        )
        except Exception as e:
            summary["generic_json_test"]["error"] = str(e)[:100]

    # 8) Infer final issue if unset
    if not summary.get("inferred_issue"):
        if not api_token and not summary["api_upload_ok"]:
            summary["inferred_issue"] = "missing_api_token"
        elif (counts or {}).get("total", 0) == 0 and not summary["worker_process_ok"]:
            summary["inferred_issue"] = "qdrant_empty"
        elif any(summary["search_hits"].values()):
            summary["inferred_issue"] = "ok"
        else:
            summary["inferred_issue"] = "unknown"

    # Print fixture upload status
    if summary.get("fixtures_uploaded", False):
        print("# Fixtures were uploaded (DIAGNOSE_UPLOAD_FIXTURES=1)", file=sys.stderr)
    else:
        print(
            "# Fixtures were NOT uploaded (DIAGNOSE_UPLOAD_FIXTURES=0 or no fixtures found)",
            file=sys.stderr,
        )

    print(json.dumps(summary))


if __name__ == "__main__":
    main()
