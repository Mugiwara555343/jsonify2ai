from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import os
from worker.app.routers import health
from worker.app.routers import status as status_router
from worker.app.routers import search as search_router
from worker.app.routers import upload as upload_router
from worker.app.routers import ask as ask_router
from worker.app.routers import process as process_router
from worker.app.routers import export as export_router
from worker.app.routers import documents as documents_router
from worker.app.config import settings as C
from worker.app.qdrant_init import ensure_collections

app = FastAPI(title="jsonify2ai-worker")

# CORS origins from environment variable or default

cors_origins_env = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,http://localhost:3000,http://127.0.0.1:3000",
)
origins = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all routers
app.include_router(health.router)
app.include_router(status_router.router)
app.include_router(search_router.router)
app.include_router(upload_router.router)
app.include_router(ask_router.router)
app.include_router(process_router.router)
app.include_router(export_router.router)
app.include_router(documents_router.router)


@app.on_event("startup")
async def _startup_log():
    logging.info(
        f"[worker] QDRANT_URL={C.QDRANT_URL}  OLLAMA_URL={getattr(C,'OLLAMA_URL','')}"
    )
    # idempotent: create collections if missing (skip if no Qdrant URL)
    try:
        if getattr(C, "QDRANT_URL", ""):
            await ensure_collections()
        else:
            logging.warning(
                "[worker] QDRANT_URL not set; skipping ensure_collections()"
            )
    except Exception as e:
        logging.warning(f"[worker] ensure_collections skipped due to error: {e}")
    logging.info(
        "[worker] Routes: /health /status /search /upload /ask /process /export /documents"
    )


@app.get("/")
async def root():
    return {"message": "jsonify2ai Worker Service"}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT_WORKER", "8090"))
    uvicorn.run(app, host="0.0.0.0", port=port)
