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
import re
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
    build_filter,
)

try:  # qdrant models for filters and query api
    from qdrant_client import models as qm  # type: ignore
except Exception:  # pragma: no cover
    qm = None  # type: ignore

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
QDRANT_COLLECTION = getattr(settings, "QDRANT_COLLECTION", None) or os.getenv(
    "QDRANT_COLLECTION", "jsonify2ai_chunks"
)
EMBEDDINGS_MODEL = getattr(settings, "EMBEDDINGS_MODEL", None) or os.getenv(
    "EMBEDDINGS_MODEL", "nomic-embed-text"
)
EMBEDDING_DIM = int(
    getattr(settings, "EMBEDDING_DIM", None) or os.getenv("EMBEDDING_DIM", "768")
)


def _is_filename_like(q: str) -> bool:
    """Return True only when query looks like a filename/path (not a sentence).

    Conditions (any one makes it True):
      - Regex suffix match: .(wav|mp3|pdf|md|txt|jsonl|json|docx)  (case-insensitive)
      - Contains a path separator ('/' or '\\')
      - Basename differs from whole query AND basename contains a dot and len>1
    Additionally: if query has >4 whitespace separated tokens → False (treat as sentence).
    """
    if not q:
        return False
    if len(q.strip().split()) > 4:
        return False
    q_clean = q.strip()
    if re.search(
        r"\.(wav|mp3|pdf|md|txt|jsonl|json|docx)$", q_clean, flags=re.IGNORECASE
    ):
        return True
    if "/" in q_clean or "\\" in q_clean:
        return True
    basename = os.path.basename(q_clean.replace("\\", "/"))
    if basename != q_clean and "." in basename and len(basename) > 1:
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
        chunk = textwrap.shorten(text, width=400, placeholder="...")
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
            },
            timeout=180,
        )
        r.raise_for_status()
        data = r.json()
        return (data.get("response") or "").strip()
    except Exception as e:
        return f"[LLM unavailable @ {url}] {e}\n---\nPrompt preview:\n{prompt[:600]}"


def _query_qdrant(
    client,
    collection: str,
    vec: List[float],
    top_k: int,
    qfilter,
    *,
    score_threshold: float | None = None,
):
    """Query Qdrant with query_points preference; fallback to legacy search as last resort."""
    # Try modern `query_points` with `query_filter` (some client builds require this name)
    try:
        kwargs = {
            "collection_name": collection,
            "query": vec,  # raw vector
            "limit": top_k,
            "with_payload": True,
            "with_vectors": False,
        }
        if qfilter is not None:
            kwargs["query_filter"] = qfilter
        if score_threshold is not None:
            kwargs["score_threshold"] = score_threshold
        res = client.query_points(**kwargs)
        return getattr(res, "points", res)
    except TypeError:
        pass

    # Retry `query_points` with `filter` kw (other client builds use this)
    try:
        kwargs = {
            "collection_name": collection,
            "query": vec,
            "limit": top_k,
            "with_payload": True,
            "with_vectors": False,
        }
        if qfilter is not None:
            kwargs["filter"] = qfilter
        if score_threshold is not None:
            kwargs["score_threshold"] = score_threshold
        res = client.query_points(**kwargs)
        return getattr(res, "points", res)
    except Exception:
        pass

    # Final fallback: legacy `search` (kept for maximal compatibility)
    return client.search(
        collection_name=collection,
        query_vector=vec,
        limit=top_k,
        with_payload=True,
        with_vectors=False,
        query_filter=qfilter,
    )


def _parse_kinds(args) -> set[str]:
    out: set[str] = set()
    if getattr(args, "kind", None):
        out.add(str(args.kind).strip())
    if getattr(args, "kinds", None):
        toks = [s.strip() for s in str(args.kinds).split(",") if s.strip()]
        out |= set(toks)
    valid = {"text", "pdf", "image", "audio"}
    bad = [k for k in out if k not in valid]
    if bad and getattr(args, "debug", False):
        print(f"[warn] ignoring unknown kinds: {bad}")
    return {k for k in out if k in valid}


def main():
    ap = argparse.ArgumentParser(
        description="Local Ask over Qdrant (optional Ollama)", allow_abbrev=False
    )
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
    ap.add_argument(
        "-k", "--k", "--topk", dest="k", type=int, default=6, help="Top-k chunks"
    )
    # optional scope filters
    ap.add_argument(
        "--document-id", type=str, default=None, help="Filter by document_id"
    )
    ap.add_argument("--kind", type=str, default=None, help="Filter by payload.kind")
    ap.add_argument(
        "--kinds",
        type=str,
        default=None,
        help="Comma-separated kinds to filter by (e.g., text,pdf,image,audio)",
    )
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
    ap.add_argument(
        "--no-path-fast",
        action="store_true",
        help="Disable filename/path fast-path scroll optimization (forces semantic retrieval)",
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

    # Parse kinds into a normalized set (optional)
    kinds_filter: set[str] | None = None
    parsed_kinds = _parse_kinds(args)
    if parsed_kinds:
        kinds_filter = parsed_kinds

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
        if args.no_path_fast:
            if args.debug:
                print("[info] path-fast disabled by flag")
        else:
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

                # Inject synthetic score (0.9999) + snippet so downstream formatting remains consistent.
                for p in points_fast:
                    if not hasattr(p, "score"):
                        try:
                            setattr(
                                p, "score", 0.9999
                            )  # synthetic score for exact path match
                        except Exception:
                            pass
                context, sources = _build_context(
                    points_fast, max_chars=args.context_chars
                )
                # Ensure each source has snippet + score explicitly stored.
                for p, s in zip(points_fast, sources):
                    try:
                        payload = getattr(p, "payload", None) or {}
                        snippet = (payload.get("text") or "")[:160].strip()
                        s["text"] = snippet
                        s["score"] = float(getattr(p, "score", 0.9999))
                        s["source_kind"] = "path-fast"
                    except Exception:
                        s.setdefault("text", "")
                        s.setdefault("source_kind", "path-fast")
                use_llm = not args.no_llm and (
                    args.llm or (getattr(settings, "ASK_MODE", "search") == "llm")
                )
                if use_llm:
                    # Snippet-first shortcut when top source has text.
                    top_text = (sources[0].get("text") or "").strip() if sources else ""
                    top_path = sources[0].get("path") if sources else query
                    if top_text:
                        if args.debug:
                            print(
                                "[info] path-fast short-circuit: returning snippet for",
                                top_path,
                            )
                        answer = f'Found an exact file match for {top_path}. Snippet: "{top_text}". (Showing top match.)'
                    else:
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
                        f"{(s.get('path') or '(unknown)')}  (chunk #{s.get('idx')})  score={float(s.get('score', 0.0)):.4f}"
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
                            score_val = float(s.get("score", 0.0))
                            print(
                                f"- {s.get('path')}  (chunk #{s.get('idx')})  score={score_val:.4f}"
                            )
                return
        # (duplicate path-fast block removed)

    # Standard filter (semantic path)
    # Build base conditions for document_id/path locally and add kinds filter using MatchAny for multi-kinds
    def _build_where():  # -> qm.Filter | None
        # If qdrant models aren't available, fall back to local helper for single-kind only
        if qm is None:
            fk = None
            if kinds_filter and len(kinds_filter) == 1:
                fk = next(iter(kinds_filter))
            return build_filter(document_id=args.document_id, kind=fk, path=args.path)  # type: ignore

        must_conds: list = []
        if args.document_id:
            must_conds.append(
                qm.FieldCondition(
                    key="document_id", match=qm.MatchValue(value=args.document_id)
                )
            )
        if args.path:
            must_conds.append(
                qm.FieldCondition(key="path", match=qm.MatchValue(value=args.path))
            )

        # Apply kinds filter logic only when explicitly provided
        if kinds_filter:
            if len(kinds_filter) == 1:
                v = next(iter(kinds_filter))
                # Prefer local build_filter for single-kind to keep parity with worker helpers
                return build_filter(
                    document_id=args.document_id, kind=v, path=args.path
                )  # type: ignore
            else:
                must_conds.append(
                    qm.FieldCondition(
                        key="kind", match=qm.MatchAny(any=list(kinds_filter))
                    )
                )

        if not must_conds:
            return None
        return qm.Filter(must=must_conds)

    where = _build_where()
    if args.debug:
        try:
            if where is None:
                qf_print = None
            elif hasattr(where, "model_dump"):
                qf_print = where.model_dump()  # type: ignore[attr-defined]
            elif hasattr(where, "dict"):
                qf_print = where.dict()  # type: ignore
            else:
                qf_print = where
        except Exception:
            qf_print = where
        print(f"[debug] qfilter: {qf_print if qf_print is not None else None}")

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
            points = _query_qdrant(
                client,
                collection,
                qv,
                args.k,
                where,
                score_threshold=args.min_score,
            )
        except Exception as e:
            print(f"[error] search (manual --min-score) failed: {e}")
            sys.exit(1)
    else:
        # Default path: use client.query_points (modern API)
        try:
            points = _query_qdrant(client, collection, qv, args.k, where)
        except Exception as e:
            print(f"[error] query_points failed: {e}")
            sys.exit(1)

        # Fallback: if no hits, re-run with raw client.search and score_threshold=0.0
        if not points:
            try:
                points = _query_qdrant(
                    client,
                    collection,
                    qv,
                    args.k,
                    where,
                    score_threshold=0.0,
                )
                if points:
                    fallback_used = True
                    print(
                        "[info] fallback: retry with score_threshold=0.0 returned hits"
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
            f"{(s.get('path') or '(unknown)')}  (chunk #{s.get('idx')})  score={float(s.get('score', 0.0)):.4f}"
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
                print(
                    f"- {s.get('path')}  (chunk #{s.get('idx')})  score={float(s.get('score', 0.0)):.4f}"
                )


if __name__ == "__main__":
    t0 = time.time()
    try:
        main()
    finally:
        dt = time.time() - t0
        print(f"\n[done in {dt:.2f}s]")
