from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import logging
import sqlite3

from . import seed, settings
from .common import network_online, content_logging
from .db import set_setting, get_setting
from .routers import system, inference, devices, catalog, evals as evals_r, obs, reviews
from .token_gate import TokenGateMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        seed.run_seed()
    except sqlite3.OperationalError as exc:
        # A locked database at boot means the PREVIOUS instance is still
        # serving from this volume. Its catalog is at most one deploy old --
        # start and serve rather than fail the whole rollout over an upsert.
        logging.getLogger(__name__).warning("seed skipped: %s", exc)
    if get_setting("network_online") is None:
        set_setting("network_online", "1")
    yield


app = FastAPI(
    title="Sarvam Edge Lab",
    version=settings.APP_VERSION,
    description=(
        "Local-first on-device AI product demo for interview purposes. "
        "NOT Sarvam Edge production software. Simulated outputs are clearly labelled "
        "and are NOT Sarvam Edge benchmarks."),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TokenGateMiddleware)

for r in (system.router, inference.router, devices.router, catalog.router,
          evals_r.router, obs.router, reviews.router):
    app.include_router(r)
    # The built SPA calls /api/*. In dev, Vite's proxy rewrites that prefix away
    # (frontend/vite.config.ts), so the routes above are enough. In production
    # nothing rewrites it: /api/models fell through to spa_fallback, came back as
    # index.html with a 200, and the UI reported "Backend API unreachable at
    # /api" over an app that was running perfectly. Mount both spellings.
    app.include_router(r, prefix="/api", include_in_schema=False)


STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if not STATIC_DIR.exists():
    @app.get("/")
    def root():
        return {"app": "Sarvam Edge Lab", "docs": "/docs", "health": "/health"}
else:
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    API_SEGMENTS = {"inference", "devices", "models", "policies", "evals",
                    "telemetry", "analytics", "audit", "reviews", "system"}

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str, request: Request):
        # T9: API-shaped paths get a JSON 404; everything else gets the SPA
        first = full_path.split("/", 1)[0]
        wants_json = "application/json" in request.headers.get("accept", "")
        if wants_json or first in API_SEGMENTS:
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        candidate = STATIC_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")
