#!/usr/bin/env python3
"""
ask_local.py — query -> retrieve -> (optional) answer

Usage:
  # simple
  PYTHONPATH=worker python examples/ask_local.py --q "what's in the pdf?" --k 6

  # ask a local LLM via Ollama (if available)
  PYTHONPATH=worker python examples/ask_local.py --q "summarize the resume" --llm --model llama3.1

  # interactive mode
  PYTHONPATH=worker python examples/ask_local.py --llm
"""

from __future__ import annotations
import argparse, json, os, sys, textwrap, time
from typing import List, Tuple

# bring in worker settings + embeddings (dev mode or real)
from app.config import settings
from app.services.embed_ollama import embed_texts  # uses Settings: OLLAMA_URL, EMBED_DEV_MODE, etc.

from qdrant_client import QdrantClient, models
import requests

def _connect_qdrant() -> QdrantClient:
    url = settings.QDRANT_URL
    try:
        c = QdrantClient(url=url, timeout=10.0)
        # light ping
        _ = c.get_collections()
        return c
    except Exception as e:
        print(f"[error] Could not reach Qdrant at {url}: {e}", file=sys.stderr)
        sys.exit(2)

def _embed_query(query: str) -> List[float]:
    try:
        vecs = embed_texts([query])  # returns List[List[float]]
        return vecs[0]
    except Exception as e:
        print(f"[error] embedding failed: {e}", file=sys.stderr)
        sys.exit(3)

def _search(c: QdrantClient, query_vec: List[float], k: int) -> List[models.ScoredPoint]:
    col = settings.QDRANT_COLLECTION
    try:
        res = c.search(
            collection_name=col,
            query_vector=query_vec,
            limit=k,
            with_payload=True,
        )
        return res
    except Exception as e:
        print(f"[error] search failed in collection '{col}': {e}", file=sys.stderr)
        sys.exit(4)

def _build_context(points: List[models.ScoredPoint], max_chars: int = 1800) -> Tuple[str, List[dict]]:
    """Concatenate top chunks into a context window and return simple source list."""
    parts = []
    sources = []
    used = 0
    for p in points:
        payload = p.payload or {}
        text = (payload.get("text") or "").strip()
        path = payload.get("path") or ""
        idx = payload.get("idx")
        if not text:
            continue
        chunk = textwrap.shorten(text, width=400, placeholder="…")
        addition = ("\n" + chunk + "\n")
        if used + len(addition) > max_chars and parts:
            break
        parts.append(addition)
        used += len(addition)
        sources.append({
            "path": path,
            "idx": idx,
            "score": float(p.score) if hasattr(p, "score") else None,
        })
    ctx = "\n".join(parts).strip()
    return ctx, sources

def _ask_llm(prompt: str, model: str, max_tokens: int, temperature: float) -> str:
    """Call Ollama /api/generate; fall back with helpful message if unreachable."""
    url = os.getenv("OLLAMA_URL", settings.OLLAMA_URL or "http://localhost:11434")
    try:
        r = requests.post(
            f"{url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": temperature},
                "keep_alive": "5m",
            },
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        return (data.get("response") or "").strip()
    except Exception as e:
        return f"[LLM unavailable @ {url}] {e}\n---\nPrompt preview:\n{prompt[:600]}"

def main():
    ap = argparse.ArgumentParser(description="Local Ask over Qdrant (optional Ollama)")
    ap.add_argument("--q", "--query", dest="query", type=str, help="Your question")
    ap.add_argument("--k", type=int, default=6, help="Top-k chunks to retrieve (default: 6)")
    ap.add_argument("--llm", action="store_true", help="Ask local LLM via Ollama")
    ap.add_argument("--model", type=str, default=os.getenv("ASK_MODEL", "llama3.1"),
                    help="Ollama model to use when --llm (default: llama3.1)")
    ap.add_argument("--max-tokens", type=int, default=400)
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--show-sources", action="store_true", help="Print source list after answer")
    ap.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = ap.parse_args()

    # interactive prompt (nice for “control panel” feel)
    query = args.query
    if not query:
        try:
            query = input("ask> ").strip()
        except KeyboardInterrupt:
            print()
            return
    if not query:
        print("[hint] empty question. try again with --q 'your question'.")
        return

    c = _connect_qdrant()
    qv = _embed_query(query)
    pts = _search(c, qv, args.k)
    if not pts:
        msg = "[no results] Your index might be empty, or embeddings mismatch this collection."
        print(msg)
        if args.json:
            print(json.dumps({"ok": False, "message": msg}, ensure_ascii=False))
        return

    context, sources = _build_context(pts)

    system = "You are a concise assistant. Use ONLY the provided context. If unsure, say you don't know."
    user = f"Question:\n{query}\n\nContext:\n{context}"
    prompt = f"{system}\n\n{user}\n\nAnswer:"

    answer = None
    if args.llm:
        answer = _ask_llm(prompt, model=args.model, max_tokens=args.max_tokens, temperature=args.temperature)
    else:
        # retrieval-only mode
        answer = "Top snippets (retrieval-only mode):\n" + "\n---\n".join(s.get("path") or "(unknown)" for s in sources[:3])

    if args.json:
        print(json.dumps({
            "ok": True,
            "query": query,
            "answer": answer,
            "sources": sources if args.show_sources else None
        }, ensure_ascii=False))
    else:
        print("\n" + "=" * 8 + " answer " + "=" * 8)
        print(answer)
        if args.show_sources:
            print("\n" + "=" * 8 + " sources " + "=" * 8)
            for s in sources:
                print(f"- {s['path']}  (chunk #{s.get('idx')})  score={s.get('score')}")

if __name__ == "__main__":
    t0 = time.time()
    try:
        main()
    finally:
        dt = time.time() - t0
        print(f"\n[done in {dt:.2f}s]")
