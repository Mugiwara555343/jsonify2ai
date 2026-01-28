#!/usr/bin/env python3
import argparse
import os
import sys
import json
import time
from typing import Dict, Any, Optional
import urllib.parse
import requests

API = os.getenv("API_URL", "http://localhost:8082")
WORKER = os.getenv("WORKER_URL", "http://localhost:8090")

# Golden sample paths (relative to repo root; worker expects data/dropzone/<rel>)
TEXT_PATH = "data/dropzone/smoke_golden/text_sample.md"
PDF_PATH = "data/dropzone/smoke_golden/sample.pdf"
IMAGE_PATH = "data/dropzone/smoke_golden/test.png"


def jprint(label: str, obj: Any):
    print(f"{label}: {json.dumps(obj, ensure_ascii=False)}")


def get_json(url: str) -> Dict[str, Any]:
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return r.json()


def post_json(url: str, body: Dict[str, Any]) -> Dict[str, Any]:
    r = requests.post(url, json=body, timeout=30)
    # allow 422 to show message for easier debugging
    if r.status_code >= 400:
        raise RuntimeError(f"POST {url} -> {r.status_code}: {r.text}")
    return r.json()


def api_status() -> Dict[str, Any]:
    return get_json(f"{API}/status")


def worker_process(kind: str, path: str) -> Dict[str, Any]:
    return post_json(f"{WORKER}/process/{kind}", {"path": path})


def api_search(q: str, kind: str, k: int = 5) -> Dict[str, Any]:
    # Try GET first
    try:
        url = f"{API}/search?q={urllib.parse.quote(q)}&kind={urllib.parse.quote(kind)}&k={k}"
        r = requests.get(url, timeout=15)
        if r.ok:
            return r.json()
    except Exception:
        pass
    # Fallback to POST
    return post_json(f"{API}/search", {"q": q, "kind": kind, "k": k})


def wait_counts_delta(
    start: Dict[str, int], max_wait: float = 15.0, require_increase: bool = False
) -> Dict[str, int]:
    """Poll API /status until counts increase or timeout."""
    t0 = time.time()
    while True:
        s = api_status()
        counts = s.get("counts", {})
        increased = (counts.get("chunks", 0) > start.get("chunks", 0)) or (
            counts.get("images", 0) > start.get("images", 0)
        )
        if increased:
            return counts
        if require_increase and not increased and time.time() - t0 > max_wait:
            return counts
        if time.time() - t0 > max_wait:
            return counts
        time.sleep(0.7)


def must_ge(val: int, minv: int, label: str):
    if val < minv:
        raise AssertionError(f"{label}: expected ≥{minv}, got {val}")


def must_true(val: bool, label: str):
    if not val:
        raise AssertionError(f"{label}: expected True, got {val}")


def _assert_has_doc(
    results,
    want_document_id: Optional[str] = None,
    want_path: Optional[str] = None,
    lane: str = "",
):
    """
    Ensure search results include either the given document_id or path from the just-processed file.
    """
    if not results:
        raise AssertionError(f"[{lane}] no results")
    if want_document_id is None and want_path is None:
        return  # nothing to check specifically
    for r in results:
        if want_document_id and str(r.get("document_id")) == str(want_document_id):
            return
        if want_path and str(r.get("path")) == str(want_path):
            return
    raise AssertionError(
        f"[{lane}] results did not include expected doc_id={want_document_id} or path={want_path}"
    )


def run() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", default=TEXT_PATH)
    ap.add_argument("--pdf", default=PDF_PATH)
    ap.add_argument("--image", default=IMAGE_PATH)
    ap.add_argument("--q-text", default="golden")
    ap.add_argument("--q-pdf", default="Pallet")
    ap.add_argument("--q-image", default="image")
    ap.add_argument(
        "--csv", default=None, help="optional CSV to process via /process/text"
    )
    ap.add_argument(
        "--docx", default=None, help="optional DOCX to process via /process/text"
    )
    ap.add_argument(
        "--html", default=None, help="optional HTML to process via /process/text"
    )
    ap.add_argument("--q-csv", default="id,name", help="query token for csv search")
    ap.add_argument(
        "--q-docx", default="Experience", help="query token for docx search"
    )
    ap.add_argument("--q-html", default="html", help="query token for html search")
    ap.add_argument(
        "--strict-increase",
        action="store_true",
        help="require counters to increase; otherwise allow idempotent no-op",
    )
    args = ap.parse_args()

    for p in [args.text, args.pdf, args.image]:
        if not os.path.exists(p):
            raise FileNotFoundError(f"missing sample file: {p}")

    print(f"[cfg] API={API} WORKER={WORKER}")

    status0 = api_status()
    counts0 = status0.get("counts", {})
    jprint("[status0]", status0)

    # Text
    t = worker_process("text", args.text)
    jprint("[process/text]", t)
    must_ge(t.get("upserted", 0), 0, "text.upserted")  # allow 0 if idempotent

    # PDF
    p = worker_process("pdf", args.pdf)
    jprint("[process/pdf]", p)
    must_ge(p.get("upserted", 0), 0, "pdf.upserted")

    # Image
    i = worker_process("image", args.image)
    jprint("[process/image]", i)
    must_ge(i.get("upserted", 0), 0, "image.upserted")

    counts1 = wait_counts_delta(counts0, require_increase=bool(args.strict_increase))
    jprint("[counts1]", counts1)

    # Search assertions per kind
    sx = api_search(args.q_text, "text")
    jprint("[search/text]", sx)
    must_ge(len(sx.get("results", [])), 1, "search.text.results")

    sp = api_search(args.q_pdf, "pdf")
    jprint("[search/pdf]", sp)
    must_ge(len(sp.get("results", [])), 1, "search.pdf.results")

    si = api_search(
        args.q_image, "image"
    )  # adjust if you use custom captions; "image" matches default
    jprint("[search/image]", si)
    must_ge(len(si.get("results", [])), 1, "search.image.results")

    # If DOCX path provided but file missing, generate it
    if args.docx and not os.path.exists(args.docx):
        print(f"[gen] {args.docx} missing; generating via scripts/gen_smoke_docs.py")
        os.system(f"{sys.executable} scripts/dev/tools/gen_smoke_docs.py")

    # Optional new types
    if args.csv and os.path.exists(args.csv):
        csv_proc = worker_process("text", args.csv)
        jprint("[process/csv]", csv_proc)
        must_true(csv_proc.get("ok") is True, "csv process ok")
        csv_doc = csv_proc.get("document_id")
        csv_search = api_search(args.q_csv, "text")
        jprint("[search/csv]", csv_search)
        _assert_has_doc(
            csv_search.get("results", []),
            want_document_id=csv_doc,
            want_path="smoke_golden/mini.csv",
            lane="csv",
        )

    if args.docx and os.path.exists(args.docx):
        docx_proc = worker_process("text", args.docx)
        jprint("[process/docx]", docx_proc)
        must_true(docx_proc.get("ok") is True, "docx process ok")
        docx_doc = docx_proc.get("document_id")
        docx_search = api_search(args.q_docx, "text")
        jprint("[search/docx]", docx_search)
        _assert_has_doc(
            docx_search.get("results", []),
            want_document_id=docx_doc,
            want_path="smoke_golden/mini.docx",
            lane="docx",
        )

    if args.html and os.path.exists(args.html):
        html_proc = worker_process("text", args.html)
        jprint("[process/html]", html_proc)
        must_true(html_proc.get("ok") is True, "html process ok")
        html_doc = html_proc.get("document_id")
        html_search = api_search(args.q_html, "text")
        jprint("[search/html]", html_search)
        _assert_has_doc(
            html_search.get("results", []),
            want_document_id=html_doc,
            want_path="smoke_golden/mini.html",
            lane="html",
        )

    print("[ok] smoke succeeded")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run())
    except Exception as e:
        print(f"[fail] {e}", file=sys.stderr)
        sys.exit(1)
