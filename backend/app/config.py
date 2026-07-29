"""
Configuration for AICSS backend.
All environment variables and model paths are managed here.
"""
import os
import torch
from pathlib import Path
from pydantic_settings import BaseSettings

# Project root
BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / ".cache"
CACHE_DIR.mkdir(exist_ok=True)

# Redirect all HuggingFace downloads to project cache (Grounding DINO, Depth, etc.)
# This must be set BEFORE any transformers/ huggingface_hub imports
os.environ.setdefault("HF_HOME", str(CACHE_DIR / "huggingface"))
os.environ.setdefault("HF_HUB_CACHE", str(CACHE_DIR / "huggingface" / "hub"))
os.environ.setdefault("TRANSFORMERS_CACHE", str(CACHE_DIR / "huggingface" / "transformers"))
# Bump the per-request timeout — huggingface_hub's hard-coded default is 10 s
# which is too short for multi-hundred-MB checkpoints on slow / proxied
# networks (manifests as ``WinError 10060``).  Override via HF_HUB_DOWNLOAD_TIMEOUT.
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "600")
# Bypass the Xet/CAS (cas-server.xethub.hf.co) reconstruction path.  The CAS
# service requires auth and cannot be proxied through hf-mirror.com, which is
# why downloads otherwise return ``401 Unauthorized`` for any LFS-backed
# repo even when ``HF_ENDPOINT`` is set.  With Xet disabled, huggingface_hub
# falls back to plain HTTP redirects to ``cdn-lfs-*.hf.co`` (or the mirror
# equivalent) and downloads succeed.  Must be set BEFORE huggingface_hub is
# imported anywhere.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
# Use the China HF mirror so downloads don't go through huggingface.co directly
# (your network blocks huggingface.co; hf-mirror.com and dl.fbaipublicfiles.com are reachable).
# Override via HF_ENDPOINT env var.
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

# ── CUDA diagnostics ──────────────────────────────────────────────────────────
_cuda_available = torch.cuda.is_available()
_torch_cuda_ver = getattr(torch.version, "cuda", None)
if _cuda_available:
    _gpu_name = torch.cuda.get_device_name(0)
    _gpu_mem = torch.cuda.get_device_properties(0).total_memory / (1024**3)
    print(f"[AICSS] CUDA detected — gpu={_gpu_name}, mem={_gpu_mem:.1f}GB, "
          f"torch.cuda={_torch_cuda_ver}")
else:
    print("=" * 60)
    print("[AICSS] WARNING: CUDA is NOT available!")
    print(f"[AICSS]   torch.cuda.is_available() = False")
    print(f"[AICSS]   torch.version.cuda = {_torch_cuda_ver}")
    print("[AICSS] Models will run on CPU, which may be very slow.")
    print("[AICSS]")
    print("[AICSS] For GPU acceleration, install:")
    print("[AICSS]   1. NVIDIA driver (latest version)")
    print("[AICSS]   2. CUDA Toolkit 12.x")
    print("[AICSS]   3. PyTorch with CUDA support:")
    print("[AICSS]      pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121")
    print("=" * 60)

class Settings(BaseSettings):
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
        "env_prefix": "AICSS_",
    }

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = True

    # Device
    device: str = "cuda"  # "cuda" or "cpu"
    hf_token: str = ""

    # Model choices
    depth_model: str = "depth-anything/Depth-Anything-V2-Large-hf"
    # Grounding DINO model
    grounding_dino_model: str = "IDEA-Research/grounding-dino-base"
    # SAM2 model size: vit_l (large, -> sam2.1_hiera_large.pt), vit_b (base, -> sam2.1_hiera_base_plus.pt), vit_s, vit_t
    sam2_model_size: str = "vit_l"

    # SAM2 checkpoint paths
    sam2_checkpoint_dir: Path = CACHE_DIR / "sam2"
    grounding_dino_checkpoint_dir: Path = CACHE_DIR / "grounding-dino"
    depth_checkpoint_dir: Path = CACHE_DIR / "depth"

    # Qwen3-VL local model (replaces DashScope remote VLM)
    # Qwen3-VL-4B-Instruct runs locally; no API key needed.
    vlm_model: str = "Qwen/Qwen3-VL-4B-Instruct"
    vlm_checkpoint_dir: Path = CACHE_DIR / "qwen3vl"
    vlm_max_new_tokens: int = 256

    # Depth bucket configuration (meters)
    depth_buckets: list[tuple[float, float, str]] = [
        (0, 5, "foreground"),
        (5, 15, "midground"),
        (15, 50, "background"),
        (50, float("inf"), "sky"),
    ]

    # VLM (Qwen-VL) fallback prompts by scene type — used when no segmentation prompt is provided
    # and VLM detection fails or is disabled
    vlm_fallback_prompts: dict[str, str] = {
        "outdoor": "person.car.truck.tree.building.sky.road.grass.lamp.sign.mountain.water.flower",
        "indoor": "person.chair.table.sofa.bed.curtain.floor.wall.window.door.lamp.ceiling",
        "night": "person.car.building.light.sign.sky.window.lamp.tree.road.railing.boat",
        "nature": "tree.grass.rock.mountain.sky.cloud.water.hill.flower.bird.animal.road",
    }

    # Segmentation prompt — dot-separated class names to detect
    segmentation_prompt: str = "person.car.building.tree.lamp.door.window.chair.table.road.sky.mountain.water.grass.flower"

    # DashScope Wanx2.1 Image Edit (deprecated - now using local LaMa)
    dashscope_api_key: str = ""
    dashscope_model: str = "wanx2.1-imageedit"
    dashscope_function: str = "description_edit_with_mask"
    inpaint_timeout: int = 120

    # DashScope API keys — per-component. Each component can have its own key
    # so users can mix vendors / accounts. Empty string means "fall back to
    # the DASHSCOPE_API_KEY env var if set, otherwise the call will fail".
    dashscope_llm_api_key: str = ""
    dashscope_vlm_api_key: str = ""
    dashscope_image_api_key: str = ""
    dashscope_video_api_key: str = ""

    # LaMa inpainting model (local, replaces DashScope API)
    lama_checkpoint_dir: Path = CACHE_DIR / "lama"

    # ── Model Mode ────────────────────────────────────────────────────────────────
    # "cloud" (default): use DashScope API for LLM, VLM, image generation
    # "local": use local models (llama-server, Qwen3-VL, Z-Image-Turbo, etc.)
    model_mode: str = "cloud"

    # Per-component mode: overrides model_mode for each category
    vlm_mode: str = "cloud"      # "cloud" | "local" - controls VLM (scene analysis)
    image_mode: str = "cloud"    # "cloud" | "local" - controls image generation
    video_mode: str = "cloud"    # "cloud" | "local" - controls video generation

    # Cloud mode — DashScope model IDs
    dashscope_llm_model: str = "qwen-plus"
    dashscope_vlm_model: str = "qwen-vl-chat-v1"
    dashscope_image_model: str = "wanx-v1"

    # ── Local LLM (llama.cpp Qwen2.5-7B-Instruct Q4_K_M GGUF) ──────────────────
    # Actual model on disk: Qwen/Qwen2.5-7B-Instruct-GGUF
    #   qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf + -00002-of-00002.gguf
    # llama-server is launched with --alias qwen2.5-7b-q4_k_m (server_manager.py)
    # Start with: llama-server -m <path> -c 8192 -ngl 99 --host 0.0.0.0 --port 8080
    llm_base_url: str = "http://localhost:8080/v1"
    llm_model: str = "qwen2.5-7b-q4_k_m"
    # Generous timeout to cover slow CPU inference / long prompts.
    # Qwen2.5-7B Q4_K_M GGUF on CPU can take 5+ minutes per request.
    llm_timeout: float = 600.0

    # ── Local Image Generation (Z-Image-Turbo / Stable Diffusion XL) ────────────
    # Model candidates (tried in order; first available is used):
    #   Tongyi-MAI/Z-Image-Turbo  — Z-Image distilled (primary, fast, 9 steps, cfg=0.0)
    #   Tongyi-MAI/Z-Image         — Z-Image base (slower, higher quality)
    #   stabilityai/stable-diffusion-xl-base-1.0  — SDXL (fallback)
    image_model_id: str = "Tongyi-MAI/Z-Image-Turbo"
    image_dtype: str = "bfloat16"  # "float16" | "bfloat16" | "float32"
    # Where Z-Image-Turbo / SDXL weights live on disk.  The loader writes
    # there so HF Hub cache + ModelScope mirror both end up at the same path.
    image_checkpoint_dir: Path = CACHE_DIR / "z-image"

    # ── Default output sizes per asset type ──────────────────────────────────────
    # DashScope wanx supports (with full coverage): 1024*1024, 720*1280,
    # 1280*720. Other models (qwen-image, dalle, local SDXL) typically accept
    # arbitrary W*H. Both fields accept "WIDTH*HEIGHT" e.g. "1280*720".
    image_size_scene: str = "1280*720"    # landscape 16:9 — for environment shots
    image_size_character: str = "720*1280"  # portrait  9:16 — for character ref

    # ── Video Generation Provider ────────────────────────────────────────────────
    # Options:
    #   "dashscope"  — wanx-i2v via DashScope API (cloud, high quality)
    #   "local_wan"  — wan2.1-i2v local inference (28GB+ VRAM, requires Modelscope)
    #   "svd"        — Stable Video Diffusion (8GB VRAM, degraded quality)
    video_provider: str = "dashscope"

    # Model loading strategy
    # True=按需懒加载（默认，推荐，可节省 16-22GB 常驻显存）
    # False=启动时全量加载（兼容旧行为，服务器内存足够时使用）
    lazy_load: bool = True

    # Project Workspace
    workspace_dir: Path = BASE_DIR / ".workspace"
    project_id_format: str = "{timestamp}_{shot_id}"


settings = Settings()

# Ensure workspace directories exist on startup
(settings.workspace_dir / "projects").mkdir(parents=True, exist_ok=True)

# Convenience
DEVICE = settings.device
print(f"[AICSS Config] Device: {DEVICE}")
print(f"[AICSS Config] Model mode: {settings.model_mode} (cloud=qwen-plus | local={settings.llm_model})")
print(f"[AICSS Config] VLM mode: {settings.vlm_mode} | Image mode: {settings.image_mode} | Video mode: {settings.video_mode}")
print(f"[AICSS Config] Depth model: {settings.depth_model}")
print(f"[AICSS Config] SAM2 size: {settings.sam2_model_size}")
print(f"[AICSS Config] VLM model: {settings.vlm_model}")

# ── Startup health checks ──────────────────────────────────────────────────
def _check_dashscope_key(env_name: str, config_val: str, component: str) -> None:
    val = config_val or os.getenv(env_name, "")
    if not val:
        print(
            f"[AICSS WARNING] {component} mode is 'cloud' but no API key is configured. "
            f"Set {env_name} in your .env file. "
            f"Auto batch generation will fail silently without an error visible to the user."
        )

if settings.image_mode == "cloud":
    _check_dashscope_key(
        "DASHSCOPE_API_KEY",
        settings.dashscope_image_api_key,
        "Image generation (wanx-v1)",
    )
if settings.model_mode == "cloud":
    _check_dashscope_key(
        "DASHSCOPE_API_KEY",
        settings.dashscope_llm_api_key,
        "LLM visual prompt generation (qwen-plus)",
    )
