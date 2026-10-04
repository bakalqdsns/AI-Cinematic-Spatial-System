"""
Standalone OpenAPI dumper.

Imports `app.main:app` with heavy third-party dependencies stubbed out,
then writes the resolved OpenAPI schema to `frontend/openapi.json`.

This is needed because the backend cannot be started in this environment
(broken venv / no torch), but FastAPI builds its OpenAPI schema purely from
route decorators + Pydantic models, which only need fastapi + pydantic to
be importable. We stub everything else.
"""
import sys
import os
import json
import types
import importlib
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

# ── Generic stub factory ──────────────────────────────────────────────────────
class _StubModule(types.ModuleType):
    """A module stub that returns stubs for any attribute access."""
    def __init__(self, name):
        super().__init__(name)
        self.__path__ = []  # mark as package so `from X import Y` works
        self.__all__ = []
        self.__file__ = ""

    def __getattr__(self, attr):
        # Return a callable that accepts any args and returns a stub.
        # For attribute chains (torch.cuda.is_available), return another stub.
        stub = _StubAttr(f"{self.__name__}.{attr}")
        self.__dict__[attr] = stub
        return stub

    def __call__(self, *args, **kwargs):
        return _StubAttr(self.__name__ + "()")

class _StubAttr:
    """An attribute stub: callable, indexable, iterable, attribute-accessible."""
    def __init__(self, name):
        self._name = name

    def __getattr__(self, attr):
        if attr.startswith("_") and attr not in ("__iter__", "__call__", "__getitem__", "__bool__", "__len__", "__contains__"):
            raise AttributeError(attr)
        return _StubAttr(f"{self._name}.{attr}")

    def __call__(self, *args, **kwargs):
        # Many stubbed callables are used as decorators or class aliases.
        # Returning a new stub attr lets `@torch.no_grad` etc. work.
        return _StubAttr(f"{self._name}()")

    def __getitem__(self, key):
        return _StubAttr(f"{self._name}[{key!r}]")

    def __iter__(self):
        return iter([])

    def __bool__(self):
        return False

    def __len__(self):
        return 0

    def __contains__(self, key):
        return False

    def __repr__(self):
        return f"<StubAttr {self._name}>"

# Modules that must resolve to real packages (fastapi ecosystem already
# installed for the running interpreter). Everything else is stubbed.
REAL_PACKAGES = {
    "fastapi", "fastapi.responses", "pydantic", "pydantic_settings",
    "starlette", "starlette.responses", "starlette.routing",
    "typing_extensions", "anyio", "anyio._core",
    "app",  # our own package — must really import
}

# Heavy / native / unavailable third-party modules to stub.
STUB_MODULES = [
    "torch", "torchvision", "torchaudio",
    "numpy", "cv2", "PIL", "PIL.Image",
    "transformers", "diffusers", "accelerate", "huggingface_hub",
    "dashscope", "openai", "httpx", "websockets", "websocket",
    "sam2", "segment_anything", "groundingdino", "grounding_dino",
    "llama_cpp", "llama_cpp_python", "tiktoken", "tokenizers",
    "tqdm", "psutil", "gpustat", "pynvml",
    "skimage", "scipy", "matplotlib", "pandas",
    "yaml", "toml", "dotenv",  # dotenv is pure-python but harmless to stub
    "modelscope", "einops", "safetensors", "sentencepiece",
    "qwen_vl_utils", "av", "imageio", "imageio_ffmpeg",
    "ffmpeg", "ffmpeg_python",
    "ultralytics",
    "pydub",
]

def install_stub(name):
    if name in sys.modules:
        return
    mod = _StubModule(name)
    # For dotted names, ensure parent is set up
    parts = name.split(".")
    if len(parts) > 1:
        parent_name = ".".join(parts[:-1])
        install_stub(parent_name)
        parent = sys.modules[parent_name]
        setattr(parent, parts[-1], mod)
    sys.modules[name] = mod

for m in STUB_MODULES:
    install_stub(m)

# Special-case: numpy stub must expose common names used at import time
# (np.ndarray, np.float32, etc.) — _StubAttr handles attribute access.

# Make `from PIL import Image` work even if PIL was stubbed as a non-package
# (we set __path__ in _StubModule, so it's fine).

# ── Now import the app ────────────────────────────────────────────────────────
# Pre-set env vars to keep config.py quiet.
os.environ.setdefault("AICSS_DEVICE", "cpu")

try:
    from app.main import app
    schema = app.openapi()
    out = BACKEND_DIR.parent / "frontend" / "openapi.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(schema, f, ensure_ascii=False, indent=2)
    print(f"OK -> {out}")
    print(f"paths: {len(schema.get('paths', {}))}")
    print(f"components.schemas: {len(schema.get('components', {}).get('schemas', {}))}")
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"ERR: {e}")
    sys.exit(1)
