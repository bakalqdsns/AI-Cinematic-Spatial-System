"""
LLM Server Control Endpoints.

Provides HTTP API for managing llama-server:
  POST /api/aicss/llm/start  — Start the server
  POST /api/aicss/llm/stop   — Stop the server
  GET  /api/aicss/llm/status — Get current status
  POST /api/aicss/llm/reload — Restart the server
"""

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.llama_server_manager import (
    start_server,
    stop_server,
    get_status,
    health_check,
    record_usage,
    start_auto_unload_manager,
)

_log = logging.getLogger("aicss")
router = APIRouter(prefix="/api/aicss/llm", tags=["LLM Server"])


# ── Response models ───────────────────────────────────────────────────────────

class LlmStatusResponse(BaseModel):
    running: bool
    port: int
    model: str | None
    model_found: bool


class LlmActionResponse(BaseModel):
    success: bool
    message: str
    already_running: bool = False


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status", response_model=LlmStatusResponse)
async def llm_status():
    """Get current llama-server status."""
    return await get_status()


@router.post("/start", response_model=LlmActionResponse)
async def llm_start():
    """
    Start llama-server.
    Uses batch script to run in system environment (bypasses venv CUDA issues).
    """
    result = await start_server()
    return LlmActionResponse(
        success=result["success"],
        message=result["message"],
        already_running=result.get("already_running", False),
    )


@router.post("/stop", response_model=LlmActionResponse)
async def llm_stop():
    """Stop llama-server gracefully."""
    result = await stop_server()
    return LlmActionResponse(
        success=result["success"],
        message=result["message"],
    )


@router.post("/reload", response_model=LlmActionResponse)
async def llm_reload():
    """Restart llama-server (stop then start)."""
    _log.info("[LLM] Reload requested")
    await stop_server()
    await start_server()
    return LlmActionResponse(
        success=True,
        message="Server reloaded",
        already_running=False,
    )


@router.post("/keep-alive")
async def llm_keep_alive():
    """
    Reset the auto-unload idle timer.
    Call this periodically from the frontend to prevent server from shutting down.
    """
    record_usage()
    return {"ok": True, "message": "Idle timer reset"}
