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

# When the model_manager detects a complete local snapshot for a model, it
# flips ``HF_HUB_OFFLINE=1`` at runtime so subsequent ``cached_file`` /
# ``from_pretrained`` calls short-circuit to disk. We also let users set this
# from the environment to force offline mode globally (useful in air-gapped
# CI runs). Default stays "0" so the rest of the codebase can still fetch new
# models when needed.
os.environ.setdefault("HF_HUB_OFFLINE", "0")

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

    # ── Layer hint rules ─────────────────────────────────────────────────────────
    # Maps a GroundingDINO label (lowercase) to the layer it should hint toward.
    # Layers without an entry fall through to the depth-percentile bucket.
    # `ground` is special-cased in `object_detector.py` (it's routed to the
    # `ground` layer rather than a depth-banded layer).
    layer_hint_rules: dict[str, str] = {
        # Foreground anchors — humans / vehicles / animals
        "person": "foreground",
        "pedestrian": "foreground",
        "people": "foreground",
        "child": "foreground",
        "car": "foreground",
        "truck": "foreground",
        "van": "foreground",
        "bus": "foreground",
        "bicycle": "foreground",
        "motorcycle": "foreground",
        "animal": "foreground",
        "dog": "foreground",
        "cat": "foreground",
        "bird": "foreground",
        # Midground — small free-standing fixtures
        "lamp": "midground",
        "sign": "midground",
        "traffic light": "midground",
        "pole": "midground",
        "fire hydrant": "midground",
        "chair": "midground",
        "table": "midground",
        "sofa": "midground",
        "bed": "midground",
        "door": "midground",
        "window": "midground",
        "small tree": "midground",
        "flower": "midground",
        # Background — large static structures
        "building": "background",
        "mountain": "background",
        "tree": "background",
        "fence": "background",
        "wall": "background",
        # Ground / floor — independent layer
        "ground": "ground",
        "road": "ground",
        "floor": "ground",
        "sidewalk": "ground",
        "grass": "ground",
        "sand": "ground",
        "water": "ground",   # treated as ground plane for lakes/rivers
        "snow": "ground",
    }

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

    # ── Cloud LLM Provider ─────────────────────────────────────────────────────
    # Which cloud provider to use when model_mode == "cloud".
    #   "dashscope"  — use DashScope API (qwen-plus etc.)
    #   "toapi"      — use ToAPIs OpenAI-compatible API (gpt-5.6-terra etc.)
    cloud_llm_provider: str = "dashscope"
    cloud_vlm_provider: str = "dashscope"
    cloud_image_provider: str = "dashscope"
    cloud_video_provider: str = "dashscope"

    # ToAPIs API key — used for ALL toapi components (LLM + Image + Video).
    # Falls back to TOAPI_API_KEY env var if empty.
    toapi_llm_api_key: str = ""

    # ToAPIs model IDs (used when cloud_xxx_provider == "toapi").
    # Available models: https://docs.toapis.com
    toapi_llm_model: str = "gpt-5.6-terra"
    toapi_image_model: str = "gpt-image-2"
    toapi_video_model: str = "sora-2-vvip"

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

    # When True, the video provider is asked to render the action against a
    # flat green-screen backdrop and the segmenter applies a chroma-key pass
    # on top of the SAM2 mask. Frontend can override per-request via
    # POST /api/aicss/v2/scripts/motion/generate {"greenscreen": true}.
    motion_greenscreen_default: bool = False
    # When True, the segmenter snaps SAM2 masks to nearby Canny edges for
    # softer silhouettes. Same per-request override pattern as above.
    motion_feather_edges_default: bool = True

    # ── Custom Cloud Providers (user-defined, JSON-serializable) ────────────────
    # Each entry is a complete provider config that the CloudRouter will instantiate
    # on demand. This is the user-facing surface for adding new third-party models
    # without backend code changes.
    #
    # Built-in provider "types":
    #   - "dashscope"          (uses official SDK, requires DASHSCOPE_API_KEY)
    #   - "openai_compatible"  (works with any OpenAI-style REST API: ToAPIs,
    #                           SiliconFlow, Groq, OpenRouter, custom proxies, etc.)
    #
    # Schema per entry:
    #   {
    #     "name":         "siliconflow",            # unique key, lowercase
    #     "type":         "openai_compatible",
    #     "base_url":     "https://api.siliconflow.cn/v1",
    #     "api_key":      "sk-xxx",
    #     "extra_headers": {"X-App-Id": "..."},     # optional
    #     "extra_json":   {"response_format": ...}, # optional
    #     "models": {
    #       "llm":   "Qwen/Qwen2.5-7B-Instruct",
    #       "vlm":   "Qwen/Qwen2.5-VL-72B",
    #       "image": "black-forest-labs/FLUX.1-schnell",
    #       "video": null,                          # null → not supported
    #     }
    #   }
    #
    # The legacy single-provider fields (cloud_xxx_provider, dashscope_xxx_api_key,
    # toapi_xxx_model) are kept for backwards compat and are AUTO-MIGRATED into
    # the `providers` list on first startup.
    providers: list[dict] = []

    # Model loading strategy
    # True=按需懒加载（默认，推荐，可节省 16-22GB 常驻显存）
    # False=启动时全量加载（兼容旧行为，服务器内存足够时使用）
    lazy_load: bool = True

    # Project Workspace
    workspace_dir: Path = BASE_DIR / ".workspace"
    project_id_format: str = "{timestamp}_{shot_id}"

    # ── Cloud provider helpers (instance methods) ──────────────────────────────

    def get_provider_config(self, component: str) -> dict:
        """
        Return the active provider's config block for the given component.

        component: 'llm' | 'vlm' | 'image' | 'video'

        Returns a dict suitable for instantiating a BaseProvider:
            {
                "provider":      "toapi",                  # provider name (key)
                "type":          "openai_compatible",      # provider class type
                "api_key":       "sk-xxx",
                "base_url":      "https://toapis.com/v1",
                "extra_headers": {...},
                "extra_json":    {...},
                "model":         "gpt-5.6-terra",          # resolved model ID for this component
            }

        If `providers` is empty, falls back to legacy fields
        (cloud_xxx_provider / dashscope_xxx_api_key / etc.).
        """
        component_to_field = {
            "llm":   ("cloud_llm_provider",   "dashscope_llm_api_key",   "dashscope_llm_model",   "toapi_llm_model",   "toapi_llm_api_key"),
            "vlm":   ("cloud_vlm_provider",   "dashscope_vlm_api_key",   "dashscope_vlm_model",   None,                None),
            "image": ("cloud_image_provider", "dashscope_image_api_key", "dashscope_image_model", "toapi_image_model", "toapi_llm_api_key"),
            "video": ("cloud_video_provider", "dashscope_video_api_key", None,                    "toapi_video_model", "toapi_llm_api_key"),
        }
        fields = component_to_field.get(component)
        if fields is None:
            raise ValueError(f"Unknown component: {component!r}")
        prov_field, ds_key_field, ds_model_attr, toapi_model_attr, toapi_key_field = fields

        # New style: look up in self.providers list
        chosen_name = getattr(self, prov_field, "dashscope")
        for p in (self.providers or []):
            if p.get("name") == chosen_name:
                models = p.get("models") or {}
                model = models.get(component) or ""
                return {
                    "provider": chosen_name,
                    "type": p.get("type", "openai_compatible"),
                    "api_key": p.get("api_key", ""),
                    "base_url": p.get("base_url", ""),
                    "extra_headers": p.get("extra_headers"),
                    "extra_json": p.get("extra_json"),
                    "model": model,
                }

        # Legacy fallback: synthesize a provider block on the fly
        legacy_type = "openai_compatible" if chosen_name == "toapi" else "dashscope"
        legacy_model = ""
        legacy_key = ""
        legacy_url = ""
        if chosen_name == "toapi":
            legacy_model = getattr(self, toapi_model_attr, "") or ""
            legacy_key = getattr(self, toapi_key_field, "") or ""
            legacy_url = "https://toapis.com/v1"
        elif chosen_name == "dashscope":
            if ds_model_attr:
                legacy_model = getattr(self, ds_model_attr, "") or ""
            if ds_key_field:
                legacy_key = getattr(self, ds_key_field, "") or ""
            # DashScope SDK uses its own base; URL not strictly needed.
        return {
            "provider": chosen_name,
            "type": legacy_type,
            "api_key": legacy_key,
            "base_url": legacy_url,
            "extra_headers": None,
            "extra_json": None,
            "model": legacy_model,
        }

    def get_model_id(self, component: str) -> str:
        """Convenience: model ID for the given component."""
        return self.get_provider_config(component).get("model") or ""

    def list_user_providers(self) -> list[dict]:
        """Return the user-defined `providers` list (used by Settings UI)."""
        return list(self.providers or [])


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
