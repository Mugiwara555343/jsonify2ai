from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException, Depends
from qdrant_client import QdrantClient
from worker.app.config import settings
from worker.app.services.qdrant_client import get_qdrant_client, delete_by_document_id
from worker.app.dependencies.auth import require_auth
from collections import defaultdict
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

router = APIRouter()


def _scroll_all_documents(
    client: QdrantClient, collection: str
) -> List[Dict[str, Any]]:
    """Scroll through all points in a collection and aggregate by document_id"""
    from qdrant_client.models import Filter

    # Scroll through all points with payload
    all_points = []
    next_page = None
    while True:
        points, next_page = client.scroll(
            collection_name=collection,
            scroll_filter=Filter(must=[]),  # No filter, get all points
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

    # Aggregate by document_id
    doc_aggregates = defaultdict(
        lambda: {
            "document_id": "",
            "kinds": set(),
            "paths": set(),
            "counts": defaultdict(int),
        }
    )

    for point in all_points:
        payload = point.payload or {}
        doc_id = payload.get("document_id")
        if not doc_id:
            continue

        doc_aggregates[doc_id]["document_id"] = doc_id
        doc_aggregates[doc_id]["kinds"].add(payload.get("kind", "unknown"))
        doc_aggregates[doc_id]["paths"].add(payload.get("path", ""))
        doc_aggregates[doc_id]["counts"][payload.get("kind", "unknown")] += 1

    # Convert to list format
    result = []
    for doc_id, data in doc_aggregates.items():
        # Convert sets to lists and limit paths to first few
        paths_list = list(data["paths"])[:3]  # Limit to first 3 paths
        kinds_list = list(data["kinds"])

        result.append(
            {
                "document_id": doc_id,
                "kinds": kinds_list,
                "paths": paths_list,
                "counts": dict(data["counts"]),
            }
        )

    return result


@router.get("/documents")
def get_documents():
    """Get list of documents across both collections"""
    client = get_qdrant_client()

    # Get documents from both collections (handle missing collections gracefully)
    try:
        chunks_docs = _scroll_all_documents(client, settings.QDRANT_COLLECTION)
    except Exception as e:
        error_msg = str(e).lower()
        # Only suppress collection-not-found errors; log and re-raise others
        if "does not exist" in error_msg or "not found" in error_msg:
            logger.debug(
                f"Collection '{settings.QDRANT_COLLECTION}' does not exist yet, returning empty list"
            )
            chunks_docs = []
        else:
            # Critical error: configuration, network, or other issues
            logger.error(
                f"Failed to retrieve documents from collection '{settings.QDRANT_COLLECTION}': {e}",
                exc_info=True,
            )
            raise

    try:
        images_docs = _scroll_all_documents(client, settings.QDRANT_COLLECTION_IMAGES)
    except Exception as e:
        error_msg = str(e).lower()
        # Only suppress collection-not-found errors; log and re-raise others
        if "does not exist" in error_msg or "not found" in error_msg:
            logger.debug(
                f"Collection '{settings.QDRANT_COLLECTION_IMAGES}' does not exist yet, returning empty list"
            )
            images_docs = []
        else:
            # Critical error: configuration, network, or other issues
            logger.error(
                f"Failed to retrieve documents from collection '{settings.QDRANT_COLLECTION_IMAGES}': {e}",
                exc_info=True,
            )
            raise

    # Merge documents (in case same document_id exists in both collections)
    merged_docs = {}

    for doc in chunks_docs + images_docs:
        doc_id = doc["document_id"]
        if doc_id in merged_docs:
            # Merge data
            existing = merged_docs[doc_id]
            existing["kinds"] = list(set(existing["kinds"] + doc["kinds"]))
            existing["paths"] = list(set(existing["paths"] + doc["paths"]))[:3]
            # Merge counts
            for kind, count in doc["counts"].items():
                existing["counts"][kind] = existing["counts"].get(kind, 0) + count
        else:
            merged_docs[doc_id] = doc

    # Convert to list and sort by document_id (most recent first, assuming UUIDs sort chronologically)
    result = list(merged_docs.values())
    result.sort(key=lambda x: x["document_id"], reverse=True)

    # Limit to last 200 documents
    return result[:200]


@router.delete("/documents/{document_id}")
def delete_document(document_id: str, _: bool = Depends(require_auth)):
    """Delete a document from both collections. Gated by AUTH_MODE or ENABLE_DOC_DELETE."""
    # Check gating: AUTH_MODE=local OR ENABLE_DOC_DELETE=true
    auth_mode = os.getenv("AUTH_MODE", "local")
    enable_delete = os.getenv("ENABLE_DOC_DELETE", "").lower() == "true"

    if auth_mode != "local" and not enable_delete:
        raise HTTPException(
            status_code=403,
            detail="Delete not enabled. Set AUTH_MODE=local or ENABLE_DOC_DELETE=true",
        )

    client = get_qdrant_client()

    # Delete from both collections
    deleted_chunks = delete_by_document_id(
        document_id, client=client, collection_name=settings.QDRANT_COLLECTION
    )
    deleted_images = delete_by_document_id(
        document_id, client=client, collection_name=settings.QDRANT_COLLECTION_IMAGES
    )

    logger.info(
        f"Deleted document {document_id}: chunks={deleted_chunks}, images={deleted_images}"
    )

    return {
        "ok": True,
        "document_id": document_id,
        "deleted_chunks": deleted_chunks,
        "deleted_images": deleted_images,
    }
