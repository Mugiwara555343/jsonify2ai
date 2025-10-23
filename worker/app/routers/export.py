from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import PlainTextResponse, StreamingResponse
from qdrant_client import QdrantClient
from worker.app.config import settings
from worker.app.services.qdrant_client import get_qdrant_client
from worker.app.telemetry import telemetry
from worker.app.dependencies.auth import require_auth
import logging
import io
import os
import os.path
import zipfile
import time
import uuid

logger = logging.getLogger(__name__)

router = APIRouter()


def _scroll_by_docid(client: QdrantClient, collection: str, document_id: str) -> list:
    """Scroll through points for a document_id in a collection.
    Returns empty list if collection doesn't exist (404).
    """
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    from qdrant_client.http.exceptions import UnexpectedResponse

    try:
        filt = Filter(
            must=[
                FieldCondition(key="document_id", match=MatchValue(value=document_id))
            ]
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
    except UnexpectedResponse as e:
        if e.status_code == 404:
            # Collection doesn't exist, return empty list
            return []
        raise


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
    _: bool = Depends(require_auth),
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


@router.get("/export/archive")
def export_archive_get(
    document_id: str = Query(..., description="Document ID to export"),
    collection: str | None = Query(
        None,
        description="Optional collection name: jsonify2ai_chunks_768 or jsonify2ai_images_768",
    ),
    _: bool = Depends(require_auth),
):
    """Stream a ZIP containing JSONL rows and the original source file if present.

    - If collection is omitted, try chunks first, then images.
    - Do everything in-memory; no disk writes.
    """
    # Instrument request
    request_id = str(uuid.uuid4())
    start_time = time.time()

    # Log request start
    telemetry.log_json(
        "export_archive_start",
        level="info",
        request_id=request_id,
        document_id=document_id,
        collection=collection,
    )

    try:
        client = get_qdrant_client()

        # Normalize requested collection: accept full names or simple hints
        def normalize_collection(value: str | None) -> str:
            if not value or value.strip() == "":
                return settings.QDRANT_COLLECTION
            v = value.lower()
            if "image" in v:
                return settings.QDRANT_COLLECTION_IMAGES
            if "chunk" in v:
                return settings.QDRANT_COLLECTION
            # fallback: if matches exactly either collection, honor it
            if value == settings.QDRANT_COLLECTION_IMAGES:
                return settings.QDRANT_COLLECTION_IMAGES
            if value == settings.QDRANT_COLLECTION:
                return settings.QDRANT_COLLECTION
            # default to chunks
            return settings.QDRANT_COLLECTION

        primary = normalize_collection(collection)

        # Try primary collection
        points = _scroll_by_docid(client, primary, document_id)
        used_collection = primary

        # If none and no strong collection provided, try the other one
        if not points and (not collection or collection.strip() == ""):
            alt = (
                settings.QDRANT_COLLECTION_IMAGES
                if primary == settings.QDRANT_COLLECTION
                else settings.QDRANT_COLLECTION
            )
            alt_points = _scroll_by_docid(client, alt, document_id)
            if alt_points:
                points = alt_points
                used_collection = alt

        if not points:
            raise HTTPException(status_code=404, detail="no points for document_id")

        # Accumulate JSONL rows and discover a source file if available
        jsonl_buf = io.StringIO()
        source_path: str | None = None

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
            import json as _json

            jsonl_buf.write(_json.dumps(row, ensure_ascii=False))
            jsonl_buf.write("\n")

            # Determine source file to include (first existing path under data/)
            if not source_path:
                candidate = pl.get("path")
                if isinstance(candidate, str) and candidate:
                    # Normalize and gate to data/ to avoid traversal
                    abs_candidate = os.path.abspath(candidate)
                    data_root = os.path.abspath(os.path.join(os.getcwd(), "data"))
                    if abs_candidate.startswith(data_root) and os.path.exists(
                        abs_candidate
                    ):
                        source_path = abs_candidate

        # Determine collection type for metadata
        collection_type = (
            "images"
            if used_collection == settings.QDRANT_COLLECTION_IMAGES
            else "chunks"
        )

        # Build ZIP in-memory
        zip_bytes = io.BytesIO()
        with zipfile.ZipFile(
            zip_bytes, mode="w", compression=zipfile.ZIP_DEFLATED
        ) as zf:
            jsonl_name = (
                "images.jsonl"
                if used_collection == settings.QDRANT_COLLECTION_IMAGES
                else "chunks.jsonl"
            )
            zf.writestr(jsonl_name, jsonl_buf.getvalue().encode("utf-8"))

            # Add manifest.json with metadata
            import datetime
            import json as _json

            manifest = {
                "collection": used_collection,
                "document_id": document_id,
                "count": len(points),
                "generated_at": datetime.datetime.now().isoformat(),
                "collection_type": collection_type,
                "files": [jsonl_name],
            }

            if source_path and os.path.exists(source_path):
                manifest["files"].append(f"source/{os.path.basename(source_path)}")

            zf.writestr(
                "manifest.json", _json.dumps(manifest, indent=2).encode("utf-8")
            )

            # Add README.txt with metadata
            readme_content = f"""jsonify2ai Export Archive
========================

Document ID: {document_id}
Collection: {used_collection}
Collection Type: {collection_type}
Export Timestamp: {datetime.datetime.now().isoformat()}
Point Count: {len(points)}

Files in this archive:
- {jsonl_name}: JSONL data with all vector points
- manifest.json: Export metadata
- source/: Original source file (if available)

This archive was generated by jsonify2ai export functionality.
For more information, visit: https://github.com/Mugiwara555343/jsonify2ai
"""
            zf.writestr("README.txt", readme_content.encode("utf-8"))

            if source_path and os.path.exists(source_path):
                # Store under source/<basename>
                arcname = os.path.join("source", os.path.basename(source_path))
                zf.write(source_path, arcname=arcname)

        zip_bytes.seek(0)

        # Create a more descriptive filename: export_<document_id>_<collection>.zip
        # Fallback to export_<document_id>.zip if collection unknown
        if collection_type in ["chunks", "images"]:
            filename = f"export_{document_id}_{collection_type}.zip"
        else:
            filename = f"export_{document_id}.zip"

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Collection-Used": used_collection,
        }

        logger.info(
            f"Export ZIP: streamed {len(points)} points for document {document_id} from collection {used_collection}"
        )

        # Log success and increment counter
        duration_ms = int((time.time() - start_time) * 1000)
        telemetry.increment("export_total")
        telemetry.log_json(
            "export_archive_success",
            level="info",
            request_id=request_id,
            document_id=document_id,
            collection=used_collection,
            duration_ms=duration_ms,
            points_count=len(points),
            status="success",
        )

        return StreamingResponse(
            zip_bytes, media_type="application/zip", headers=headers
        )

    except Exception as e:
        # Log failure
        duration_ms = int((time.time() - start_time) * 1000)
        telemetry.log_json(
            "export_archive_failure",
            level="error",
            request_id=request_id,
            document_id=document_id,
            collection=collection,
            duration_ms=duration_ms,
            status="error",
            error=str(e),
        )
        raise
