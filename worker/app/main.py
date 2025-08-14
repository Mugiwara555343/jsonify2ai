import os
from fastapi import FastAPI

app = FastAPI(title="jsonify2ai Worker", version="1.0.0")

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
