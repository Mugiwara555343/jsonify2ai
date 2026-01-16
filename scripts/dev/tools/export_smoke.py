import os
import json
import requests
from urllib.parse import urlencode


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


def main():
    env = read_env()
    api_base = env.get("API_BASE", os.getenv("API_BASE", "http://localhost:8082"))
    api_token = env.get("API_AUTH_TOKEN", os.getenv("API_AUTH_TOKEN", ""))

    # Build headers
    headers = {}
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"

    verdict = {
        "api_base": api_base,
        "docs_checked": 0,
        "export_json_ok": True,
        "export_zip_ok": True,
        "json_failures": [],
        "zip_failures": [],
        "status": "ok",
    }

    # Step 1: Fetch documents
    try:
        resp = requests.get(f"{api_base}/documents", headers=headers, timeout=15)
        if resp.status_code != 200:
            verdict["status"] = f"documents_fetch_failed_{resp.status_code}"
            print(json.dumps(verdict))
            return
        documents = resp.json()
    except requests.exceptions.ConnectionError:
        verdict["status"] = "api_unreachable"
        print(json.dumps(verdict))
        return
    except Exception as e:
        verdict["status"] = f"documents_error_{str(e)[:50]}"
        print(json.dumps(verdict))
        return

    if not isinstance(documents, list):
        verdict["status"] = "documents_not_array"
        print(json.dumps(verdict))
        return

    # Step 2: Select documents to test
    text_docs = []
    image_docs = []
    for doc in documents:
        kinds = doc.get("kinds", [])
        if "text" in kinds and len(text_docs) < 3:
            text_docs.append(doc)
        if "image" in kinds and len(image_docs) < 2:
            image_docs.append(doc)

    selected_docs = []
    for doc in text_docs:
        selected_docs.append(
            {"doc": doc, "kind": "text", "collection": "jsonify2ai_chunks_768"}
        )
    for doc in image_docs:
        selected_docs.append(
            {"doc": doc, "kind": "image", "collection": "jsonify2ai_images_768"}
        )

    verdict["docs_checked"] = len(selected_docs)

    if len(selected_docs) == 0:
        verdict["status"] = "no_documents_found"
        print(json.dumps(verdict))
        return

    # Step 3: Test /export for each doc
    for item in selected_docs:
        doc = item["doc"]
        doc_id = doc.get("document_id")
        kind = item["kind"]
        collection = item["collection"]

        try:
            params = {
                "document_id": doc_id,
                "collection": collection,
            }
            url = f"{api_base}/export?{urlencode(params)}"
            resp = requests.get(url, headers=headers, timeout=30)

            if resp.status_code != 200:
                verdict["export_json_ok"] = False
                verdict["json_failures"].append(
                    {
                        "document_id": doc_id,
                        "kind": kind,
                        "status": resp.status_code,
                        "reason": f"http_{resp.status_code}",
                    }
                )
                continue

            # Check content type
            content_type = resp.headers.get("Content-Type", "").lower()
            if "text/html" in content_type:
                verdict["export_json_ok"] = False
                verdict["json_failures"].append(
                    {
                        "document_id": doc_id,
                        "kind": kind,
                        "status": resp.status_code,
                        "reason": "html_error_page",
                    }
                )
                continue

            # Check body is non-empty
            body = resp.text
            if not body or not body.strip():
                verdict["export_json_ok"] = False
                verdict["json_failures"].append(
                    {
                        "document_id": doc_id,
                        "kind": kind,
                        "status": resp.status_code,
                        "reason": "empty_body",
                    }
                )
                continue

            # Parse first non-empty line as JSON
            lines = [line.strip() for line in body.split("\n") if line.strip()]
            if not lines:
                verdict["export_json_ok"] = False
                verdict["json_failures"].append(
                    {
                        "document_id": doc_id,
                        "kind": kind,
                        "status": resp.status_code,
                        "reason": "no_json_lines",
                    }
                )
                continue

            try:
                first_line_json = json.loads(lines[0])
                # Verify required keys
                required_keys = ["id", "document_id", "kind", "path"]
                missing_keys = [
                    key for key in required_keys if key not in first_line_json
                ]
                if missing_keys:
                    verdict["export_json_ok"] = False
                    verdict["json_failures"].append(
                        {
                            "document_id": doc_id,
                            "kind": kind,
                            "status": resp.status_code,
                            "reason": f"missing_keys_{','.join(missing_keys)}",
                        }
                    )
            except json.JSONDecodeError as e:
                verdict["export_json_ok"] = False
                verdict["json_failures"].append(
                    {
                        "document_id": doc_id,
                        "kind": kind,
                        "status": resp.status_code,
                        "reason": f"json_decode_error_{str(e)[:30]}",
                    }
                )

        except requests.exceptions.ConnectionError:
            verdict["status"] = "api_unreachable"
            verdict["export_json_ok"] = False
            verdict["json_failures"].append(
                {
                    "document_id": doc_id,
                    "kind": kind,
                    "status": 0,
                    "reason": "connection_error",
                }
            )
        except Exception as e:
            verdict["export_json_ok"] = False
            verdict["json_failures"].append(
                {
                    "document_id": doc_id,
                    "kind": kind,
                    "status": 0,
                    "reason": f"exception_{str(e)[:50]}",
                }
            )

    # Step 4: Test /export/archive for each doc
    for item in selected_docs:
        doc = item["doc"]
        doc_id = doc.get("document_id")
        kind = item["kind"]
        collection = item["collection"]

        try:
            params = {
                "document_id": doc_id,
                "collection": collection,
            }
            url = f"{api_base}/export/archive?{urlencode(params)}"
            resp = requests.get(url, headers=headers, timeout=30)

            if resp.status_code != 200:
                verdict["export_zip_ok"] = False
                verdict["zip_failures"].append(
                    {
                        "document_id": doc_id,
                        "kind": kind,
                        "status": resp.status_code,
                        "reason": f"http_{resp.status_code}",
                    }
                )
                continue

            # Check content type
            content_type = resp.headers.get("Content-Type", "").lower()
            if "text/html" in content_type:
                verdict["export_zip_ok"] = False
                verdict["zip_failures"].append(
                    {
                        "document_id": doc_id,
                        "kind": kind,
                        "status": resp.status_code,
                        "reason": "html_error_page",
                    }
                )
                continue

            # Check body size
            content_length = resp.headers.get("Content-Length")
            body_size = len(resp.content)
            if (content_length and int(content_length) == 0) or body_size == 0:
                verdict["export_zip_ok"] = False
                verdict["zip_failures"].append(
                    {
                        "document_id": doc_id,
                        "kind": kind,
                        "status": resp.status_code,
                        "reason": "empty_body",
                    }
                )
                continue

            # Check content type is zip-like
            if (
                "application/zip" not in content_type
                and "application/octet-stream" not in content_type
            ):
                # Still allow it if body is non-empty (might be a different zip MIME type)
                if body_size > 0:
                    pass  # Acceptable
                else:
                    verdict["export_zip_ok"] = False
                    verdict["zip_failures"].append(
                        {
                            "document_id": doc_id,
                            "kind": kind,
                            "status": resp.status_code,
                            "reason": f"unexpected_content_type_{content_type}",
                        }
                    )

        except requests.exceptions.ConnectionError:
            verdict["status"] = "api_unreachable"
            verdict["export_zip_ok"] = False
            verdict["zip_failures"].append(
                {
                    "document_id": doc_id,
                    "kind": kind,
                    "status": 0,
                    "reason": "connection_error",
                }
            )
        except Exception as e:
            verdict["export_zip_ok"] = False
            verdict["zip_failures"].append(
                {
                    "document_id": doc_id,
                    "kind": kind,
                    "status": 0,
                    "reason": f"exception_{str(e)[:50]}",
                }
            )

    # Final status determination
    if verdict["status"] == "ok":
        if not verdict["export_json_ok"] or not verdict["export_zip_ok"]:
            verdict["status"] = "partial_failure"
    elif verdict["status"] != "api_unreachable":
        if not verdict["export_json_ok"] or not verdict["export_zip_ok"]:
            verdict["status"] = "failure"

    print(json.dumps(verdict))


if __name__ == "__main__":
    main()
