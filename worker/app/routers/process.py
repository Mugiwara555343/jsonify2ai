import uuid
import os
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from ..services.chunker import chunk_text
from ..services.embed_ollama import embed_texts
from ..services.qdrant_client import get_qdrant_client, ensure_collection, upsert_points
from ..config import settings

router = APIRouter()

class ProcessTextRequest(BaseModel):
    document_id: str = Field(..., description="Unique document identifier")
    text: Optional[str] = Field(None, description="Raw text content")
    path: Optional[str] = Field(None, description="Path to text file")

class ProcessTextResponse(BaseModel):
    ok: bool
    document_id: str
    chunks: int
    embedded: int
    upserted: int
    collection: str
    error: Optional[str] = None

@router.post("/text", response_model=ProcessTextResponse)
async def process_text(request: ProcessTextRequest):
    """
    Process text: chunk, embed, and store in Qdrant.
    
    Accepts either raw text or file path, processes into chunks,
    generates embeddings via Ollama, and stores in vector database.
    """
    try:
        # Determine text content
        text_content = request.text
        
        if request.path and not text_content:
            # Read from file path
            file_path = Path(request.path)
            
            if not file_path.exists():
                raise HTTPException(status_code=400, detail="File not found")
            
            if file_path.stat().st_size > 5 * 1024 * 1024:  # 5MB limit
                raise HTTPException(status_code=400, detail="File too large (>5MB)")
            
            try:
                text_content = file_path.read_text(encoding='utf-8')
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")
        
        if not text_content or not text_content.strip():
            raise HTTPException(status_code=400, detail="No text content provided")
        
        # Chunk the text
        chunks = chunk_text(
            text_content, 
            settings.CHUNK_SIZE, 
            settings.CHUNK_OVERLAP
        )
        
        if not chunks:
            raise HTTPException(status_code=400, detail="No chunks generated")
        
        # Generate embeddings
        embeddings = embed_texts(chunks, settings.EMBEDDINGS_MODEL, settings.OLLAMA_URL)
        
        if len(embeddings) != len(chunks):
            raise HTTPException(status_code=500, detail="Embedding count mismatch")
        
        # Prepare Qdrant data
        qdrant_client = get_qdrant_client()
        collection_name = settings.QDRANT_COLLECTION
        
        # Ensure collection exists with correct dimensions
        ensure_collection(qdrant_client, collection_name, settings.EMBEDDING_DIM)
        
        # Prepare payloads and IDs
        payloads = []
        ids = []
        
        for idx, chunk in enumerate(chunks):
            payloads.append({
                "document_id": request.document_id,
                "idx": idx,
                "text": chunk
            })
            ids.append(f"{request.document_id}:{idx}")
        
        # Upsert to Qdrant
        upsert_points(qdrant_client, collection_name, embeddings, payloads, ids)
        
        return ProcessTextResponse(
            ok=True,
            document_id=request.document_id,
            chunks=len(chunks),
            embedded=len(embeddings),
            upserted=len(ids),
            collection=collection_name
        )
        
    except HTTPException:
        raise
    except Exception as e:
        # Return 502 for external service errors
        return ProcessTextResponse(
            ok=False,
            document_id=request.document_id,
            chunks=0,
            embedded=0,
            upserted=0,
            collection=settings.QDRANT_COLLECTION,
            error=str(e)
        )
