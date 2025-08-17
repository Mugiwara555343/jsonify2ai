import os
from fastapi import FastAPI
from .config import settings
from .routers import process

app = FastAPI(title="jsonify2ai Worker", version="1.0.0")

# Log configuration on startup
@app.on_event("startup")
async def startup_event():
    print(f"Worker config -> model={settings.EMBEDDINGS_MODEL} dim={settings.EMBEDDING_DIM} dev_mode={os.getenv('EMBED_DEV_MODE', '0')} qdrant={settings.QDRANT_URL} ollama={settings.OLLAMA_URL} collection={settings.QDRANT_COLLECTION}")

# Include routers
app.include_router(process.router, prefix="/process", tags=["processing"])

@app.get("/health")
async def health():
    return {"ok": True}

@app.get("/debug/config")
async def debug_config():
    """Debug endpoint to show configuration (gated by DEBUG_CONFIG=1)"""
    if settings.DEBUG_CONFIG != "1":
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Not found")
    
    # Mask any potential secrets in URLs
    def mask_url(url: str) -> str:
        if not url:
            return url
        # Simple masking - replace password parts if they exist
        if "://" in url and "@" in url:
            # URL has auth, mask the password part
            parts = url.split("@")
            if len(parts) == 2:
                auth_part = parts[0]
                if ":" in auth_part:
                    scheme_host = auth_part.split("://")[0] + "://"
                    username = auth_part.split("://")[1].split(":")[0]
                    return f"{scheme_host}{username}:***@{parts[1]}"
        return url
    
    return {
        "model": settings.EMBEDDINGS_MODEL,
        "dim": settings.EMBEDDING_DIM,
        "dev_mode": os.getenv("EMBED_DEV_MODE", "0"),
        "qdrant_url": mask_url(settings.QDRANT_URL),
        "ollama_url": mask_url(settings.OLLAMA_URL),
        "collection": settings.QDRANT_COLLECTION,
        "chunk_size": settings.CHUNK_SIZE,
        "chunk_overlap": settings.CHUNK_OVERLAP,
        "debug_enabled": settings.DEBUG_CONFIG == "1"
    }

@app.get("/")
async def root():
    return {"message": "jsonify2ai Worker Service"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT_WORKER", "8090"))
    uvicorn.run(app, host="0.0.0.0", port=port)
