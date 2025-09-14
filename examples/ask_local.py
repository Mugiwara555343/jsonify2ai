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

# Load .env so entrypoint processes see repository defaults early (no-op if python-dotenv missing)
try:
    from dotenv import load_dotenv  # type: ignore

    dotenv_path = REPO_ROOT.joinpath(".env")
    if dotenv_path.exists():
        load_dotenv(dotenv_path=str(dotenv_path))
except Exception:
    # If python-dotenv isn't installed or load fails, fall back to system env (no crash)
    pass

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


def _is_filename_like(q: str) -> bool:
    """Heuristic: treat query as filename/path if it clearly references a file.

    Conditions (OR):
      1) Ends with known extension (.wav/.mp3/.pdf/.md/.txt/.json/.jsonl/.docx)
      2) Contains a path separator ('/' or '\\')
      3) Basename contains a dot (e.g., 'file.ext') and basename length > 1
    """
    if not q:
        return False
    q_clean = q.strip()
    lower = q_clean.lower()
    exts = (".wav", ".mp3", ".pdf", ".md", ".txt", ".json", ".jsonl", ".docx")
    if any(lower.endswith(ext) for ext in exts):
        return True
    if "/" in q_clean or "\\" in q_clean:
        return True
    basename = os.path.basename(q_clean.replace("\\", "/"))
    if "." in basename and len(basename) > 1:
        return True
    return False


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
        # Keep original length line for backward compatibility, add richer debug lines per new requirements
        print(f"[debug] query_vector_len={len(qv)}")
    if args.debug:
        qv_sample = [round(float(x), 6) for x in qv[:8]]
        qv_norm = sum(abs(float(x)) for x in qv)
        print(f"[debug] qv_len: {len(qv)} qv_sample: {qv_sample}")
        print(f"[debug] qv_norm: {qv_norm:.6f}")

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

    # Build client
    client = get_qdrant_client()

    # Fast path: filename/path-style query direct filter scan (skip wrapper if direct hit)
    if _is_filename_like(query) and args.min_score is None:
        # Path-fast heuristic: attempt exact path match first; if that fails and the query
        # looks like it includes directories, also try its basename.
        attempts = []
        attempts.append((query, "full"))
        basename = os.path.basename(query.strip().replace("\\", "/"))
        if basename and basename != query:
            attempts.append((basename, "basename"))

        for path_candidate, label in attempts:
            path_filter = build_filter(path=path_candidate)
            if args.debug:
                try:
                    if hasattr(path_filter, "model_dump"):
                        pf_print = path_filter.model_dump()  # type: ignore[attr-defined]
                    elif hasattr(path_filter, "dict"):
                        pf_print = path_filter.dict()  # type: ignore
                    else:
                        pf_print = (
                            path_filter.to_dict()  # type: ignore[attr-defined]
                            if hasattr(path_filter, "to_dict")
                            else path_filter
                        )
                except Exception:
                    pf_print = path_filter
                print(
                    f"[debug] qfilter (path-fast:{label}): {pf_print if pf_print else {}}"
                )
                print(
                    f"[debug] path-fast-path: attempting {label} path match via scroll (candidate='{path_candidate}')"
                )
            try:
                points_fast, _ = client.scroll(
                    collection_name=collection,
                    scroll_filter=path_filter,
                    limit=args.k,
                    with_payload=True,
                    with_vectors=False,
                )
            except Exception as e:
                points_fast = []
                if args.debug:
                    print(f"[debug] path-fast-path scroll error ({label}): {e}")
            if not points_fast:
                continue

            # Inject synthetic score + snippet so downstream formatting remains consistent.
            for p in points_fast:
                if not hasattr(p, "score"):
                    try:
                        setattr(p, "score", 1.0)  # synthetic score for exact path match
                    except Exception:
                        pass
            context, sources = _build_context(points_fast, max_chars=args.context_chars)
            # Add snippet (first 160 chars raw payload text) for each source without altering human list formatting.
            for p, s in zip(points_fast, sources):
                try:
                    payload = getattr(p, "payload", None) or {}
                    snippet = (payload.get("text") or "")[:160].strip()
                    s.setdefault("text", snippet)
                except Exception:
                    s.setdefault("text", "")
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
                answer = "Top snippets (path match):\n" + "\n---\n".join(
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
                                "fallback_used": False,
                                "path_fast_path": True,
                                "path_fast_variant": label,
                            },
                            "filters": {
                                "document_id": args.document_id,
                                "kind": args.kind,
                                "path": path_candidate,
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
                        print(
                            f"- {s['path']}  (chunk #{s.get('idx')})  score={s.get('score')}"
                        )
            return

    # Standard filter (semantic path)
    qfilter = build_filter(document_id=args.document_id, kind=args.kind, path=args.path)
    if args.debug:
        try:
            if hasattr(qfilter, "dict"):
                qf_print = qfilter.dict()  # type: ignore
            else:
                qf_print = (
                    qfilter.to_dict()  # type: ignore[attr-defined]
                    if hasattr(qfilter, "to_dict")
                    else qfilter
                )
        except Exception:
            qf_print = qfilter
        print(f"[debug] qfilter: {qf_print if qf_print else {}}")

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
                        "[info] fallback: wrapper returned no hits; using direct client.search() with score_threshold=0.0"
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
