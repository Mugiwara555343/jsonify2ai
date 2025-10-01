#!/usr/bin/env python3
import os
import sys
import time
import argparse
from pathlib import Path
from qdrant_client import QdrantClient
from qdrant_client.models import PayloadSchemaType, VectorParams, Distance

# Add repo root to path for imports
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

QDRANT = os.getenv("QDRANT_URL", "http://localhost:6333")
CHUNKS = os.getenv("QDRANT_COLLECTION", "jsonify2ai_chunks_768")
IMAGES = os.getenv("QDRANT_COLLECTION_IMAGES", "jsonify2ai_images_768")

FIELDS = ["document_id", "kind", "path"]


def put_index(client: QdrantClient, coll: str, field: str) -> None:
    try:
        client.create_payload_index(
            collection_name=coll,
            field_name=field,
            field_schema=PayloadSchemaType.KEYWORD,
        )
        print(f"[ok] index {coll}.{field}")
    except Exception as e:
        if "already exists" in str(e).lower() or "already created" in str(e).lower():
            print(f"[ok] index {coll}.{field} (exists)")
        else:
            # Retry once for transient readiness races
            time.sleep(0.8)
            try:
                client.create_payload_index(
                    collection_name=coll,
                    field_name=field,
                    field_schema=PayloadSchemaType.KEYWORD,
                )
                print(f"[ok] index {coll}.{field} (retry)")
            except Exception as e2:
                raise SystemExit(f"[fail] create index {coll}.{field} -> {e2}")


def ensure_collection(
    client: QdrantClient, coll: str, size: int = 768, distance: str = "Cosine"
) -> None:
    try:
        # Check if collection exists
        collections = client.get_collections()
        existing_names = [c.name for c in collections.collections]
        if coll in existing_names:
            print(f"[ok] collection {coll} (exists)")
            return

        # Create collection
        client.create_collection(
            collection_name=coll,
            vectors_config=VectorParams(size=size, distance=Distance.COSINE),
        )
        print(f"[ok] created collection {coll}")
    except Exception as e:
        raise SystemExit(f"[fail] create collection {coll} -> {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--qdrant", default=QDRANT)
    ap.add_argument("--chunks", default=CHUNKS)
    ap.add_argument("--images", default=IMAGES)
    ap.add_argument("--size", type=int, default=768)
    ap.add_argument("--distance", default="Cosine")
    args = ap.parse_args()

    print(f"[cfg] QDRANT={args.qdrant} CHUNKS={args.chunks} IMAGES={args.images}")

    # Connect to Qdrant
    try:
        client = QdrantClient(url=args.qdrant)
    except Exception as e:
        raise SystemExit(f"[fail] connect to Qdrant at {args.qdrant} -> {e}")

    # Collections (ensure exist)
    ensure_collection(client, args.chunks, size=args.size, distance=args.distance)
    ensure_collection(client, args.images, size=args.size, distance=args.distance)

    # Indexes for both
    for coll in (args.chunks, args.images):
        for f in FIELDS:
            put_index(client, coll, f)

    print("[ok] indexes ready")


if __name__ == "__main__":
    main()
