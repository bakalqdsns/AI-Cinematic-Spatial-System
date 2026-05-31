"""
AICSS Backend — FastAPI Application
"""
import sys
import os

# Put the backend root on sys.path so absolute imports (from app.xxx) work
# regardless of the working directory when uvicorn starts the process.
_backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Absolute imports — work because backend root is now on sys.path
from app.config import settings, DEVICE
from app.models import model_manager
from app.endpoints import router as endpoints_router


# ─────────────────────────────────────────────────────────────────────────────
# Lifespan — load models on startup
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[AICSS] Loading models on startup...")
    try:
        model_manager.load_all()
        print("[AICSS] All models loaded successfully.")
    except Exception as e:
        print(f"[AICSS] WARNING: Model loading failed: {e}")
        print("[AICSS] Server will start but inference endpoints may fail.")
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

# CORS — allow frontend on any port during dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount endpoints router
app.include_router(endpoints_router, prefix="/api/aicss", tags=["AICSS"])


# ─────────────────────────────────────────────────────────────────────────────
# Health check
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "device": DEVICE,
        "models_loaded": model_manager.is_loaded(),
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
