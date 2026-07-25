#!/usr/bin/env python3
"""
Quick start script for AICSS backend.

Usage:
    python run.py                # auto-detects and uses .venv
    python run.py --cpu         # force CPU mode
    python run.py --download-vlm # download Qwen3-VL-4B-Instruct weights from hf-mirror
"""
import os
import sys
import subprocess
import argparse

# ─── Auto-detect venv Python ───────────────────────────────────
# Accept either `.venv` (project convention) or `venv` (often created by `python -m venv venv`).
_backend_dir = os.path.dirname(os.path.abspath(__file__))


def _locate_venv_python() -> str | None:
    """Return absolute path to the venv's python.exe / python, or None if not found.

    Search order:
      1. .venv (Scripts/python.exe on Windows, bin/python on POSIX)
      2. venv  (Scripts/python.exe on Windows, bin/python on POSIX)
    """
    is_windows = os.name == "nt"
    sub_scripts = "Scripts" if is_windows else "bin"
    exe = "python.exe" if is_windows else "python"

    for venv_name in (".venv", "venv"):
        candidate = os.path.join(_backend_dir, venv_name, sub_scripts, exe)
        if os.path.exists(candidate):
            return candidate
    return None


_venv_python = _locate_venv_python()

_current_python = os.path.abspath(sys.executable)
# Treat the script as "running inside venv" if its path lives under either .venv or venv
_is_venv = (os.sep + ".venv") in _current_python or (os.sep + "venv") in _current_python

# Backwards compat: older callers referenced this name
is_venv_valid = _venv_python is not None

# ─── Parse args before re-launch ────────────────────────────────
parser = argparse.ArgumentParser(description="AICSS Backend Runner")
parser.add_argument("--host", default=None)
parser.add_argument("--port", type=int, default=None)
parser.add_argument("--cpu", action="store_true", help="Force CPU mode")
parser.add_argument(
    "--download-vlm",
    action="store_true",
    help="Download Qwen3-VL-4B-Instruct weights from hf-mirror before starting the server",
)
args, _unknown = parser.parse_known_args()

# ─── Re-launch with venv Python if needed ─────────────────────
if not _is_venv and is_venv_valid:
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

    if args.download_vlm:
        # Download Qwen3-VL weights via the dedicated streaming helper
        # (hf-mirror.com endpoint, resumable, chunked progress).
        helper = os.path.join(_backend_dir, "download_qwen3vl.py")
        if not os.path.exists(helper):
            print(f"[run.py] ERROR: download helper missing: {helper}", file=sys.stderr)
            sys.exit(1)
        result = subprocess.run(
            [_venv_python if is_venv_valid else sys.executable, helper],
            cwd=_backend_dir,
        )
        if result.returncode != 0:
            print(f"[run.py] VLM download failed (exit={result.returncode})", file=sys.stderr)
            sys.exit(result.returncode)

    import uvicorn
    from app.config import settings

    # Allow CLI overrides
    host = args.host or settings.host
    port = args.port or settings.port

    print(f"Starting AICSS Backend on {host}:{port}")
    print(f"  Device  : {settings.device}")
    print(f"  Depth   : {settings.depth_model}")
    print(f"  SAM2    : {settings.sam2_model_size}")
    print(f"  VLM     : {settings.vlm_model}")

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=settings.reload,
    )
