"""
AICSS Backend — FastAPI Application
"""
import sys
import os
import logging
from logging.handlers import RotatingFileHandler

# File-based logging so errors are always visible
_log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(_log_dir, exist_ok=True)
_log_file = os.path.join(_log_dir, "aicss.log")

_log = logging.getLogger("aicss")
_log.setLevel(logging.DEBUG)
_handler = RotatingFileHandler(_log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
if not any(isinstance(h, RotatingFileHandler) for h in _log.handlers):
    _log.addHandler(_handler)

# Put the backend root on sys.path so absolute imports (from app.xxx) work
# regardless of the working directory when uvicorn starts the process.
_backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

# Temp directory for large binary artifacts (depth maps, masks) served as static files
_TEMP_DIR = os.path.join(_backend_root, "temp")
os.makedirs(_TEMP_DIR, exist_ok=True)

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Absolute imports — work because backend root is now on sys.path
from app.config import settings, DEVICE
from app.models import model_manager
from app.endpoints import router as endpoints_router


# ─────────────────────────────────────────────────────────────────────────────
# Model loading state
# ─────────────────────────────────────────────────────────────────────────────
_models_loaded = False
_model_load_error: str | None = None


def _try_load_models() -> None:
    global _models_loaded, _model_load_error
    try:
        model_manager.load_all()
        _models_loaded = True
        _model_load_error = None
        print("[AICSS] All models loaded successfully.")
    except Exception as e:
        _models_loaded = False
        _model_load_error = str(e)
        print(f"[AICSS] WARNING: Model loading failed: {e}")
        print("[AICSS] Server will start but inference endpoints may fail.")


# ─────────────────────────────────────────────────────────────────────────────
# Lifespan — load models on startup
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    _try_load_models()
    yield
    print("[AICSS] Shutting down...")


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI App
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AICSS Backend",
    description="AI Cinematic Spatial System — Depth + Segmentation + Spatial Layers",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — restrict to known origins. Add your frontend URL here for production.
# For dev, allow localhost variants.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8001",
    ],
    allow_credentials=False,  # must be False when allow_origins is not ["*"]
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount endpoints router
app.include_router(endpoints_router, prefix="/api/aicss", tags=["AICSS"])

# Serve temp files (depth maps, masks) at /temp/
app.mount("/temp", StaticFiles(directory=_TEMP_DIR), name="temp")


# ─────────────────────────────────────────────────────────────────────────────
# Health check
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok" if _models_loaded else "degraded",
        "device": DEVICE,
        "models_loaded": _models_loaded,
        "model_load_error": _model_load_error,
    }


@app.get("/")
async def root():
    return {
        "service": "AICSS Backend",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Run directly
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
    )
