#!/usr/bin/env python3
import os
import json
import time
import statistics
import requests

API = os.getenv("API_BASE", "http://localhost:8082")
TOKEN = os.getenv("API_AUTH_TOKEN", "")
KIND = os.getenv("ASK_KIND", "text")
QFILE = os.getenv("QA_FILE", "eval/qa.example.jsonl")


def ask(q: str):
    url = f"{API}/ask"
    headers = {}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    t0 = time.perf_counter()
    r = requests.post(url, json={"kind": KIND, "q": q}, headers=headers, timeout=120)
    dt = (time.perf_counter() - t0) * 1000
    ok = r.ok
    try:
        js = r.json()
    except Exception:
        js = {"raw": r.text}
    return ok, dt, js


def main():
    qs = []
    with open(QFILE, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            qs.append(json.loads(line))
    results, dts, hits = [], [], 0
    for i, item in enumerate(qs, 1):
        ok, dt, js = ask(item["question"])
        dts.append(dt)
        body = json.dumps(js, ensure_ascii=False)[:800]
        hit = item.get("answer_contains", "").lower() in body.lower()
        hits += 1 if hit else 0
        results.append(
            {
                "i": i,
                "ms": round(dt, 1),
                "ok": ok,
                "hit": hit,
                "question": item["question"],
            }
        )
        print(f"[{i}] {dt:7.1f} ms | ok={ok} | hit={hit} | {item['question']}")
    if dts:
        print("\nSummary:")
        print(f"  n={len(dts)}, hit@1={hits}/{len(dts)} ({(hits/len(dts))*100:.1f}%)")
        p95 = statistics.quantiles(dts, n=20)[-1] if len(dts) >= 20 else max(dts)
        print(f"  p50={statistics.median(dts):.1f} ms, p95={p95:.1f} ms")
    out = {
        "ts": time.time(),
        "api": API,
        "n": len(dts),
        "hits": hits,
        "latencies_ms": dts,
        "cases": results,
    }
    os.makedirs("eval/results", exist_ok=True)
    with open("eval/results/last.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
