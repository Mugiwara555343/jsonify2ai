from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import requests
import time
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, Range
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
    answer_mode: str = None
    ingested_after: Optional[str] = None
    ingested_before: Optional[str] = None


def _parse_iso_to_timestamp(iso_str: str) -> Optional[int]:
    """Parse ISO-8601 string to unix timestamp (seconds). Returns None if invalid."""
    try:
        # Handle both 'Z' and '+00:00' formats
        iso_str = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso_str)
        return int(dt.timestamp())
    except (ValueError, AttributeError):
        return None


def _normalize_source(hit: dict) -> dict:
    """Convert raw Qdrant hit to standardized Source object."""
    # Handle both direct fields and payload
    payload = hit.get("payload", {}) if isinstance(hit.get("payload"), dict) else {}

    # Extract text excerpt (trim to 400-800 chars by default, use 600 as middle ground)
    text = (
        hit.get("text")
        or payload.get("text")
        or hit.get("caption")
        or payload.get("caption")
        or ""
    )
    if len(text) > 600:
        text = text[:600] + "…"

    # Build meta object
    meta = payload.get("meta", {}) if isinstance(payload.get("meta"), dict) else {}
    if not isinstance(meta, dict):
        meta = {}

    # Preserve existing meta fields
    source_meta = {}
    for key in [
        "ingested_at",
        "ingested_at_ts",
        "source_system",
        "title",
        "logical_path",
        "conversation_id",
        "source_file",
    ]:
        if key in meta:
            source_meta[key] = meta[key]

    # Allow passthrough of additional meta keys
    for k, v in meta.items():
        if k not in source_meta:
            source_meta[k] = v

    return {
        "id": str(hit.get("id", "")),
        "document_id": hit.get("document_id") or payload.get("document_id", ""),
        "path": hit.get("path") or payload.get("path"),
        "kind": hit.get("kind") or payload.get("kind"),
        "idx": hit.get("idx") or payload.get("idx") or hit.get("chunk_index"),
        "score": hit.get("score"),
        "text": text,
        "meta": source_meta if source_meta else None,
    }


def _search(
    q: str,
    k: int,
    document_id: str = None,
    path_prefix: str = None,
    ingested_after: Optional[str] = None,
    ingested_before: Optional[str] = None,
):
    vec = embed_texts([q])[0]
    qc = QdrantClient(url=settings.QDRANT_URL)

    # Build filter if document_id, path_prefix, or time filters provided
    qf = None
    must = []
    if document_id:
        must.append(
            FieldCondition(key="document_id", match=MatchValue(value=document_id))
        )
    if path_prefix:
        # Use prefix match for path_prefix (if supported) or exact match
        # For now, use exact match on path field
        must.append(FieldCondition(key="path", match=MatchValue(value=path_prefix)))

    # Time range filters on meta.ingested_at_ts
    if ingested_after:
        ts_after = _parse_iso_to_timestamp(ingested_after)
        if ts_after is not None:
            must.append(
                FieldCondition(key="meta.ingested_at_ts", range=Range(gte=ts_after))
            )
    if ingested_before:
        ts_before = _parse_iso_to_timestamp(ingested_before)
        if ts_before is not None:
            must.append(
                FieldCondition(key="meta.ingested_at_ts", range=Range(lt=ts_before))
            )

    if must:
        qf = Filter(must=must)

    def go(col):
        hits = qc.query_points(
            collection_name=col, query=vec, limit=k, query_filter=qf
        ).points
        out = []
        for h in hits:
            p = h.payload or {}
            raw_hit = {"id": str(h.id), "score": float(h.score), **p}
            # Normalize to standardized Source shape
            normalized = _normalize_source(raw_hit)
            out.append(normalized)
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
        'You are a concise assistant. Answer using ONLY the provided sources. Do not use any knowledge outside these sources. If insufficient, reply: "I don\'t have enough in the indexed sources to answer that yet."',
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
        body.query,
        body.k,
        body.document_id,
        body.path_prefix,
        body.ingested_after,
        body.ingested_before,
    )
    # Sources are already normalized by _search()
    sources = text_hits[: body.k // 2] + img_hits[: body.k - body.k // 2]

    # Determine mode: prioritize answer_mode, then mode, then settings
    # answer_mode="retrieve" means retrieve-only (no synthesis)
    # answer_mode="synthesize" means try synthesis if available
    answer_mode = body.answer_mode
    if answer_mode:
        answer_mode = answer_mode.lower()

    # Normalize requested mode: "retrieval" maps to "search"
    mode = (body.mode or settings.ASK_MODE or "search").lower()
    if mode == "retrieval":
        mode = "search"

    import logging

    log = logging.getLogger(__name__)

    # If answer_mode is "retrieve", force retrieve-only mode
    if answer_mode == "retrieve" or mode == "search":
        # Retrieval-only path
        log.info(f"[ask] running in retrieve mode for query: {body.query[:50]}...")
        result = {
            "ok": True,
            "mode": "retrieve",
            "answer": "",  # Empty answer for retrieve-only
            "sources": sources,
            "stats": {"k": body.k, "returned": len(sources)},
        }

        # Optional LLM synthesis if enabled (but only if answer_mode is not "retrieve")
        if answer_mode != "retrieve" and settings.LLM_PROVIDER == "ollama" and sources:
            result = _try_llm_synthesis(body.query, result, log, body.answer_mode)

        return result
    else:
        # LLM/synthesize path
        log.info(f"[ask] running in synthesize mode for query: {body.query[:50]}...")
        prompt = _format_prompt(body.query, text_hits, img_hits)
        resp = _ollama_generate(prompt)
        if resp:
            return {
                "ok": True,
                "mode": "synthesize",
                "model": settings.ASK_MODEL,
                "answer": resp,
                "sources": sources,
                "stats": {"k": body.k, "returned": len(sources)},
            }
        # Fallback to retrieve if LLM fails
        log.warning("[ask] LLM generation failed, falling back to retrieve mode")
        result = {
            "ok": True,
            "mode": "retrieve",
            "answer": "",
            "sources": sources,
            "stats": {"k": body.k, "returned": len(sources)},
        }

        # Optional LLM synthesis if enabled (but only if answer_mode is not "retrieve")
        if answer_mode != "retrieve" and settings.LLM_PROVIDER == "ollama" and sources:
            result = _try_llm_synthesis(body.query, result, log, body.answer_mode)

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
        "You are a concise assistant. Answer using ONLY the snippets below. Do not use any knowledge outside these snippets.\n"
        'If information is missing, reply: "I don\'t have enough in the indexed sources to answer that yet."\n\n'
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


def _try_llm_synthesis(query: str, result: dict, log, answer_mode: str = None) -> dict:
    """
    Try optional LLM synthesis using Ollama if enabled and sources exist.
    Adds 'final' field to result on success.
    """
    # If answer_mode is "retrieve", skip synthesis entirely
    if answer_mode == "retrieve":
        result["synth_skipped_reason"] = "retrieve_only"
        log.info("[ask] synthesis skipped: retrieve_only mode")
        return result

    if settings.LLM_PROVIDER != "ollama":
        return result

    # Check if we have sources to synthesize
    sources = result.get("sources", [])
    if not sources or len(sources) == 0:
        result["synth_skipped_reason"] = "no_sources"
        log.info("[ask] synthesis skipped: no sources")
        return result

    # Compute top_score from sources
    top_score = max((s.get("score", 0.0) for s in sources), default=0.0)
    if top_score < settings.MIN_SYNTH_SCORE:
        result["synth_skipped_reason"] = "low_confidence"
        result["top_score"] = top_score
        result["min_synth_score"] = settings.MIN_SYNTH_SCORE
        log.info(
            f"[ask] synthesis skipped: top_score {top_score:.3f} < {settings.MIN_SYNTH_SCORE}"
        )
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
            result["mode"] = "synthesize"  # Update mode to reflect synthesis
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
