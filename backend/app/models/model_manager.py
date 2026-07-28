"""
Model Manager — singleton that loads and manages all ML models.

Cloud-first architecture:
- In "cloud" mode (default), LLM, VLM, and image generation delegate to DashScope API.
  llama-server is not started, and local VLM/image models are not loaded.
- In "local" mode, all models run locally via llama-server, Qwen3-VL, Z-Image-Turbo, etc.
- Depth and SAM2 always run locally (no DashScope equivalent).

按需加载设计：
- 启动时不加载任何模型，FastAPI 收到第一个请求时才触发懒加载
- 每个模型独立 load/unload，管线内每步用完立即卸载
- 管线模型使用顺序（POST /analyze）：
  1. DepthAnything  → depth_map 提取后立即卸载
  2. Qwen3-VL        → detected_classes 字符串列表拿到后立即卸载
  3. Grounding DINO  → boxes/scores numpy 提取后立即卸载
  4. SAM2            → masks numpy 提取后立即卸载
管线结束显存峰值 ≈ Grounding DINO + SAM2 ≈ 4-7 GB（vs 原来 16-22 GB 全量常驻）

Usage:
    manager = ModelManager()
    # 懒加载：首次访问 property 时自动加载
    depth_map = manager.depth_model.predict(image)
    # 手动卸载（管线内用完即弃）
    manager.unload_depth()

Download-only (no GPU) API:
    manager.ensure_depth_downloaded()   # fetch checkpoint to disk
    manager.ensure_sam2_downloaded()     # fetch checkpoint to disk
    manager.ensure_lama_downloaded()    # fetch checkpoint to disk
    manager.ensure_z_image_downloaded()  # fetch snapshot to disk
    manager.ensure_grounding_dino_downloaded()
    manager.ensure_qwen3vl_downloaded()
"""
import os
import torch
import time
from pathlib import Path
from typing import Optional
from app.config import settings, DEVICE
from app.models.depth_loader import DepthModel
from app.models.grounding_dino_loader import GroundingDinoModel
from app.models.sam2_loader import SAM2Model
from app.models.qwen3vl_loader import Qwen3VLModel
from app.models.lama_loader import LaMaModel, LAMA_FILENAME
from app.models.z_image_loader import ZImageModel


class ModelManager:
    def __init__(self):
        self._depth: Optional[DepthModel] = None
        self._grounding_dino: Optional[GroundingDinoModel] = None
        self._sam2: Optional[SAM2Model] = None
        self._qwen3vl: Optional[Qwen3VLModel] = None
        self._lama: Optional[LaMaModel] = None
        self._z_image: Optional[ZImageModel] = None
        self._loaded = False
        self._dashscope_client = None

    # ── Cloud mode accessors ────────────────────────────────────────────────

    @property
    def use_cloud(self) -> bool:
        """Whether we are running in cloud mode (DashScope API for LLM/VLM/Image)."""
        from app.config import settings as _s
        return _s.model_mode == "cloud"

    @property
    def dashscope_client(self):
        """Lazily create and return the shared DashScopeClient singleton."""
        if self._dashscope_client is None:
            from app.services.dashscope_client import get_dashscope_client
            self._dashscope_client = get_dashscope_client()
        return self._dashscope_client

    # ── Cloud-mode convenience wrappers ─────────────────────────────────────

    def cloud_llm_chat(self, messages: list[dict], temperature: float = 0.3, max_tokens: int = 4096) -> str:
        """Send a chat request via DashScope API. Raises if not in cloud mode."""
        if not self.use_cloud:
            raise RuntimeError("cloud_llm_chat() called in local mode — use local_llm instead")
        return self.dashscope_client.chat(messages, temperature=temperature, max_tokens=max_tokens)

    def cloud_vlm_analyze(self, image, prompt: str) -> str:
        """Analyze an image via DashScope VLM. Raises if not in cloud mode."""
        if not self.use_cloud:
            raise RuntimeError("cloud_vlm_analyze() called in local mode — use qwen3vl instead")
        return self.dashscope_client.vlm_analyze(image, prompt)

    def cloud_generate_image(self, prompt: str, size: str = "1024*1024", n: int = 1) -> list[str]:
        """Generate images via DashScope. Raises if not in cloud mode."""
        if not self.use_cloud:
            raise RuntimeError("cloud_generate_image() called in local mode — use image_model instead")
        return self.dashscope_client.generate_image(prompt, size=size, n=n)

    # ── Lazy-load properties ───────────────────────────────────────────────────

    @property
    def depth_model(self) -> DepthModel:
        if self._depth is None:
            self.load_depth()
        return self._depth

    @property
    def grounding_dino(self) -> GroundingDinoModel:
        if self._grounding_dino is None:
            self.load_grounding_dino()
        return self._grounding_dino

    @property
    def sam2(self) -> SAM2Model:
        if self._sam2 is None:
            self.load_sam2()
        return self._sam2

    @property
    def qwen3vl(self) -> Qwen3VLModel:
        if self._qwen3vl is None:
            self.load_qwen3vl()
        return self._qwen3vl

    @property
    def lama_model(self) -> LaMaModel:
        if self._lama is None:
            self.load_lama()
        return self._lama

    @property
    def image_model(self) -> ZImageModel:
        if self._z_image is None:
            self.load_z_image()
        return self._z_image

    # ── Download-only helpers (no GPU) ─────────────────────────────────────────

    def ensure_depth_downloaded(self) -> None:
        """Fetch DepthAnything checkpoint to disk (no GPU)."""
        if self._depth is not None:
            return  # already loaded
        loader = DepthModel(model_name=settings.depth_model, device="cpu")
        loader.ensure_downloaded()

    def ensure_grounding_dino_downloaded(self) -> None:
        """Fetch Grounding DINO checkpoint to disk (no GPU)."""
        if self._grounding_dino is not None:
            return
        loader = GroundingDinoModel(model_name=settings.grounding_dino_model, device="cpu")
        loader.ensure_downloaded()

    def ensure_sam2_downloaded(self) -> None:
        """Fetch SAM2 checkpoint to disk (no GPU)."""
        if self._sam2 is not None:
            return
        loader = SAM2Model(device="cpu", checkpoint_dir=str(settings.sam2_checkpoint_dir) if settings.sam2_checkpoint_dir else None)
        loader.ensure_downloaded()

    def ensure_qwen3vl_downloaded(self) -> None:
        """Fetch Qwen3-VL checkpoint to disk (no GPU)."""
        if self._qwen3vl is not None:
            return
        loader = Qwen3VLModel(model_name=settings.vlm_model, device="cpu")
        loader.ensure_downloaded()

    def ensure_lama_downloaded(self) -> None:
        """Fetch LaMa checkpoint to disk (no GPU)."""
        if self._lama is not None:
            return
        loader = LaMaModel(device="cpu", checkpoint_dir=str(settings.lama_checkpoint_dir) if settings.lama_checkpoint_dir else None)
        loader.ensure_downloaded()

    def ensure_z_image_downloaded(self) -> None:
        """Fetch Z-Image snapshot to disk (no GPU)."""
        if self._z_image is not None:
            return
        loader = ZImageModel(
            model_id=settings.image_model_id,
            checkpoint_dir=str(settings.image_checkpoint_dir),
        )
        loader.ensure_downloaded()

    # ── Individual load methods ───────────────────────────────────────────────

    def load_depth(self) -> None:
        """Load DepthAnything V2 on first use."""
        if self._depth is not None:
            return
        t0 = time.time()
        print("[ModelManager] Loading DepthAnything V2...")
        try:
            loader = DepthModel(model_name=settings.depth_model, device=DEVICE)
            loader.load()
            self._depth = loader
            print(f"[ModelManager] DepthAnything V2 ready in {time.time() - t0:.1f}s")
        except FileNotFoundError as e:
            hint = self._get_download_hint("depth", {"path": str(settings.depth_checkpoint_dir)})
            raise RuntimeError(
                f"Depth model not found. Please download it first.\n{hint}"
            ) from e

    def load_grounding_dino(self) -> None:
        """Load Grounding DINO on first use."""
        if self._grounding_dino is not None:
            return
        t0 = time.time()
        print("[ModelManager] Loading Grounding DINO...")
        try:
            loader = GroundingDinoModel(
                model_name=settings.grounding_dino_model,
                device=DEVICE,
            )
            loader.load()
            self._grounding_dino = loader
            print(f"[ModelManager] Grounding DINO ready in {time.time() - t0:.1f}s")
        except FileNotFoundError as e:
            hint = self._get_download_hint("grounding_dino", {"path": str(settings.grounding_dino_checkpoint_dir)})
            raise RuntimeError(
                f"Grounding DINO model not found. Please download it first.\n{hint}"
            ) from e

    def load_sam2(self) -> None:
        """Load SAM2 on first use."""
        if self._sam2 is not None:
            return
        t0 = time.time()
        print("[ModelManager] Loading SAM2...")
        try:
            sam2_checkpoint_dir = str(settings.sam2_checkpoint_dir) if settings.sam2_checkpoint_dir else None
            loader = SAM2Model(
                model_size=settings.sam2_model_size,
                device=DEVICE,
                checkpoint_dir=sam2_checkpoint_dir,
            )
            loader.load()
            self._sam2 = loader
            print(f"[ModelManager] SAM2 ready in {time.time() - t0:.1f}s")
        except FileNotFoundError as e:
            hint = self._get_download_hint("sam2", {"path": str(settings.sam2_checkpoint_dir)})
            raise RuntimeError(
                f"SAM2 checkpoint not found. Please download it first.\n{hint}"
            ) from e

    def load_qwen3vl(self) -> None:
        """Load Qwen3-VL on first use."""
        if self._qwen3vl is not None:
            return
        t0 = time.time()
        print("[ModelManager] Loading Qwen3-VL (8GB bfloat16)...")
        try:
            loader = Qwen3VLModel(
                model_name=settings.vlm_model,
                device=DEVICE,
                max_new_tokens=settings.vlm_max_new_tokens,
            )
            loader.load()
            self._qwen3vl = loader
            print(f"[ModelManager] Qwen3-VL ready in {time.time() - t0:.1f}s")
        except FileNotFoundError as e:
            hint = self._get_download_hint("qwen3vl", {"path": str(settings.vlm_checkpoint_dir)})
            raise RuntimeError(
                f"Qwen3-VL model not found. Please download it first.\n{hint}"
            ) from e

    def load_lama(self) -> None:
        """Load LaMa inpainting model on first use."""
        if self._lama is not None:
            return
        t0 = time.time()
        print("[ModelManager] Loading LaMa inpainting...")
        try:
            lama_checkpoint_dir = str(settings.lama_checkpoint_dir) if settings.lama_checkpoint_dir else None
            loader = LaMaModel(
                device=DEVICE,
                checkpoint_dir=lama_checkpoint_dir,
            )
            loader.load()
            self._lama = loader
            print(f"[ModelManager] LaMa ready in {time.time() - t0:.1f}s")
        except FileNotFoundError as e:
            hint = self._get_download_hint("lama", {"path": str(settings.lama_checkpoint_dir)})
            raise RuntimeError(
                f"LaMa model not found. Please download it first.\n{hint}"
            ) from e

    def load_z_image(self) -> ZImageModel:
        """
        Build / return the ZImageModel handle.  ``ensure_downloaded`` is
        called separately by ``ensure_all_downloaded`` so a brand-new
        install pulls the ~33 GB snapshot once at startup, in the
        foreground, instead of surprising the user on first inference.
        This method just wires the model_id / checkpoint_dir from settings.
        """
        if self._z_image is None:
            loader = ZImageModel(
                model_id=settings.image_model_id,
                checkpoint_dir=str(settings.image_checkpoint_dir),
            )
            loader.ensure_downloaded()  # raises on failure
            self._z_image = loader
        return self._z_image

    # ── Individual unload methods ─────────────────────────────────────────────

    def _clear_cuda_cache(self) -> None:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()

    def unload_depth(self) -> None:
        """Release DepthAnything V2 from GPU memory."""
        if self._depth is None:
            return
        self._depth = None
        self._clear_cuda_cache()
        print("[ModelManager] DepthAnything V2 unloaded.")

    def unload_grounding_dino(self) -> None:
        """Release Grounding DINO from GPU memory."""
        if self._grounding_dino is None:
            return
        self._grounding_dino = None
        self._clear_cuda_cache()
        print("[ModelManager] Grounding DINO unloaded.")

    def unload_sam2(self) -> None:
        """Release SAM2 from GPU memory."""
        if self._sam2 is None:
            return
        self._sam2 = None
        self._clear_cuda_cache()
        print("[ModelManager] SAM2 unloaded.")

    def unload_qwen3vl(self) -> None:
        """Release Qwen3-VL from GPU memory."""
        if self._qwen3vl is None:
            return
        self._qwen3vl = None
        self._clear_cuda_cache()
        print("[ModelManager] Qwen3-VL unloaded (freed ~8GB VRAM).")

    def unload_lama(self) -> None:
        """Release LaMa from GPU/CPU memory."""
        if self._lama is None:
            return
        self._lama = None
        self._clear_cuda_cache()
        print("[ModelManager] LaMa unloaded.")

    def unload_z_image(self) -> None:
        """Release the Z-Image loader handle.  The actual pipeline (held by
        ``image_generator._img_gen``) is freed by its own ``LocalImageGenerator.unload()``."""
        if self._z_image is None:
            return
        self._z_image = None
        print("[ModelManager] Z-Image loader handle released.")

    # ── Bulk load / unload (backward compatibility) ───────────────────────────

    def load_all(self) -> None:
        """Load all models. Call manually or via lifespan when AICSS_LAZY_LOAD=false."""
        self.load_depth()
        self.load_grounding_dino()
        self.load_sam2()
        self.load_qwen3vl()
        self.load_lama()
        self.load_z_image()
        self._loaded = True
        print("[ModelManager] All models ready.")

    def ensure_all_downloaded(self) -> None:
        """
        Pre-flight: ensure every model's checkpoint is on disk before we
        start loading any of them into GPU memory.

        Each underlying loader already does its own two-phase logic inside
        ``load()``; this method just surfaces downloads that take a long
        time (LaMa's ``big-lama.pt`` is ~200 MB, Z-Image-Turbo is ~33 GB,
        Qwen3-VL is several GB) with explicit progress so users see
        something is happening.

        Safe to call repeatedly — once a checkpoint is on disk it is reused.
        """
        print("[ModelManager] Pre-flight: ensuring all checkpoints are on disk...")

        # DepthAnything / Grounding DINO / Qwen3-VL are HF Hub models whose
        # ``load()`` already does the two-phase (online → local cache) dance.
        # We just touch them once to trigger any download.
        # SAM2, LaMa, and Z-Image each need an explicit pre-step before
        # their loader runs.

        # LaMa: pure disk download (no torch / GPU), cheap to do first.
        try:
            lama = LaMaModel(device="cpu")
            lama.ensure_downloaded()
        except Exception as e:
            print(f"[ModelManager] WARNING: LaMa checkpoint pre-flight failed: {e}")

        # SAM2: download via huggingface_hub.snapshot_download. Also cheap
        # (only file IO, no model loading yet).
        try:
            sam2 = SAM2Model(device="cpu")
            sam2.ensure_downloaded()
        except Exception as e:
            print(f"[ModelManager] WARNING: SAM2 checkpoint pre-flight failed: {e}")

        # Z-Image-Turbo: HF Hub (Xet disabled) → ModelScope mirror.  This is
        # the biggest single download in AICSS (~33 GB) — surfacing it here
        # at startup means the user sees one clear network round-trip
        # instead of the pipeline lazily fetching halfway through a request.
        if settings.image_model_id:
            try:
                z_image = ZImageModel(
                    model_id=settings.image_model_id,
                    checkpoint_dir=str(settings.image_checkpoint_dir),
                )
                z_image.ensure_downloaded()
            except Exception as e:
                print(f"[ModelManager] WARNING: Z-Image checkpoint pre-flight failed: {e}")

        print("[ModelManager] All checkpoints are present on disk.")

    def is_loaded(self) -> bool:
        return self._loaded

    def unload_all(self) -> None:
        """Unload all models and reclaim GPU memory."""
        self.unload_depth()
        self.unload_grounding_dino()
        self.unload_sam2()
        self.unload_qwen3vl()
        self.unload_lama()
        self.unload_z_image()
        self._loaded = False
        self._clear_cuda_cache()
        print("[ModelManager] All models unloaded.")

    # ── Status ────────────────────────────────────────────────────────────────

    def model_status(self) -> dict:
        """Return loading status of each model (for /health endpoint)."""
        return {
            "depth": self._depth is not None,
            "grounding_dino": self._grounding_dino is not None,
            "sam2": self._sam2 is not None,
            "qwen3vl": self._qwen3vl is not None,
            "lama": self._lama is not None,
            "image": self._z_image is not None,
        }

    def check_models_status(self) -> dict[str, dict]:
        """
        Check download/availability status of each model.
        Returns dict with model name -> {available: bool, info: str}.
        """
        from pathlib import Path
        from app.config import CACHE_DIR, settings as _s

        status = {}
        status["_meta"] = {"model_mode": _s.model_mode}
        hf_cache = CACHE_DIR / "huggingface"

        # Depth model
        depth_path = hf_cache / "hub" / "models--depth-anything--Depth-Anything-V2-Large-hf"
        status["depth"] = {
            "available": depth_path.exists() or self._depth is not None,
            "path": str(depth_path),
            "model": settings.depth_model,
        }

        # Grounding DINO
        dino_path = hf_cache / "hub" / f"models--{settings.grounding_dino_model.replace('/', '--')}"
        status["grounding_dino"] = {
            "available": dino_path.exists() or self._grounding_dino is not None,
            "path": str(dino_path),
            "model": settings.grounding_dino_model,
        }

        # SAM2
        sam2_path = settings.sam2_checkpoint_dir
        sam2_available = (
            (sam2_path and sam2_path.exists() and list(sam2_path.glob("*.pt")))
            or self._sam2 is not None
        )
        status["sam2"] = {
            "available": sam2_available,
            "path": str(sam2_path) if sam2_path else "N/A",
            "model": f"facebook/sam2.1_{settings.sam2_model_size}",
        }

        # Qwen3-VL
        qwen_path = settings.vlm_checkpoint_dir
        qwen_available = (
            (qwen_path and qwen_path.exists() and list(qwen_path.glob("*.safetensors")))
            or self._qwen3vl is not None
        )
        status["qwen3vl"] = {
            "available": qwen_available,
            "path": str(qwen_path) if qwen_path else "N/A",
            "model": settings.vlm_model,
            "download_script": "python download_qwen3vl.py",
        }

        # LaMa — use the loader's own checkpoint resolver for accuracy
        lama_path = settings.lama_checkpoint_dir
        lama_ckpt = None
        try:
            lama_checker = LaMaModel(device="cpu", checkpoint_dir=str(lama_path) if lama_path else None)
            lama_ckpt = lama_checker._local_checkpoint()
        except Exception:
            pass
        lama_available = (
            (lama_ckpt is not None)
            or self._lama is not None
        )
        status["lama"] = {
            "available": lama_available,
            "path": lama_ckpt or (str(lama_path) if lama_path else "N/A"),
        }

        # Z-Image (text-to-image).  We treat a hub/snapshots/<rev> containing
        # model_index.json + transformer/ + text_encoder/ + vae/ as the
        # authoritative availability signal — that's what
        # ZImagePipeline.from_pretrained() actually needs.
        z_path = settings.image_checkpoint_dir
        z_available = (
            (z_path and z_path.exists() and any(z_path.glob("**/model_index.json")))
            or self._z_image is not None
        )
        status["image"] = {
            "available": z_available,
            "path": str(z_path) if z_path else "N/A",
            "model": settings.image_model_id,
        }

        return status

    def get_missing_models_info(self) -> list[dict]:
        """
        Return information about missing models that need to be downloaded.
        """
        status = self.check_models_status()
        missing = []

        for name, info in status.items():
            if not info["available"]:
                missing.append({
                    "model": name,
                    "path": info["path"],
                    "download_hint": self._get_download_hint(name, info),
                })

        return missing

    def _get_download_hint(self, model_name: str, info: dict) -> str:
        """Get download hint for a specific model."""
        hints = {
            "depth": (
                "Run: huggingface-cli download depth-anything/Depth-Anything-V2-Large-hf\n"
                "  Or: pip install transformers && python -c \"from transformers import AutoModelForDepthEstimation; "
                "AutoModelForDepthEstimation.from_pretrained('depth-anything/Depth-Anything-V2-Large-hf')\""
            ),
            "grounding_dino": (
                "Run: huggingface-cli download IDEA-Research/grounding-dino-base\n"
                "  Or: pip install transformers && python -c \"from transformers import AutoModelForZeroShotObjectDetection; "
                "AutoModelForZeroShotObjectDetection.from_pretrained('IDEA-Research/grounding-dino-base')\""
            ),
            "sam2": (
                f"Download SAM2 checkpoint from: https://github.com/facebookresearch/segment-anything-2\n"
                f"Place in: {info['path']}\n"
                f"Or: huggingface-cli download facebook/sam2.1_{settings.sam2_model_size}"
            ),
            "qwen3vl": (
                "Run: python download_qwen3vl.py  (uses hf-mirror.com)\n"
                "  Or: huggingface-cli download Qwen/Qwen3-VL-4B-Instruct\n"
                f"Place in: {info['path']}"
            ),
            "lama": (
                "Download LaMa model from: https://github.com/advimman/lama#model-checkpoints\n"
                f"Place in: {info['path']}\n"
                "Required file: big-lama.zip (or lama-model.pth)"
            ),
            "image": (
                "Run the AICSS server — startup pre-flight downloads Z-Image-Turbo from HF Hub "
                "(via hf-mirror.com) and falls back to ModelScope if HF Hub fails.\n"
                f"Target directory: {info['path']}\n"
                f"Model: {settings.image_model_id}\n"
                "Or download manually:\n"
                "  huggingface-cli download Tongyi-MAI/Z-Image-Turbo "
                "--local-dir <path>\n"
                "  OR\n"
                "  python -c \"from modelscope import snapshot_download; "
                f"snapshot_download('{settings.image_model_id}', "
                "allow_patterns=['transformer/*.safetensors','text_encoder/*.safetensors',"
                "'vae/*.safetensors','tokenizer/*','scheduler/*','model_index.json',"
                "'transformer/*.json','text_encoder/*.json','vae/*.json'])\""
            ),
        }
        return hints.get(model_name, "Please download this model manually.")


model_manager = ModelManager()
