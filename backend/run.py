#!/usr/bin/env python3
"""
Quick start script for AICSS backend.

Usage:
    python run.py          # auto-detects and uses .venv
    python run.py --cpu   # force CPU mode
"""
import os
import sys
import subprocess
import argparse

# ─── Auto-detect venv Python ───────────────────────────────────
_backend_dir = os.path.dirname(os.path.abspath(__file__))
_venv_python = os.path.join(_backend_dir, ".venv", "Scripts", "python.exe")

# Fallback paths for different OS shells
if not os.path.exists(_venv_python):
    _venv_python = os.path.join(_backend_dir, ".venv", "bin", "python")

_current_python = os.path.abspath(sys.executable)
_is_venv = ".venv" in _current_python

def is_venv_valid():
    return os.path.exists(_venv_python)

# ─── Parse args before re-launch ────────────────────────────────
parser = argparse.ArgumentParser(description="AICSS Backend Runner")
parser.add_argument("--host", default=None)
parser.add_argument("--port", type=int, default=None)
parser.add_argument("--cpu", action="store_true", help="Force CPU mode")
args, _unknown = parser.parse_known_args()

# ─── Re-launch with venv Python if needed ─────────────────────
if not _is_venv and is_venv_valid():
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    if args.cpu:
        env["AICSS_DEVICE"] = "cpu"
    cmd = [_venv_python, __file__] + sys.argv[1:]
    print(f"[run.py] Detected virtual environment. Launching with:")
    print(f"         {' '.join(cmd)}")
    result = subprocess.run(cmd, env=env, cwd=_backend_dir)
    sys.exit(result.returncode)

# ─── Main: run the server ──────────────────────────────────────
if __name__ == "__main__":
    # sys.path setup so 'from app.xxx' works
    if _backend_dir not in sys.path:
        sys.path.insert(0, _backend_dir)

    # Force UTF-8 mode on Windows (fixes GBK encoding issues with pip, transformers)
    os.environ.setdefault("PYTHONUTF8", "1")

    import uvicorn
    from app.config import settings

    # Allow CLI overrides
    host = args.host or settings.host
    port = args.port or settings.port

    print(f"Starting AICSS Backend on {host}:{port}")
    print(f"  Device  : {settings.device}")
    print(f"  Depth   : {settings.depth_model}")
    print(f"  SAM2    : {settings.sam2_model_size}")

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=settings.reload,
    )
