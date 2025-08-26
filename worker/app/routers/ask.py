from fastapi import APIRouter
from pydantic import BaseModel
from typing import List
import requests, json
from qdrant_client import QdrantClient
from ..config import settings
from ..services.embed_ollama import embed_texts

router = APIRouter()

class AskBody(BaseModel):
    query: str
    k: int = 6

def _search(q: str, k: int):
    vec = embed_texts([q])[0]
    qc = QdrantClient(url=settings.QDRANT_URL)
    def go(col):
        hits = qc.search(collection_name=col, query_vector=vec, limit=k)
        out=[]; 
        for h in hits:
            p=h.payload or {}
            out.append({"id": str(h.id), "score": float(h.score), **p})
        return out
    return go(settings.QDRANT_COLLECTION), go(getattr(settings,"QDRANT_COLLECTION_IMAGES","jsonify2ai_images_768"))

def _format_prompt(q:str, text_hits:List[dict], img_hits:List[dict]):
    lines=["You are a concise assistant. Answer using ONLY the provided sources. If insufficient, say you don't know.",
           f"Question: {q}", "---- SOURCES ----"]
    for i,h in enumerate(text_hits):
        if "text" in h: lines.append(f"[T{i}] {h['text'][:700]}")
    for i,h in enumerate(img_hits):
        if "caption" in h: lines.append(f"[I{i}] {h['caption']}")
    lines.append("Respond with a short paragraph and cite like [T0] [I0] where relevant.")
    return "\n".join(lines)

def _ollama_generate(prompt:str):
    try:
        r = requests.post(f"{settings.OLLAMA_URL}/api/generate",
            json={"model": settings.ASK_MODEL, "prompt": prompt, "options":{
                  "temperature": settings.ASK_TEMP, "top_p": settings.ASK_TOP_P},
                  "stream": False, "keep_alive": "1m"},
            timeout=60)
        if r.ok:
            j=r.json()
            return j.get("response","").strip()
    except Exception:
        pass
    return None

@router.post("/ask")
def ask(body: AskBody):
    text_hits, img_hits = _search(body.query, body.k)
    sources = text_hits[: body.k//2] + img_hits[: body.k - body.k//2]
    if settings.ASK_MODE.lower()=="llm":
        prompt = _format_prompt(body.query, text_hits, img_hits)
        resp = _ollama_generate(prompt)
        if resp:
            return {"ok": True, "mode":"llm", "model": settings.ASK_MODEL,
                    "answer": resp, "sources": sources}
    # fallback / retrieval-only
    # tiny summary: top 2 snippets
    snippets=[]
    for h in (text_hits[:2]+img_hits[:2]):
        s = h.get("text") or h.get("caption")
        if s: snippets.append(s[:220])
    summary = " • ".join(snippets) or "(no matching snippets)"
    return {"ok": True, "mode":"search", "answer": summary, "sources": sources}
