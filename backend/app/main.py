"""
AICSS Backend — FastAPI Application
"""
import faulthandler
import sys
import os
import logging
from logging.handlers import RotatingFileHandler

# Enable Python's faulthandler at process start so that native crashes
# (CUDA OOM kill, segfault inside a C extension, …) leave a useful
# traceback in stderr instead of silently killing the process.  This
# is especially important for Z-Image-Turbo / SDXL where
# ``torch.cuda.OutOfMemoryError`` is raised from native code and would
# otherwise surface as a generic "the backend timed out".
try:
    faulthandler.enable()
    # Register SIGUSR1 handler so on-call engineers can dump a Python
    # traceback from a running process without restarting it.  Windows
    # has no SIGUSR1 — skip silently there.
    try:
        import signal as _signal

        faulthandler.register(_signal.SIGUSR1)
    except (AttributeError, ValueError):
        pass
    print("[AICSS] faulthandler enabled — native crashes will dump traceback")
except Exception as _fe:
    print(f"[AICSS] WARNING: faulthandler not enabled: {_fe}")

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
from app.services.image_generator import configure_image_generator, warmup_image_generator
from app.services.dashscope_client import configure_dashscope_client
from app.endpoints import router as endpoints_router
from app.endpoints_projects import router as projects_router
from app.endpoints_sequence import router as sequence_router
from app.endpoints_shots import router as shots_router
from app.endpoints_script import router as script_router
from app.endpoints_mesh import router as mesh_router
from app.endpoints_llm import router as llm_router
from app.endpoints_settings import router as settings_router
from app.endpoints_models import router as models_router
from app.services.llama_server_manager import ensure_server_running


# ─────────────────────────────────────────────────────────────────────────────
# Lifespan — models load on demand when AICSS_LAZY_LOAD=true
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DashScope client for cloud mode
    configure_dashscope_client(
        llm_model=settings.dashscope_llm_model,
        vlm_model=settings.dashscope_vlm_model,
        image_model=settings.dashscope_image_model,
    )
    # Initialize local LLM and image generator clients with settings
    configure_llm(base_url=settings.llm_base_url, model=settings.llm_model, timeout=settings.llm_timeout)
    # Route LLM calls through DashScope when in cloud mode
    from app.services.local_llm import set_use_cloud
    set_use_cloud(settings.model_mode == "cloud")
    configure_image_generator(model_id=settings.image_model_id, dtype_name=settings.image_dtype)
    print(f"[AICSS] Model mode: {settings.model_mode}")
    print(f"[AICSS] LLM client: {settings.llm_base_url} ({settings.llm_model})")
    print(f"[AICSS] Image generator: {settings.image_model_id} (dtype={settings.image_dtype})")
    print(f"[AICSS] Video provider: {settings.video_provider}")
    print(f"[AICSS] HF download timeout: {os.environ.get('HF_HUB_DOWNLOAD_TIMEOUT', '10')}s")

    # Snapshot baseline GPU memory so any future discrepancy is obvious
    # in the log (e.g. "vram_before_warmup=14.82/16.00GB" makes it
    # trivial to see whether the previous server crashed without
    # releasing the Z-Image pipeline).
    try:
        import torch as _torch
        if _torch.cuda.is_available():
            _free, _total = _torch.cuda.mem_get_info(0)
            print(
                f"[AICSS] GPU baseline: {_torch.cuda.get_device_name(0)} "
                f"vram={_free / 1024**3:.2f}/{_total / 1024**3:.2f}GB "
                f"free={_free / 1024**3:.2f}GB"
            )
        else:
            print("[AICSS] GPU baseline: CUDA not available")
    except Exception as _e:
        print(f"[AICSS] GPU baseline check failed: {_e}")

    # ── llama-server / auto-unload manager (local mode only) ─────────────────
    if settings.model_mode == "local":
        print("[AICSS] Model mode: local — checking llama-server...")
        try:
            llm_started = await ensure_server_running()
            if llm_started:
                print("[AICSS] llama-server is running.")
            else:
                print("[AICSS] WARNING: llama-server not available.")
            # Start the auto-unload background manager
            from app.services.llama_server_manager import start_auto_unload_manager
            start_auto_unload_manager()
        except Exception as e:
            print(f"[AICSS] WARNING: Failed to check llama-server: {e}")
    else:
        print("[AICSS] Model mode: cloud — skipping llama-server startup.")

    # ── Startup model pre-flight (disabled — managed via Settings UI) ───────────
    # Previously this unconditionally called model_manager.ensure_all_downloaded()
    # on every startup, which blocked boot and attempted downloads even in cloud mode.
    # Model downloading is now handled exclusively through the Settings UI
    # via POST /api/aicss/models/download/{name} → /api/aicss/models/status.

    if settings.lazy_load:
        print("[AICSS] Lazy model loading enabled — models load on first use.")
    else:
        print("[AICSS] Loading all models on startup (lazy_load=False)...")
        try:
            model_manager.load_all()
            warmup_image_generator(settings.image_model_id, settings.image_dtype)
            print("[AICSS] All models loaded successfully.")
        except Exception as e:
            import traceback as _tb
            print(f"[AICSS] WARNING: Model loading failed: {e}")
            _tb.print_exc()
            print("[AICSS] Server will start but inference endpoints may fail.")
    yield
    print("[AICSS] Shutting down — unloading all models...")
    model_manager.unload_all()
    if settings.model_mode == "local":
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
app.include_router(llm_router, tags=["LLM Server"])
app.include_router(settings_router, tags=["Settings"])
app.include_router(models_router, tags=["Models"])


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
        "model_mode": settings.model_mode,
        "models_loaded": model_manager.is_loaded(),  # 兼容前端期望的字段名
        "lazy_load": settings.lazy_load,
        "all_loaded": model_manager.is_loaded(),
        "models": model_manager.model_status(),
        "llm_server": settings.llm_base_url,
        "llm_alive": llm_ok,
        "image_model": settings.image_model_id,
        "video_provider": settings.video_provider,
    }


@app.get("/health/models")
async def health_models():
    """
    Detailed per-model availability check.

    Returns whether each model file/weight is present on disk so the frontend
    can warn the user (and the dev can diagnose 5xx errors) before triggering
    expensive inference. Lazy-loaded models also report whether they are
    currently resident in GPU memory.

    The response shape is stable — frontend code can rely on these keys:
      - `models`     : per-model {available, path, ...} details
      - `missing`    : list of {model, path, download_hint} for unavailable models
      - `all_ready`  : True iff every required model is available
      - `device`     : cuda / cpu
      - `lazy_load`  : whether models are loaded on first use
    """
    try:
        status = model_manager.check_models_status()
        missing = model_manager.get_missing_models_info()
        return {
            "all_ready": len(missing) == 0,
            "device": DEVICE,
            "model_mode": settings.model_mode,
            "lazy_load": settings.lazy_load,
            "models": status,
            "missing": missing,
        }
    except Exception as e:
        _log.exception("health_models failed")
        raise HTTPException(
            status_code=500,
            detail=f"health_models failed: {type(e).__name__}: {e}"[:500],
        )


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
