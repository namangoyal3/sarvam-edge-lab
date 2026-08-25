from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import seed, settings
from .common import network_online, content_logging
from .db import set_setting, get_setting
from .routers import system, inference, devices, catalog, evals as evals_r, obs, reviews


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed.run_seed()
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
    allow_origins=settings.CORS_ORIGINS + ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (system.router, inference.router, devices.router, catalog.router,
          evals_r.router, obs.router, reviews.router):
    app.include_router(r)


@app.get("/")
def root():
    return {"app": "Sarvam Edge Lab", "docs": "/docs", "health": "/health"}


# ---- production single-container mode: serve the built SPA after all API routes ----
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        candidate = STATIC_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")
