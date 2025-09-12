#!/usr/bin/env python3
# --- import ordering: __future__ -> stdlib -> bootstrap -> 3rd-party -> local ---
from __future__ import annotations

# stdlib
import sys
import pathlib
import argparse
import json
import os
import textwrap
import time
from typing import List, Tuple

# repo-root import bootstrap (works even if PYTHONPATH is unset)
REPO_ROOT = (
    pathlib.Path(__file__).resolve().parents[1]
)  # parent of 'scripts/' or 'examples/'
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# third-party (optional)
try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None  # type: ignore

# local imports (after bootstrap)
from worker.app.config import settings  # noqa: E402
from worker.app.services.embed_ollama import embed_texts  # noqa: E402
from worker.app.services.qdrant_client import (  # noqa: E402
    get_qdrant_client,
    search as q_search,
    build_filter,
)

"""
ask_local.py — query -> retrieve -> (optional) answer

Usage:
  # retrieval-only (default)
  PYTHONPATH=worker python examples/ask_local.py --q "what's in the pdf?" -k 6

  # with optional filters
  PYTHONPATH=worker python examples/ask_local.py --q "install steps" --kind text --path README.md

  # ask a local LLM via Ollama (uses settings by default)
  PYTHONPATH=worker python examples/ask_local.py --q "summarize the repo" --llm

  # interactive mode
  PYTHONPATH=worker python examples/ask_local.py --llm
"""

# Environment config (align with worker services)
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "jsonify2ai_chunks")
EMBEDDINGS_MODEL = os.getenv("EMBEDDINGS_MODEL", "nomic-embed-text")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "768"))


def _embed_query(query: str) -> List[float]:
    vecs = embed_texts([query])  # returns List[List[float]]
    if not vecs or not vecs[0]:
        raise RuntimeError("embedding returned no vectors")
    # Optionally check embedding dim
    if len(vecs[0]) != EMBEDDING_DIM:
        raise RuntimeError(
            f"Embedding dimension mismatch: expected {EMBEDDING_DIM}, got {len(vecs[0])}"
        )
    return vecs[0]


def _build_context(points, max_chars: int = 1800) -> Tuple[str, List[dict]]:
    """Concatenate top chunks into a context window; collect compact sources."""
    parts: List[str] = []
    sources: List[dict] = []
    used = 0
    for p in points:
        payload = getattr(p, "payload", None) or {}
        text = (payload.get("text") or "").strip()
        path = payload.get("path") or ""
        idx = payload.get("idx")
        if not text:
            continue
        chunk = textwrap.shorten(text, width=400, placeholder="…")
        addition = "\n" + chunk + "\n"
        if used + len(addition) > max_chars and parts:
            break
        parts.append(addition)
        used += len(addition)
        sources.append(
            {"path": path, "idx": idx, "score": float(getattr(p, "score", 0.0))}
        )
    ctx = "\n".join(parts).strip()
    return ctx, sources


def _ask_llm(prompt: str, model: str, max_tokens: int, temperature: float) -> str:
    url = os.getenv("OLLAMA_URL", settings.OLLAMA_URL or "http://localhost:11434")
    if not requests:
        return f"[requests not installed]\n---\nPrompt preview:\n{prompt[:600]}"
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
    ap.add_argument(
        "--collection",
        type=str,
        default=None,
        help="Override Qdrant collection for ad-hoc tests",
    )
    ap.add_argument(
        "--debug", action="store_true", help="Print preflight and diagnostics"
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Run embedding logic but do not query. Print summary JSON and exit.",
    )
    ap.add_argument("--q", "--query", dest="query", type=str, help="Your question")
    ap.add_argument("-k", "--topk", dest="k", type=int, default=6, help="Top-k chunks")
    # optional scope filters
    ap.add_argument(
        "--document-id", type=str, default=None, help="Filter by document_id"
    )
    ap.add_argument("--kind", type=str, default=None, help="Filter by payload.kind")
    ap.add_argument("--path", type=str, default=None, help="Filter by payload.path")
    # LLM options
    ap.add_argument("--llm", action="store_true", help="Ask local LLM via Ollama")
    ap.add_argument(
        "--no-llm",
        action="store_true",
        help="Force retrieval-only even if ASK_MODE=llm or --llm is set",
    )
    ap.add_argument(
        "--model",
        type=str,
        default=os.getenv("ASK_MODEL", settings.ASK_MODEL),
        help=f"Ollama model when --llm (default: {settings.ASK_MODEL})",
    )
    ap.add_argument("--max-tokens", type=int, default=settings.ASK_MAX_TOKENS)
    ap.add_argument("--temperature", type=float, default=settings.ASK_TEMP)
    ap.add_argument(
        "--context-chars",
        type=int,
        default=3000,
        help="Max characters of retrieved context to include in the LLM prompt (default: 3000)",
    )
    # Output toggles
    ap.add_argument("--show-sources", action="store_true", help="Print source list")
    ap.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    ap.add_argument(
        "--min-score",
        type=float,
        default=None,
        help=(
            "Override similarity floor (uses raw client.search score_threshold). "
            "If omitted, uses existing wrapper thresholds with automatic fallback on empty results."
        ),
    )
    args = ap.parse_args()

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

    # Resolve collection name precedence: CLI > env > settings > hardcoded
    collection = (
        args.collection
        or getattr(settings, "QDRANT_COLLECTION", None)
        or os.getenv("QDRANT_COLLECTION")
        or QDRANT_COLLECTION
    )
    if not collection:
        print(
            "[error] No Qdrant collection specified. Use --collection or set QDRANT_COLLECTION in env/settings."
        )
        sys.exit(1)

    # --debug: print resolved env and collection info
    if args.debug or args.dry_run:
        qdrant_url = os.getenv(
            "QDRANT_URL", getattr(settings, "QDRANT_URL", "http://localhost:6333")
        )
        embeddings_model = getattr(settings, "EMBEDDINGS_MODEL", EMBEDDINGS_MODEL)
        embedding_dim = int(getattr(settings, "EMBEDDING_DIM", EMBEDDING_DIM))
        print(
            f"[debug] QDRANT_URL={qdrant_url} QDRANT_COLLECTION={collection} "
            f"EMBEDDINGS_MODEL={embeddings_model} EMBEDDING_DIM={embedding_dim}"
        )
        # Try to get Qdrant collection info
        try:
            client_dbg = get_qdrant_client()
            info = client_dbg.get_collection(collection)

            # Handle different qdrant-client versions - might return object model or nested structure
            points_count = getattr(info, "points_count", None)
            indexed_vectors_count = getattr(info, "indexed_vectors_count", None)

            # If attributes not directly on info, check for nested result structure
            if points_count is None:
                result = getattr(info, "result", {})
                if result:
                    points_count = getattr(result, "points_count", None)
                    if points_count is None:
                        points_count = getattr(result, "points", None)

                    indexed_vectors_count = getattr(
                        result, "indexed_vectors_count", None
                    )

            # Handle both object and dict access patterns for completeness
            if points_count is None and hasattr(info, "get"):
                points_count = info.get("points_count") or info.get("points")
                indexed_vectors_count = info.get("indexed_vectors_count")

            # Final fallback
            points_count = points_count if points_count is not None else "?"
            indexed_vectors_count = (
                indexed_vectors_count if indexed_vectors_count is not None else "?"
            )

            print(
                f"[debug] collection_info points_count={points_count} indexed_vectors_count={indexed_vectors_count}"
            )
        except Exception as e:
            print(f"[debug] collection_info unavailable: {e}")

    # Embed once
    qv = _embed_query(query)
    if args.debug or args.dry_run:
        print(f"[debug] query_vector_len={len(qv)}")

    # --dry-run: print summary and exit
    if args.dry_run:
        summary = {
            "ok": True,
            "collection": collection,
            "embed_dim": int(getattr(settings, "EMBEDDING_DIM", EMBEDDING_DIM)),
            "query_vector_len": len(qv),
        }
        print(json.dumps(summary, indent=2))
        sys.exit(0)

    # Build client and optional filter
    client = get_qdrant_client()
    qfilter = build_filter(document_id=args.document_id, kind=args.kind, path=args.path)

    # Search logic with optional manual score threshold and fallback safety valve
    points = []
    fallback_used = False

    if args.min_score is not None:
        # Manual override path: direct client.search with provided score_threshold
        if args.debug:
            print(
                f"[debug] manual min-score path: score_threshold={args.min_score} k={args.k}"
            )
        try:
            points = client.search(
                collection_name=collection,
                query_vector=qv,
                limit=args.k,
                with_vectors=False,
                with_payload=True,
                query_filter=qfilter,
                score_threshold=args.min_score,
            )
        except Exception as e:
            print(f"[error] search (manual --min-score) failed: {e}")
            sys.exit(1)
    else:
        # Default path: use existing helper (retains its internal default thresholds)
        try:
            points = q_search(
                qv,
                k=args.k,
                client=client,
                query_filter=qfilter,
                with_payload=True,
                collection_name=collection,
                debug=args.debug,
            )
        except Exception as e:
            print(f"[error] {e}")
            sys.exit(1)

        # Fallback: if no hits, re-run with raw client.search and score_threshold=0.0
        if not points:
            try:
                points = client.search(
                    collection_name=collection,
                    query_vector=qv,
                    limit=args.k,
                    with_vectors=False,
                    with_payload=True,
                    query_filter=qfilter,
                    score_threshold=0.0,
                )
                if points:
                    fallback_used = True
                    print(
                        "[info] fallback: no matches ≥ default threshold; showing best available."
                    )
            except Exception as e:
                print(f"[error] fallback search failed: {e}")
                sys.exit(1)

    if not points:
        msg = "[no results] index empty or query not matched."
        if args.json:
            print(json.dumps({"ok": False, "message": msg}, ensure_ascii=False))
        else:
            print(msg)
        return

    # Build context + sources
    context, sources = _build_context(points, max_chars=args.context_chars)

    # Retrieval-only or LLM mode (default respects settings)
    use_llm = not args.no_llm and (
        args.llm or (getattr(settings, "ASK_MODE", "search") == "llm")
    )
    if use_llm:
        system = (
            "You are a concise assistant. Use ONLY the provided context. "
            "If the answer is not in context, say you don't know."
        )
        user = f"Question:\n{query}\n\nContext:\n{context}"
        prompt = f"{system}\n\n{user}\n\nAnswer:"
        answer = _ask_llm(
            prompt=prompt,
            model=args.model,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
        )
    else:
        answer = "Top snippets (retrieval-only mode):\n" + "\n---\n".join(
            f"{(s.get('path') or '(unknown)')}  (chunk #{s.get('idx')})  score={s.get('score'):.4f}"
            for s in sources[:3]
        )

    if args.json:
        print(
            json.dumps(
                {
                    "ok": True,
                    "query": query,
                    "answer": answer,
                    "sources": sources if args.show_sources else None,
                    "meta": {
                        "manual_min_score": args.min_score,
                        "fallback_used": fallback_used,
                    },
                    "filters": {
                        "document_id": args.document_id,
                        "kind": args.kind,
                        "path": args.path,
                    },
                },
                ensure_ascii=False,
            )
        )
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
