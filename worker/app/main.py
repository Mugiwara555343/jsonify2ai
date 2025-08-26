from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from worker.app.routers import health
from worker.app.routers import status as status_router
from worker.app.routers import search as search_router
from worker.app.routers import upload as upload_router
from worker.app.routers import ask as ask_router
from worker.app.routers import process as process_router
from worker.app.config import settings as C
from worker.app.qdrant_init import ensure_collections, collections_status
import logging

from .config import settings
from .routers import process
from .routers import status as status_router
from .routers import search as search_router
from .routers import upload as upload_router


app = FastAPI(title="jsonify2ai-worker")
# CORS for local dev (Vite + any 3000-series localhost)
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(status_router.router)
app.include_router(search_router.router)
app.include_router(upload_router.router)
app.include_router(ask_router.router)
app.include_router(process_router.router)


@app.on_event("startup")
async def _startup_log():
    logging.info(f"[worker] QDRANT_URL={C.QDRANT_URL}  OLLAMA_URL={getattr(C,'OLLAMA_URL','')}")
    # idempotent: create collections if missing (skip if no Qdrant URL)
    try:
        if getattr(C, "QDRANT_URL", ""):
            await ensure_collections()
        else:
            logging.warning("[worker] QDRANT_URL not set; skipping ensure_collections()")
    except Exception as e:
        logging.warning(f"[worker] ensure_collections skipped due to error: {e}")
    logging.info("[worker] Routes: /health /status /search /upload /ask /process")

# Add CORS middleware
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Log configuration on startup
@app.on_event("startup")
async def startup_event():
    print(f"Worker config -> model={settings.EMBEDDINGS_MODEL} dim={settings.EMBEDDING_DIM} dev_mode={os.getenv('EMBED_DEV_MODE', '0')} qdrant={settings.QDRANT_URL} ollama={settings.OLLAMA_URL} collection={settings.QDRANT_COLLECTION}")

# Include routers
app.include_router(process.router, prefix="/process", tags=["processing"])
app.include_router(status_router.router)
app.include_router(search_router.router)
app.include_router(upload_router.router)

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
