from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse
from qdrant_client import QdrantClient
from worker.app.config import settings
from worker.app.services.qdrant_client import get_qdrant_client
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


def _scroll_by_docid(client: QdrantClient, collection: str, document_id: str) -> list:
    """Scroll through points for a document_id in a collection"""
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    filt = Filter(
        must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
    )
    all_points = []
    next_page = None
    while True:
        points, next_page = client.scroll(
            collection_name=collection,
            scroll_filter=filt,
            with_payload=True,
            with_vectors=False,
            limit=8192,
            offset=next_page,
        )
        if not points:
            break
        all_points.extend(points)
        if next_page is None:
            break
    return all_points


def _export_doc(client: QdrantClient, collection: str, document_id: str) -> str:
    # Stream via scroll; emit JSONL per point with stable fields
    points = _scroll_by_docid(client, collection, document_id)
    out_lines = []
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
    return "\n".join(out_lines)


@router.get("/export", response_class=PlainTextResponse)
def export_get(
    document_id: str = Query(..., description="Document ID to export"),
    collection: str | None = Query(
        None, description="Override collection: chunks or images"
    ),
):
    client = get_qdrant_client()

    # Try the specified collection first
    coll = (
        settings.QDRANT_COLLECTION
        if collection in (None, "", "chunks")
        else settings.QDRANT_COLLECTION_IMAGES
    )

    # Check if we have points in the primary collection
    points = _scroll_by_docid(client, coll, document_id)

    # If no points and no specific collection was requested, try the other collection
    if not points and (not collection or collection == ""):
        alt_coll = (
            settings.QDRANT_COLLECTION_IMAGES
            if coll == settings.QDRANT_COLLECTION
            else settings.QDRANT_COLLECTION
        )
        alt_points = _scroll_by_docid(client, alt_coll, document_id)
        if alt_points:
            points = alt_points
            coll = alt_coll
            logger.info(f"Export fallback: found document {document_id} in {coll}")

    if not points:
        raise HTTPException(status_code=404, detail="no points for document_id")

    # Generate JSONL data
    out_lines = []
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

    data = "\n".join(out_lines)
    fname = f'export_{document_id}_{ "images" if coll == settings.QDRANT_COLLECTION_IMAGES else "chunks" }.jsonl'
    headers = {
        "Content-Disposition": f'attachment; filename="{fname}"',
        "X-Collection-Used": coll,
    }

    logger.info(
        f"Export: streamed {len(points)} points for document {document_id} from collection {coll}"
    )
    return PlainTextResponse(content=data, headers=headers)
