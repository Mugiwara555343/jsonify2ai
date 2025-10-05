from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse
from qdrant_client import QdrantClient
from worker.app.config import settings
from worker.app.services.qdrant_client import get_qdrant_client

router = APIRouter()


def _export_doc(client: QdrantClient, collection: str, document_id: str) -> str:
    # Stream via scroll; emit JSONL per point with stable fields
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    filt = Filter(
        must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
    )
    out_lines = []
    next_page = None
    while True:
        points, next_page = client.scroll(
            collection_name=collection,
            scroll_filter=filt,
            with_payload=True,
            with_vectors=False,
            limit=256,
            offset=next_page,
        )
        if not points:
            break
        for p in points:
            pl = p.payload or {}
            row = {
                "id": str(p.id),
                "document_id": pl.get("document_id"),
                "path": pl.get("path"),
                "kind": pl.get("kind"),
                "idx": pl.get("idx"),
                "text": pl.get("text"),
                "meta": pl.get("meta", {}),
            }
            import json

            out_lines.append(json.dumps(row, ensure_ascii=False))
        if next_page is None:
            break
    return "\n".join(out_lines)


@router.get("/export", response_class=PlainTextResponse)
def export_get(
    document_id: str = Query(..., description="Document ID to export"),
    collection: str | None = Query(
        None, description="Override collection: chunks or images"
    ),
):
    client = get_qdrant_client()
    coll = (
        settings.QDRANT_COLLECTION
        if collection in (None, "", "chunks")
        else settings.QDRANT_COLLECTION_IMAGES
    )
    data = _export_doc(client, coll, document_id)
    if not data:
        raise HTTPException(status_code=404, detail="no points for document_id")
    fname = f'export_{document_id}_{ "images" if coll == settings.QDRANT_COLLECTION_IMAGES else "chunks" }.jsonl'
    headers = {"Content-Disposition": f'attachment; filename="{fname}"'}
    return PlainTextResponse(content=data, headers=headers)
