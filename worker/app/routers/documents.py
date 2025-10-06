from __future__ import annotations

from fastapi import APIRouter
from qdrant_client import QdrantClient
from worker.app.config import settings
from worker.app.services.qdrant_client import get_qdrant_client
from collections import defaultdict
from typing import Dict, List, Any

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

    # Get documents from both collections
    chunks_docs = _scroll_all_documents(client, settings.QDRANT_COLLECTION)
    images_docs = _scroll_all_documents(client, settings.QDRANT_COLLECTION_IMAGES)

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
