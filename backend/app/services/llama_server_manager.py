"""
LlamaServer Manager - Start/stop/status for llama-server in AICSS backend.

Architecture:
- llama-server runs in SYSTEM ENVIRONMENT (not venv) due to CUDA DLL dependencies
- Python manages it via batch scripts
- Auto mode: server starts on first use, unloads after idle timeout
- Manual mode: explicit /start and /stop calls

Usage:
  1. Manual: POST /api/aicss/llm/start  → starts server
  2. Manual: POST /api/aicss/llm/stop   → stops server
  3. Auto mode in lifespan: starts on startup if not running
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import threading
from pathlib import Path

import httpx

# Use a child of the project-wide "aicss" logger so llama-server output ends up
# in backend/logs/aicss.log alongside the rest of the Python backend logs.
logger = logging.getLogger("aicss.llama_server")

# ── Paths ─────────────────────────────────────────────────────────────────────

BACKEND_DIR = Path(__file__).parent.parent.parent.resolve()
LLMSERVER_DIR = BACKEND_DIR / "llmserver"
SERVER_EXE = LLMSERVER_DIR / "llama-server.exe"
START_SCRIPT = LLMSERVER_DIR / "start-llama-server.bat"
STOP_SCRIPT = LLMSERVER_DIR / "stop-llama-server.bat"

# Model cache
MODELS_DIR = LLMSERVER_DIR / "models"
MODEL_CACHE_DIR = MODELS_DIR / "models"

DEFAULT_PORT = 8080

# Auto-unload after this many seconds of inactivity (None = never auto-unload)
# IMPORTANT: Keep high enough to avoid killing a long-running LLM call.
#   - Qwen2.5-7B Q4_K_M on CPU: up to ~5 min per request
#   - Qwen2.5-7B Q4_K_M on GPU: ~30-120s per request
AUTO_UNLOAD_TIMEOUT: float | None = 1800  # 30 minutes


# ── Model detection ────────────────────────────────────────────────────────────

MODEL_CONFIGS = [
    # Qwen2.5-7B Q4_K_M — ~4.6GB, best performance/ram ratio
    {
        "name": "Qwen2.5-7B-Q4_K_M",
        "repo_id": "Qwen/Qwen2.5-7B-Instruct-GGUF",
        "split_files": [
            "qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf",
            "qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf",
        ],
    },
    # Qwen2.5-7B FP16 — 14GB
    {
        "name": "Qwen2.5-7B-FP16",
        "repo_id": "Qwen/Qwen2.5-7B-Instruct-GGUF",
        "split_files": [
            "qwen2.5-7b-instruct-fp16-00001-of-00004.gguf",
            "qwen2.5-7b-instruct-fp16-00002-of-00004.gguf",
            "qwen2.5-7b-instruct-fp16-00003-of-00004.gguf",
            "qwen2.5-7b-instruct-fp16-00004-of-00004.gguf",
        ],
    },
]


def find_available_model() -> dict | None:
    """Find the first available GGUF model in the cache."""
    for config in MODEL_CONFIGS:
        repo_dir = MODEL_CACHE_DIR / config["repo_id"].replace("/", "--") / "snapshots" / "master"
        all_exist = all((repo_dir / f).exists() for f in config["split_files"])
        if all_exist:
            return {
                "name": config["name"],
                "path": str(repo_dir / config["split_files"][0]),
                "repo_id": config["repo_id"],
            }
    return None


# ── Core operations ───────────────────────────────────────────────────────────

def _forward_llama_output(pipe) -> None:
    """Forward llama-server stdout/stderr into the `aicss.llama_server` logger.

    Runs in a daemon thread so the asyncio event loop is never blocked by
    llama-server's output. Each line is prefixed with `[llama-server]` so
    entries are easy to grep out of aicss.log.
    """
    try:
        with pipe:
            for raw_line in iter(pipe.readline, ""):
                line = raw_line.rstrip()
                if not line:
                    continue
                # Promote known error/failure strings to WARNING/ERROR so the
                # RotatingFileHandler doesn't bury them under INFO.
                lower = line.lower()
                if "error" in lower or "fail" in lower or "abort" in lower:
                    logger.warning("[llama-server] %s", line)
                else:
                    logger.info("[llama-server] %s", line)
    except Exception as exc:
        logger.warning("[llama-server] Log forwarding stopped: %s", exc)


async def health_check(port: int = DEFAULT_PORT, timeout: float = 2.0) -> bool:
    """Check if llama-server is responding on the port (fast timeout)."""
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            resp = await client.get(f"http://localhost:{port}/health")
            return resp.status_code == 200
    except Exception:
        return False


async def start_server() -> dict:
    """
    Start llama-server via batch script.
    Returns {"success": bool, "message": str, "already_running": bool}
    """
    # Already running?
    if await health_check():
        return {
            "success": True,
            "message": "Server already running",
            "already_running": True,
        }

    # Check batch script exists
    if not START_SCRIPT.exists():
        return {
            "success": False,
            "message": f"Start script not found: {START_SCRIPT}",
            "already_running": False,
        }

    # Check model exists
    model = find_available_model()
    if not model:
        return {
            "success": False,
            "message": f"No GGUF model found. Expected at: {MODEL_CACHE_DIR}",
            "already_running": False,
        }

    # Start llama-server.exe directly via Popen (DETACHED, returns instantly)
    # This bypasses batch script overhead and runs in system environment
    import sys
    if sys.platform == "win32":
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
        creationflags = 0x00000008 | 0x00000200 | 0x08000000
    else:
        creationflags = 0

    # ── Force CUDA device 0 if multiple GPUs present (avoid integrated GPU) ──
    import os
    env = os.environ.copy()
    env.setdefault("CUDA_VISIBLE_DEVICES", "0")

    # ── Align the --alias with the client-side model name used in
    # local_llm.py (DEFAULT_MODEL) so the /v1/chat completions call
    # finds the right model on the server side.
    cmd = [
        str(SERVER_EXE),
        "-m", model["path"],
        "-c", "8192",
        "-ngl", "99",
        "--host", "0.0.0.0",
        "--port", str(DEFAULT_PORT),
        "--alias", "qwen2.5-7b-q4_k_m",
    ]
    logger.info("[LlamaServer] Launching: %s", " ".join(cmd))

    try:
        # Pipe stdout/stderr back into the Python logger. A daemon thread reads
        # them line-by-line and routes every line through the `aicss.llama_server`
        # logger so it interleaves with the rest of the backend output in
        # backend/logs/aicss.log. We intentionally do NOT have llama-server
        # write to aicss.log directly: the RotatingFileHandler rotates the file
        # underneath us, which would break a long-lived file handle.
        # stderr is merged into stdout — llama.cpp writes progress/diagnostics
        # (CUDA init, model load, errors) to stderr, so dropping it would lose
        # most of the useful output.
        proc = subprocess.Popen(
            cmd,
            cwd=str(LLMSERVER_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            creationflags=creationflags,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        if proc.stdout is not None:
            threading.Thread(
                target=_forward_llama_output,
                args=(proc.stdout,),
                daemon=True,
                name="llama-server-log-forwarder",
            ).start()
        logger.info(
            "[LlamaServer] Launched with PID %d; llama-server output is forwarded to aicss.log",
            proc.pid,
        )
    except FileNotFoundError:
        return {"success": False, "message": f"llama-server.exe not found at {SERVER_EXE}", "already_running": False}
    except Exception as e:
        return {"success": False, "message": f"Failed to launch: {e}", "already_running": False}

    # Wait for health check (model loading takes ~5-15s)
    for attempt in range(20):  # up to 30 seconds
        await asyncio.sleep(1.5)
        if await health_check():
            return {
                "success": True,
                "message": f"Server started with model: {model['name']} (PID {proc.pid})",
                "model": model["name"],
                "pid": proc.pid,
                "already_running": False,
            }

    return {
        "success": False,
        "message": f"Server launched (PID {proc.pid}) but health check timed out after 30s",
        "already_running": False,
    }


async def stop_server() -> dict:
    """Stop llama-server via batch script."""
    # Already stopped?
    if not await health_check():
        return {"success": True, "message": "Server already stopped"}

    if not STOP_SCRIPT.exists():
        return {"success": False, "message": f"Stop script not found: {STOP_SCRIPT}"}

    logger.info("[LlamaServer] Stopping via batch script...")
    try:
        result = subprocess.run(
            [str(STOP_SCRIPT)],
            cwd=str(LLMSERVER_DIR),
            capture_output=True,
            text=True,
            timeout=15,
        )
        logger.info("[LlamaServer] Batch script output: %s", result.stdout.strip())
    except Exception as e:
        return {"success": False, "message": f"Failed to run stop script: {e}"}

    # Verify stopped
    await asyncio.sleep(2)
    if await health_check():
        return {"success": False, "message": "Server still running after stop"}

    return {"success": True, "message": "Server stopped"}


async def get_status() -> dict:
    """Get current server status."""
    running = await health_check()
    model = find_available_model()
    return {
        "running": running,
        "port": DEFAULT_PORT,
        "model": model["name"] if model else None,
        "model_found": model is not None,
        "start_script": str(START_SCRIPT),
        "stop_script": str(STOP_SCRIPT),
    }


# ── Auto-unload manager ───────────────────────────────────────────────────────

_auto_unload_task: asyncio.Task | None = None
_last_used_time: float = 0


async def _auto_unload_loop():
    """Background task: unloads server after idle timeout."""
    global _last_used_time
    while True:
        await asyncio.sleep(30)
        if AUTO_UNLOAD_TIMEOUT is None:
            continue
        import time
        if _last_used_time > 0 and (time.time() - _last_used_time) > AUTO_UNLOAD_TIMEOUT:
            if await health_check():
                logger.info("[LlamaServer] Idle timeout reached, stopping server...")
                await stop_server()
                _last_used_time = 0


def record_usage():
    """Call this whenever the LLM is used to reset idle timer."""
    global _last_used_time
    import time
    _last_used_time = time.time()


def start_auto_unload_manager():
    """Start the background auto-unload task."""
    global _auto_unload_task
    if _auto_unload_task is None or _auto_unload_task.done():
        _auto_unload_task = asyncio.create_task(_auto_unload_loop())
        logger.info("[LlamaServer] Auto-unload manager started (timeout=%s)", AUTO_UNLOAD_TIMEOUT)


def stop_auto_unload_manager():
    """Stop the background auto-unload task."""
    global _auto_unload_task
    if _auto_unload_task:
        _auto_unload_task.cancel()
        _auto_unload_task = None


# ── ensure_server_running (legacy compatibility) ──────────────────────────────

async def ensure_server_running() -> bool:
    """
    Ensure llama-server is running (for lifespan startup).
    Only starts if not already running.
    """
    if await health_check():
        logger.info("[LlamaServer] Already running on port %d", DEFAULT_PORT)
        return True

    result = await start_server()
    return result["success"]
