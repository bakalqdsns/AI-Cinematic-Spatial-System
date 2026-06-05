"""
Configuration for AICSS backend.
All environment variables and model paths are managed here.
"""
import os
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

class Settings(BaseSettings):
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False  # Windows: set True only if file-watcher permissions allow WinError 10013

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

    # DashScope Wanx2.1 Image Edit
    dashscope_api_key: str = ""
    dashscope_model: str = "wanx2.1-imageedit"
    dashscope_function: str = "description_edit_with_mask"
    inpaint_timeout: int = 120

    class Config:
        env_prefix = "AICSS_"
        extra = "ignore"


settings = Settings()

# Convenience
DEVICE = settings.device
print(f"[AICSS Config] Device: {DEVICE}")
print(f"[AICSS Config] Depth model: {settings.depth_model}")
print(f"[AICSS Config] SAM2 size: {settings.sam2_model_size}")
