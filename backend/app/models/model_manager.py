"""
Model Manager — singleton that loads and manages all ML models.

单例模式说明：
- 模型在 GPU 上加载后占用大量显存，多个实例会浪费内存
- 整个应用只需要一份模型副本，所有请求共享使用
- __init__ 仅初始化占位符（None），真正的模型在 load_all() 时才加载
  —— 这就是延迟加载（lazy loading），避免启动时一次性加载所有模型导致卡顿
- 三个 @property 装饰的属性也体现了延迟加载思想：访问时才检查是否已加载

Usage:
    manager = ModelManager()
    manager.load_all()
    depth_map = manager.depth_model.predict(image_tensor)
"""
import torch
from typing import Optional
from app.config import settings, DEVICE
from .depth_loader import DepthModel
from .grounding_dino_loader import GroundingDinoModel
from .sam2_loader import SAM2Model


class ModelManager:
    def __init__(self):
        self._depth: Optional[DepthModel] = None
        self._grounding_dino: Optional[GroundingDinoModel] = None
        self._sam2: Optional[SAM2Model] = None
        self._loaded = False

    @property
    def depth_model(self) -> DepthModel:
        if self._depth is None:
            raise RuntimeError("Depth model not loaded. Call load_all() first.")
        return self._depth

    @property
    def grounding_dino(self) -> GroundingDinoModel:
        if self._grounding_dino is None:
            raise RuntimeError("Grounding DINO model not loaded. Call load_all() first.")
        return self._grounding_dino

    @property
    def sam2(self) -> SAM2Model:
        if self._sam2 is None:
            raise RuntimeError("SAM2 model not loaded. Call load_all() first.")
        return self._sam2

    def load_all(self):
        """Load all models. Call once on startup."""
        print("[ModelManager] Loading DepthAnything V2...")
        self._depth = DepthModel(
            model_name=settings.depth_model,
            device=DEVICE,
        )
        self._depth.load()

        print("[ModelManager] Loading Grounding DINO...")
        self._grounding_dino = GroundingDinoModel(
            model_name=settings.grounding_dino_model,
            device=DEVICE,
        )
        self._grounding_dino.load()

        print("[ModelManager] Loading SAM2...")
        sam2_checkpoint_dir = str(settings.sam2_checkpoint_dir) if settings.sam2_checkpoint_dir else None
        self._sam2 = SAM2Model(
            model_size=settings.sam2_model_size,
            device=DEVICE,
            checkpoint_dir=sam2_checkpoint_dir,
        )
        self._sam2.load()

        self._loaded = True
        print("[ModelManager] All models ready.")

    def is_loaded(self) -> bool:
        return self._loaded

    def unload_all(self):
        """
        释放 GPU 显存中的模型。

        深度学习模型（尤其是在 GPU 上运行的）不会自动被 Python GC 回收，
        因为 PyTorch 会维护对 GPU 内存的引用。显式设置为 None 后调用
        torch.cuda.empty_cache() 才能将显存归还给 GPU 驱动，
        防止长时间运行的服务（如 API 服务）因显存泄漏而崩溃。
        """
        self._depth = None
        self._grounding_dino = None
        self._sam2 = None
        self._loaded = False
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


model_manager = ModelManager()
