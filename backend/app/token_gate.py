import os

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse

from . import settings

OPEN_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}


class TokenGateMiddleware(BaseHTTPMiddleware):
    """Optional shared-secret gate for public deployments.

    Set DEMO_API_TOKEN to require X-Demo-Token (header or ?token= query param)
    on every path except OPEN_PATHS. Unset (local dev) => open, as before.
    """

    async def dispatch(self, request: Request, call_next):
        token = os.environ.get("DEMO_API_TOKEN", "").strip()
        if token:
            path = request.url.path.rstrip("/") or "/"
            if path not in OPEN_PATHS:
                supplied = request.headers.get("X-Demo-Token") or request.query_params.get("token")
                if supplied != token:
                    return JSONResponse({"detail": "invalid or missing demo token"},
                                        status_code=401)
        return await call_next(request)


def config():
    return settings
