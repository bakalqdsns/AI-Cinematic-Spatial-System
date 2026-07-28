"""
Shared GPU concurrency limiter.

Multiple background workers (character three-view, scene keyframes, …) all
compete for the same GPU. If each owns its own semaphore, the *combined*
in-flight SDXL/Z-Image requests can exceed VRAM capacity and trigger OOM.

This module exposes a single process-wide :class:`asyncio.Semaphore` that
every GPU-bound worker must acquire before issuing inference. The default
cap of 2 is calibrated for an RTX 4060 Ti (16 GB) running SDXL/Z-Image-Turbo
in bfloat16.
"""
from __future__ import annotations

import asyncio
from typing import Optional


# Hard cap on concurrently-running GPU inference jobs (txt2img + img2img +
# inpaint count the same). 2 keeps SDXL/Z-Image-Turbo inside the 16 GB
# consumer-tier VRAM budget while still letting one character + one scene
# (or two scenes) progress in parallel.
_MAX_CONCURRENT_GPU_JOBS = 2

_GPU_SEM: Optional[asyncio.Semaphore] = None


def get_gpu_sem() -> asyncio.Semaphore:
    """Return the shared process-wide GPU semaphore (lazy init)."""
    global _GPU_SEM
    if _GPU_SEM is None:
        _GPU_SEM = asyncio.Semaphore(_MAX_CONCURRENT_GPU_JOBS)
    return _GPU_SEM


def max_concurrent_gpu_jobs() -> int:
    """Return the configured cap (mostly for tests / diagnostics)."""
    return _MAX_CONCURRENT_GPU_JOBS
