"""
Model Manager — singleton that loads and manages all ML models.

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
"""
import torch
import time
from typing import Optional
from app.config import settings, DEVICE
from .depth_loader import DepthModel
from .grounding_dino_loader import GroundingDinoModel
from .sam2_loader import SAM2Model
from .qwen3vl_loader import Qwen3VLModel
from .lama_loader import LaMaModel


class ModelManager:
    def __init__(self):
        self._depth: Optional[DepthModel] = None
        self._grounding_dino: Optional[GroundingDinoModel] = None
        self._sam2: Optional[SAM2Model] = None
        self._qwen3vl: Optional[Qwen3VLModel] = None
        self._lama: Optional[LaMaModel] = None
        self._loaded = False

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

    # ── Individual load methods ───────────────────────────────────────────────

    def load_depth(self) -> None:
        """Load DepthAnything V2 on first use."""
        if self._depth is not None:
            return
        t0 = time.time()
        print("[ModelManager] Loading DepthAnything V2...")
        try:
            self._depth = DepthModel(model_name=settings.depth_model, device=DEVICE)
            self._depth.load()
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
            self._grounding_dino = GroundingDinoModel(
                model_name=settings.grounding_dino_model,
                device=DEVICE,
            )
            self._grounding_dino.load()
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
            self._sam2 = SAM2Model(
                model_size=settings.sam2_model_size,
                device=DEVICE,
                checkpoint_dir=sam2_checkpoint_dir,
            )
            self._sam2.load()
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
            self._qwen3vl = Qwen3VLModel(
                model_name=settings.vlm_model,
                device=DEVICE,
                max_new_tokens=settings.vlm_max_new_tokens,
            )
            self._qwen3vl.load()
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
            self._lama = LaMaModel(
                device=DEVICE,
                checkpoint_dir=lama_checkpoint_dir,
            )
            self._lama.load()
            print(f"[ModelManager] LaMa ready in {time.time() - t0:.1f}s")
        except FileNotFoundError as e:
            hint = self._get_download_hint("lama", {"path": str(settings.lama_checkpoint_dir)})
            raise RuntimeError(
                f"LaMa model not found. Please download it first.\n{hint}"
            ) from e

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

    # ── Bulk load / unload (backward compatibility) ───────────────────────────

    def load_all(self) -> None:
        """Load all models. Call manually or via lifespan when AICSS_LAZY_LOAD=false."""
        self.load_depth()
        self.load_grounding_dino()
        self.load_sam2()
        self.load_qwen3vl()
        self.load_lama()
        self._loaded = True
        print("[ModelManager] All models ready.")

    def is_loaded(self) -> bool:
        return self._loaded

    def unload_all(self) -> None:
        """Unload all models and reclaim GPU memory."""
        self.unload_depth()
        self.unload_grounding_dino()
        self.unload_sam2()
        self.unload_qwen3vl()
        self.unload_lama()
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
        }

    def check_models_status(self) -> dict[str, dict]:
        """
        Check download/availability status of each model.
        Returns dict with model name -> {available: bool, info: str}.
        """
        from pathlib import Path
        from app.config import CACHE_DIR

        status = {}
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

        # LaMa
        lama_path = settings.lama_checkpoint_dir
        lama_available = (
            (lama_path and lama_path.exists() and list(lama_path.glob("*.pth")))
            or self._lama is not None
        )
        status["lama"] = {
            "available": lama_available,
            "path": str(lama_path) if lama_path else "N/A",
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
        }
        return hints.get(model_name, "Please download this model manually.")


model_manager = ModelManager()
