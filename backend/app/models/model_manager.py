"""
Model Manager — singleton that loads and manages all ML models.

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
        """Free GPU memory."""
        self._depth = None
        self._grounding_dino = None
        self._sam2 = None
        self._loaded = False
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


model_manager = ModelManager()
