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

# ── CUDA diagnostics ──────────────────────────────────────────────────────────
_cuda_available = torch.cuda.is_available()
_torch_cuda_ver = getattr(torch.version, "cuda", None)
if _cuda_available:
    _gpu_name = torch.cuda.get_device_name(0)
    _gpu_mem = torch.cuda.get_device_properties(0).total_memory / (1024**3)
    print(f"[AICSS] CUDA detected — gpu={_gpu_name}, mem={_gpu_mem:.1f}GB, "
          f"torch.cuda={_torch_cuda_ver}")
else:
    print(f"[AICSS] CUDA NOT available — torch.cuda.is_available()=False, "
          f"torch.version.cuda={_torch_cuda_ver}. Models will run on CPU.")

class Settings(BaseSettings):
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
    # SAM2 model size: vit_l (large, -> sam2.1_l.pt), vit_b (base, -> sam2.1_b.pt), vit_s, vit_t
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

    # LaMa inpainting model (local, replaces DashScope API)
    lama_checkpoint_dir: Path = CACHE_DIR / "lama"

    # ── Local LLM (llama.cpp Qwen3.5-9B-GGUF) ─────────────────────────────────
    # Start with: llama-server -hf lmstudio-community/Qwen3.5-9B-GGUF:Q4_K_M
    #             -c 8192 --host 0.0.0.0 --port 8080
    llm_base_url: str = "http://localhost:8080/v1"
    llm_model: str = "qwen3.5-9b"
    llm_timeout: float = 180.0

    # ── Local Image Generation (Stable Diffusion XL / Z-Image) ─────────────────
    # Model candidates (tried in order; first available is used):
    #   Tongyi-MAI/Z-Image  — Z-Image (primary, when available)
    #   stabilityai/stable-diffusion-xl-base-1.0  — SDXL (fallback)
    image_model_id: str = "stabilityai/stable-diffusion-xl-base-1.0"
    image_dtype: str = "bfloat16"  # "float16" | "bfloat16" | "float32"

    # ── Video Generation Provider ────────────────────────────────────────────────
    # Options:
    #   "dashscope"  — wan2.7-i2v via DashScope API (cloud, high quality)
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

    class Config:
        env_prefix = "AICSS_"
        extra = "ignore"


settings = Settings()

# Ensure workspace directories exist on startup
(settings.workspace_dir / "projects").mkdir(parents=True, exist_ok=True)

# Convenience
DEVICE = settings.device
print(f"[AICSS Config] Device: {DEVICE}")
print(f"[AICSS Config] Depth model: {settings.depth_model}")
print(f"[AICSS Config] SAM2 size: {settings.sam2_model_size}")
print(f"[AICSS Config] VLM model: {settings.vlm_model}")
