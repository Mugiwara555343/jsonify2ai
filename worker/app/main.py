import os
from fastapi import FastAPI
from .config import settings
from .routers import process

app = FastAPI(title="jsonify2ai Worker", version="1.0.0")

# Log configuration on startup
@app.on_event("startup")
async def startup_event():
    print(f"Starting worker with:")
    print(f"  Model: {settings.EMBEDDINGS_MODEL}")
    print(f"  Collection: {settings.QDRANT_COLLECTION}")
    print(f"  Chunk size: {settings.CHUNK_SIZE}")
    print(f"  Chunk overlap: {settings.CHUNK_OVERLAP}")

# Include routers
app.include_router(process.router, prefix="/process", tags=["processing"])

@app.get("/health")
async def health():
    return {"ok": True}

@app.get("/")
async def root():
    return {"message": "jsonify2ai Worker Service"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT_WORKER", "8090"))
    uvicorn.run(app, host="0.0.0.0", port=port)
