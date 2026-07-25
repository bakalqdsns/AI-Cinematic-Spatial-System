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
if not _log.handlers:
    _log.addHandler(_handler)

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
from app.services.local_llm import configure_llm
from app.services.image_generator import configure_image_generator
from app.endpoints import router as endpoints_router
from app.endpoints_projects import router as projects_router
from app.endpoints_sequence import router as sequence_router
from app.endpoints_shots import router as shots_router
from app.endpoints_script import router as script_router
from app.endpoints_mesh import router as mesh_router
from app.endpoints_llm import router as llm_router
from app.services.llama_server_manager import ensure_server_running


# ─────────────────────────────────────────────────────────────────────────────
# Lifespan — models load on demand when AICSS_LAZY_LOAD=true
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize local LLM and image generator clients with settings
    configure_llm(base_url=settings.llm_base_url, model=settings.llm_model)
    configure_image_generator(model_id=settings.image_model_id, dtype_name=settings.image_dtype)
    print(f"[AICSS] LLM client: {settings.llm_base_url} ({settings.llm_model})")
    print(f"[AICSS] Image generator: {settings.image_model_id} (dtype={settings.image_dtype})")
    print(f"[AICSS] Video provider: {settings.video_provider}")

    # Auto-start llama-server if not already running
    print("[AICSS] Checking llama-server status...")
    try:
        llm_started = await ensure_server_running()
        if llm_started:
            print("[AICSS] llama-server is running.")
        else:
            print("[AICSS] WARNING: llama-server not available. Use POST /api/aicss/llm/start to start it manually.")
        # Start the auto-unload background manager
        from app.services.llama_server_manager import start_auto_unload_manager
        start_auto_unload_manager()
    except Exception as e:
        print(f"[AICSS] WARNING: Failed to check llama-server: {e}")

    if settings.lazy_load:
        print("[AICSS] Lazy model loading enabled — models load on first use.")
    else:
        print("[AICSS] Loading all models on startup...")
        try:
            model_manager.load_all()
            print("[AICSS] All models loaded successfully.")
        except Exception as e:
            print(f"[AICSS] WARNING: Model loading failed: {e}")
            print("[AICSS] Server will start but inference endpoints may fail.")
    yield
    print("[AICSS] Shutting down — unloading all models...")
    model_manager.unload_all()
    from app.services.llama_server_manager import stop_auto_unload_manager, stop_server
    stop_auto_unload_manager()
    await stop_server()
    print("[AICSS] Shutdown complete.")


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
app.include_router(projects_router, prefix="/api/aicss", tags=["Projects"])
app.include_router(sequence_router, prefix="/api/aicss", tags=["v2 - Sequence"])
app.include_router(shots_router, prefix="/api/aicss", tags=["v2 - Shots"])
app.include_router(script_router, prefix="/api/aicss", tags=["v2 - Script & Motion"])
app.include_router(mesh_router, prefix="/api/aicss", tags=["v2 - 3D Mesh Export"])
app.include_router(llm_router, prefix="/api/aicss", tags=["LLM Server"])


# ─────────────────────────────────────────────────────────────────────────────
# Health check
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    from app.services.local_llm import get_llm_client
    llm_ok = False
    try:
        llm_ok = await get_llm_client().is_alive()
    except Exception:
        pass
    return {
        "status": "ok",
        "device": DEVICE,
        "models_loaded": model_manager.is_loaded(),  # 兼容前端期望的字段名
        "lazy_load": settings.lazy_load,
        "all_loaded": model_manager.is_loaded(),
        "models": model_manager.model_status(),
        "llm_server": settings.llm_base_url,
        "llm_alive": llm_ok,
        "image_model": settings.image_model_id,
        "video_provider": settings.video_provider,
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
