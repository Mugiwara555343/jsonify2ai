from fastapi import APIRouter
from pydantic import BaseModel
from typing import List
import requests
import time
from qdrant_client import QdrantClient
from worker.app.config import settings
from worker.app.services.embed_ollama import embed_texts
from worker.app.telemetry import telemetry

router = APIRouter()


class AskBody(BaseModel):
    query: str
    k: int = 6
    mode: str = None
    document_id: str = None
    path_prefix: str = None


def _search(q: str, k: int, document_id: str = None, path_prefix: str = None):
    vec = embed_texts([q])[0]
    qc = QdrantClient(url=settings.QDRANT_URL)

    # Build filter if document_id or path_prefix provided
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    qf = None
    if document_id or path_prefix:
        must = []
        if document_id:
            must.append(
                FieldCondition(key="document_id", match=MatchValue(value=document_id))
            )
        if path_prefix:
            # Use prefix match for path_prefix (if supported) or exact match
            # For now, use exact match on path field
            must.append(FieldCondition(key="path", match=MatchValue(value=path_prefix)))
        if must:
            qf = Filter(must=must)

    def go(col):
        hits = qc.search(
            collection_name=col, query_vector=vec, limit=k, query_filter=qf
        )
        out = []
        for h in hits:
            p = h.payload or {}
            out.append({"id": str(h.id), "score": float(h.score), **p})
        return out

    # Always perform text search
    text_hits = go(settings.QDRANT_COLLECTION)

    # Only attempt images search when IMAGES_CAPTION is enabled
    img_hits = []
    if getattr(settings, "IMAGES_CAPTION", 0):
        try:
            img_hits = go(
                getattr(settings, "QDRANT_COLLECTION_IMAGES", "jsonify2ai_images_768")
            )
        except Exception as e:
            import logging

            log = logging.getLogger(__name__)
            log.warning(f"[ask] images search skipped: {e}")
            img_hits = []

    return text_hits, img_hits


def _format_prompt(q: str, text_hits: List[dict], img_hits: List[dict]):
    lines = [
        "You are a concise assistant. Answer using ONLY the provided sources. If insufficient, say you don't know.",
        f"Question: {q}",
        "---- SOURCES ----",
    ]
    for i, h in enumerate(text_hits):
        if "text" in h:
            lines.append(f"[T{i}] {h['text'][:700]}")
    for i, h in enumerate(img_hits):
        if "caption" in h:
            lines.append(f"[I{i}] {h['caption']}")
    lines.append(
        "Respond with a short paragraph and cite like [T0] [I0] where relevant."
    )
    return "\n".join(lines)


def _ollama_generate(prompt: str):
    try:
        r = requests.post(
            f"{settings.OLLAMA_URL}/api/generate",
            json={
                "model": settings.ASK_MODEL,
                "prompt": prompt,
                "options": {
                    "temperature": settings.ASK_TEMP,
                    "top_p": settings.ASK_TOP_P,
                },
                "stream": False,
                "keep_alive": "1m",
            },
            timeout=60,
        )
        if r.ok:
            j = r.json()
            return j.get("response", "").strip()
    except Exception:
        pass
    return None


@router.post("/ask")
def ask(body: AskBody):
    text_hits, img_hits = _search(
        body.query, body.k, body.document_id, body.path_prefix
    )
    sources = text_hits[: body.k // 2] + img_hits[: body.k - body.k // 2]

    # Normalize requested mode: "retrieval" maps to "search"
    mode = (body.mode or settings.ASK_MODE or "search").lower()
    if mode == "retrieval":
        mode = "search"

    import logging

    log = logging.getLogger(__name__)

    if mode == "search":
        # Retrieval-only path
        log.info(f"[ask] running in search mode for query: {body.query[:50]}...")
        snippets = []
        for h in text_hits[:2] + img_hits[:2]:
            s = h.get("text") or h.get("caption")
            if s:
                snippets.append(s[:220])
        summary = " • ".join(snippets) or "(no matching snippets)"
        result = {"ok": True, "mode": "search", "answer": summary, "sources": sources}

        # Optional LLM synthesis if enabled
        if settings.LLM_PROVIDER == "ollama" and snippets:
            result = _try_llm_synthesis(body.query, result, log)

        return result
    else:
        # LLM path
        log.info(f"[ask] running in llm mode for query: {body.query[:50]}...")
        prompt = _format_prompt(body.query, text_hits, img_hits)
        resp = _ollama_generate(prompt)
        if resp:
            return {
                "ok": True,
                "mode": "llm",
                "model": settings.ASK_MODEL,
                "answer": resp,
                "sources": sources,
            }
        # Fallback to search if LLM fails
        log.warning("[ask] LLM generation failed, falling back to search mode")
        snippets = []
        for h in text_hits[:2] + img_hits[:2]:
            s = h.get("text") or h.get("caption")
            if s:
                snippets.append(s[:220])
        summary = " • ".join(snippets) or "(no matching snippets)"
        result = {"ok": True, "mode": "search", "answer": summary, "sources": sources}

        # Optional LLM synthesis if enabled
        if settings.LLM_PROVIDER == "ollama" and snippets:
            result = _try_llm_synthesis(body.query, result, log)

        return result


def _truncate(s: str, limit: int) -> str:
    """Truncate string with ellipsis."""
    if len(s) <= limit:
        return s
    return s[:limit] + "…"


def _build_prompt(question: str, snippets: list[str]) -> str:
    """Build concise, grounded prompt for small models."""
    joined = "\n".join(f"{i+1}) {snip}" for i, snip in enumerate(snippets))
    return (
        "You are a concise assistant. Answer using ONLY the snippets below.\n"
        'If information is missing, reply: "Not enough information."\n\n'
        f"Question: {question}\n\n"
        "Snippets:\n"
        f"{joined}\n\n"
        "Requirements:\n"
        "- 3–6 sentences maximum.\n"
        "- Be factual and avoid speculation.\n"
        "- If helpful, mention filenames or document_id present in snippets.\n"
    )


def _select_snippets(
    results: list[dict],
    max_keep: int = 5,
    min_score: float = 0.2,
    per_snippet_chars: int = 2000,
    total_chars: int = 8000,
) -> list[str]:
    """
    Filter and cap retrieval results.

    Args:
        results: List of {"text":..., "score":..., "path":..., "document_id":...}
        max_keep: Maximum number of snippets to keep
        min_score: Minimum score threshold
        per_snippet_chars: Max chars per snippet
        total_chars: Max total chars across all snippets

    Returns:
        List of filtered snippet strings with metadata
    """
    # Take top-10, drop low scores
    pool = results[:10]
    pool = [r for r in pool if (r.get("score") or 0) >= min_score]

    # Build snippets with metadata, obey caps
    out, acc = [], 0
    for r in pool:
        text = str(r.get("text") or "")
        meta = []
        if r.get("path"):
            meta.append(f"[path: {r['path']}]")
        if r.get("document_id"):
            meta.append(f"[doc: {r['document_id']}]")

        snip = _truncate(text, per_snippet_chars)
        if meta:
            snip = snip + "\n" + " ".join(meta)

        if acc + len(snip) > total_chars:
            break

        out.append(snip)
        acc += len(snip)

        if len(out) >= max_keep:
            break

    return out


def _try_llm_synthesis(query: str, result: dict, log) -> dict:
    """
    Try optional LLM synthesis using Ollama if enabled and sources exist.
    Adds 'final' field to result on success.
    """
    if settings.LLM_PROVIDER != "ollama":
        return result

    # Check if we have sources to synthesize
    sources = result.get("sources", [])
    if not sources or len(sources) == 0:
        return result

    try:
        from worker.providers.llm.ollama import generate as ollama_generate

        # Filter and cap retrieval
        snippets = _select_snippets(sources)
        if not snippets:
            return result

        # Build concise prompt
        prompt = _build_prompt(query, snippets)

        # Call Ollama generate
        start_time = time.time()
        final_answer = ollama_generate(prompt)
        duration_ms = int((time.time() - start_time) * 1000)

        if final_answer:
            result["final"] = final_answer
            log.info(f"[ask] synthesis successful ({duration_ms}ms)")
        else:
            log.warning("[ask] synthesis failed, result unchanged")

        # Telemetry
        telemetry.increment("ask_synth_total")
        telemetry.log_json(
            "ask_synthesis", duration_ms=duration_ms, success=bool(final_answer)
        )

    except Exception as e:
        log.warning(f"[ask] synthesis error: {e}")
        # Don't fail the request, just continue without 'final'

    return result
