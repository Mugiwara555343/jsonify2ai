# worker/app/dependencies/auth.py
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from worker.app.config import settings

security = HTTPBearer(auto_error=False)


async def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> bool:
    """
    Verify bearer token authentication.
    If WORKER_AUTH_TOKEN is not set, authentication is disabled.
    """
    # If no auth token is configured, skip authentication
    if not settings.WORKER_AUTH_TOKEN:
        return True

    # If no credentials provided, deny access
    if not credentials:
        raise HTTPException(
            status_code=401, detail={"ok": False, "error": "unauthorized"}
        )

    # Verify the token
    if credentials.credentials != settings.WORKER_AUTH_TOKEN:
        raise HTTPException(
            status_code=401, detail={"ok": False, "error": "unauthorized"}
        )

    return True


# Dependency that can be used in route handlers
def require_auth(credentials: HTTPAuthorizationCredentials = Depends(security)) -> bool:
    """
    Dependency that requires authentication for protected routes.
    """
    return verify_token(credentials)
