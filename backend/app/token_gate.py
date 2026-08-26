import os

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse

from . import settings

OPEN_PATHS = {"/health", "/docs", "/openapi.json", "/redoc", "/"}

# The SPA shell has to load before it can present a token.
#
# A share link is `https://app/?token=xyz`, and the code that reads that query
# param and stores it lives INSIDE the JS bundle. But a `<script
# src="/assets/index-*.js">` tag carries no query string, so gating the bundle
# 401s it, the module never runs, and the share link renders a blank page --
# the token gate locking out the one thing that reads the token. It shipped
# that way and looked like a dead deployment.
#
# The shell is public code with no data in it (the repo is public). Every data
# route stays gated, so an opened shell with no token renders an empty app,
# never someone else's fleet.
OPEN_PREFIXES = ("/assets/",)


class TokenGateMiddleware(BaseHTTPMiddleware):
    """Optional shared-secret gate for public deployments.

    Set DEMO_API_TOKEN to require X-Demo-Token (header or ?token= query param)
    on every path except OPEN_PATHS and OPEN_PREFIXES -- the health/docs routes
    and the static SPA shell. Unset (local dev) => open, as before.
    """

    async def dispatch(self, request: Request, call_next):
        token = os.environ.get("DEMO_API_TOKEN", "").strip()
        if token:
            path = request.url.path.rstrip("/") or "/"
            # Every route is mounted twice, at / and at /api (see main.py), so
            # the open list has to match both spellings.
            bare = path[4:] or "/" if path.startswith("/api") else path
            if bare not in OPEN_PATHS and not path.startswith(OPEN_PREFIXES):
                supplied = request.headers.get("X-Demo-Token") or request.query_params.get("token")
                if supplied != token:
                    return JSONResponse({"detail": "invalid or missing demo token"},
                                        status_code=401)
        return await call_next(request)


def config():
    return settings
