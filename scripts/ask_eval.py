#!/usr/bin/env python3
import os
import json
import time
import statistics
import requests
import argparse

API = os.getenv("API_BASE", "http://localhost:8082")
TOKEN = os.getenv("API_AUTH_TOKEN", "")
KIND = os.getenv("ASK_KIND", "text")
QFILE = os.getenv("QA_FILE", "eval/qa.example.jsonl")


def ask(q: str, document_id: str = None, path_prefix: str = None):
    url = f"{API}/ask"
    headers = {}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

    # Build query params for filters
    params = {}
    if document_id:
        params["document_id"] = document_id
    if path_prefix:
        params["path_prefix"] = path_prefix

    t0 = time.perf_counter()
    r = requests.post(
        url, json={"kind": KIND, "q": q}, headers=headers, params=params, timeout=120
    )
    dt = (time.perf_counter() - t0) * 1000
    ok = r.ok
    try:
        js = r.json()
    except Exception:
        js = {"raw": r.text}
    return ok, dt, js


def main():
    parser = argparse.ArgumentParser(description="Evaluate /ask endpoint")
    parser.add_argument(
        "--qa",
        default=QFILE,
        help="QA file path (default: from QA_FILE env or eval/qa.example.jsonl)",
    )
    args = parser.parse_args()

    qs = []
    with open(args.qa, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            qs.append(json.loads(line))
    results, dts, hits = [], [], 0
    for i, item in enumerate(qs, 1):
        # Support both old format (question, answer_contains) and new format (q, must_contain, filters)
        question = item.get("q") or item.get("question", "")
        document_id = item.get("document_id")
        path_prefix = item.get("path_prefix")

        ok, dt, js = ask(question, document_id=document_id, path_prefix=path_prefix)
        dts.append(dt)

        # Check hit@1: look for must_contain substrings in top answer
        hit = False
        must_contain = item.get("must_contain", [])
        if must_contain:
            # Check in answer, final, or top snippet
            answer_text = ""
            if js.get("final"):
                answer_text = js["final"].lower()
            elif js.get("answer"):
                answer_text = js["answer"].lower()
            elif js.get("answers") and len(js["answers"]) > 0:
                top_answer = js["answers"][0]
                answer_text = (
                    top_answer.get("text") or top_answer.get("caption") or ""
                ).lower()
            elif js.get("sources") and len(js["sources"]) > 0:
                top_source = js["sources"][0]
                answer_text = (
                    top_source.get("text") or top_source.get("caption") or ""
                ).lower()

            # Check if any must_contain substring is present
            hit = any(
                substr.lower() in answer_text for substr in must_contain if substr
            )
        else:
            # Fallback to old answer_contains format
            answer_contains = item.get("answer_contains", "")
            if answer_contains:
                body = json.dumps(js, ensure_ascii=False).lower()
                hit = answer_contains.lower() in body

        hits += 1 if hit else 0
        results.append(
            {
                "i": i,
                "ms": round(dt, 1),
                "ok": ok,
                "hit": hit,
                "question": question,
            }
        )
        print(f"[{i}] {dt:7.1f} ms | ok={ok} | hit={hit} | {question[:60]}")
    if dts:
        print("\nSummary:")
        print(f"  n={len(dts)}, hit@1={hits}/{len(dts)} ({(hits/len(dts))*100:.1f}%)")
        p95 = statistics.quantiles(dts, n=20)[-1] if len(dts) >= 20 else max(dts)
        print(f"  p50={statistics.median(dts):.1f} ms, p95={p95:.1f} ms")
    out = {
        "ts": time.time(),
        "api": API,
        "n": len(dts),
        "hit@1": hits,
        "p50_ms": statistics.median(dts) if dts else 0,
        "p95_ms": (
            statistics.quantiles(dts, n=20)[-1]
            if len(dts) >= 20
            else (max(dts) if dts else 0)
        ),
        "latencies_ms": dts,
        "cases": results,
    }
    os.makedirs("eval/results", exist_ok=True)
    with open("eval/results/last.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
