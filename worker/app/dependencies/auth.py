# worker/app/dependencies/auth.py
from fastapi import HTTPException, Request
from fastapi.security import HTTPBearer
from ..config import settings

security = HTTPBearer(auto_error=False)


def require_auth(request: Request) -> bool:
    """
    Dependency that requires authentication for protected routes.
    If WORKER_AUTH_TOKEN is not set, authentication is disabled.
    """
    # Debug logging
    print(f"[auth_debug] WORKER_AUTH_TOKEN='{settings.WORKER_AUTH_TOKEN}'")
    print(f"[auth_debug] Token length: {len(settings.WORKER_AUTH_TOKEN)}")
    print(f"[auth_debug] Token stripped: '{settings.WORKER_AUTH_TOKEN.strip()}'")

    # If no auth token is configured, skip authentication entirely
    if not settings.WORKER_AUTH_TOKEN or settings.WORKER_AUTH_TOKEN.strip() == "":
        print("[auth_debug] No auth token configured, skipping authentication")
        return True

    # Get the Authorization header manually
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(
            status_code=401, detail={"ok": False, "error": "unauthorized"}
        )

    # Check if it's a Bearer token
    parts = auth_header.split(" ", 1)
    if len(parts) != 2 or parts[0] != "Bearer":
        raise HTTPException(
            status_code=401, detail={"ok": False, "error": "unauthorized"}
        )

    # Verify the token
    if parts[1] != settings.WORKER_AUTH_TOKEN:
        raise HTTPException(
            status_code=401, detail={"ok": False, "error": "unauthorized"}
        )

    return True
