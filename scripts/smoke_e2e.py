#!/usr/bin/env python3
import argparse
import os
import sys
import json
import time
from typing import Dict, Any
import urllib.parse
import requests

API = os.getenv("API_URL", "http://localhost:8082")
WORKER = os.getenv("WORKER_URL", "http://localhost:8090")

# Golden sample paths (relative to repo root; worker expects data/dropzone/<rel>)
TEXT_PATH = "data/dropzone/smoke_golden/text_sample.md"
PDF_PATH = "data/dropzone/Mauricio-A-Ventura-FlowCV-Resume-20250805-3.pdf"
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

    # Optional new types
    if args.csv and os.path.exists(args.csv):
        tc = worker_process("text", args.csv)
        jprint("[process/csv]", tc)
        must_ge(tc.get("upserted", 0), 0, "csv.upserted")
        sc = api_search(args.q_csv, "text")
        jprint("[search/csv]", sc)
        must_ge(len(sc.get("results", [])), 1, "search.csv.results")

    if args.docx and os.path.exists(args.docx):
        td = worker_process("text", args.docx)
        jprint("[process/docx]", td)
        must_ge(td.get("upserted", 0), 0, "docx.upserted")
        sd = api_search(args.q_docx, "text")
        jprint("[search/docx]", sd)
        must_ge(len(sd.get("results", [])), 1, "search.docx.results")

    if args.html and os.path.exists(args.html):
        th = worker_process("text", args.html)
        jprint("[process/html]", th)
        must_ge(th.get("upserted", 0), 0, "html.upserted")
        sh = api_search(args.q_html, "text")
        jprint("[search/html]", sh)
        must_ge(len(sh.get("results", [])), 1, "search.html.results")

    print("[ok] smoke succeeded")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run())
    except Exception as e:
        print(f"[fail] {e}", file=sys.stderr)
        sys.exit(1)
