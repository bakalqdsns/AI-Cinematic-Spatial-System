"""
Depth Model Loader — Depth Anything V2 via HuggingFace Transformers.

本地优先：加载时使用 local_files_only=True，避免离线时触发 HuggingFace Hub 检查。
"""
import torch
import numpy as np
from PIL import Image
from typing import Union

from transformers import AutoImageProcessor, AutoModelForDepthEstimation

from app.config import settings
from app.models.hf_compat import auth_kwargs


def _snapshot_download_hf(model_name: str) -> str:
    """
    Download a HuggingFace model via snapshot_download (through hf-mirror.com)
    and return the local snapshot directory.  Raises on failure.
    """
    import os as _os
    _os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "600")
    _os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    _os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

    from huggingface_hub import snapshot_download
    token_kwargs = auth_kwargs(settings.hf_token)
    cache_dir = str(settings.depth_checkpoint_dir)
    local_dir = snapshot_download(
        repo_id=model_name,
        cache_dir=cache_dir,
        **token_kwargs,
    )
    return local_dir


class DepthModel:
    """
    Depth Anything V2 Large via HuggingFace Transformers.

    Usage:
        model = DepthModel(device="cuda")
        model.load()
        depth_np = model.predict(rgb_pil_image)  # HxW, float32, normalized 0-1
    """

    def __init__(
        self,
        model_name: str = "depth-anything/Depth-Anything-V2-Large-hf",
        device: str = "cuda",
    ):
        self.model_name = model_name
        _effective = device if torch.cuda.is_available() else "cpu"
        self.device = torch.device(_effective)
        if _effective != device:
            print(f"[DepthModel] CUDA unavailable — fell back to CPU (requested: {device})")
        self._processor = None
        self._model = None

    def ensure_downloaded(self) -> str:
        """
        Ensure the DepthAnything V2 checkpoint is on disk.  Returns the
        snapshot directory path that ``from_pretrained`` can use with
        ``local_files_only=True``.
        """
        print(f"[DepthModel] Ensuring {self.model_name} is on disk ...")
        path = _snapshot_download_hf(self.model_name)
        print(f"[DepthModel] Snapshot ready: {path}")
        return path

    def load(self):
        """Load model and processor. Tries online download first, falls back to local cache."""
        print(f"[DepthModel] Loading {self.model_name} on {self.device}...")
        token_kwargs = auth_kwargs(settings.hf_token)
        loaded = False

        # Phase 1: try online download (enables auto-download on first run)
        for phase, local_only in enumerate(["online (auto-download)", "local cache"], 1):
            try:
                print(f"[DepthModel]   phase {phase}: {local_only}...")
                self._processor = AutoImageProcessor.from_pretrained(
                    self.model_name,
                    local_files_only=local_only,
                    **token_kwargs,
                )
                self._model = AutoModelForDepthEstimation.from_pretrained(
                    self.model_name,
                    local_files_only=local_only,
                    **token_kwargs,
                )
                self._model.to(self.device)
                self._model.eval()
                print(f"[DepthModel]   ✓ loaded from {local_only}")
                loaded = True
                break
            except FileNotFoundError:
                print(f"[DepthModel]   ✗ not found in {local_only}, trying next...")
                self._processor = None
                self._model = None
                continue

        if not loaded:
            raise FileNotFoundError(
                f"Depth model '{self.model_name}' not found locally and could not be "
                f"downloaded. Check network / HF_TOKEN / proxy settings."
            )
        print("[DepthModel] Loaded.")

    def predict(self, image: Union[Image.Image, np.ndarray]) -> np.ndarray:
        """
        Predict depth map.

        Args:
            image: RGB PIL Image or numpy array (HxWx3)

        Returns:
            depth: numpy array HxW, float32, normalized 0-1 (1 = far, 0 = close)
        """
        if self._model is None:
            raise RuntimeError("Model not loaded. Call load() first.")

        if isinstance(image, np.ndarray):
            image = Image.fromarray(image.astype(np.uint8))

        orig_w, orig_h = image.size

        # Ensure RGB (RGBA base64 images from frontend would otherwise cause
        # "Unable to infer channel dimension format" in transformers >= 4.51)
        if image.mode != 'RGB':
            image = image.convert('RGB')

        inputs = self._processor(images=image, return_tensors="pt")
        pixel_values = inputs["pixel_values"].to(self.device)

        with torch.no_grad():
            outputs = self._model(pixel_values)
            if hasattr(outputs, "predicted_depth"):
                depth_pred = outputs.predicted_depth
            else:
                depth_pred = outputs.logits.squeeze(1)

        depth_pred = torch.nn.functional.interpolate(
            depth_pred.unsqueeze(1),
            size=(orig_h, orig_w),
            mode="bilinear",
            align_corners=False,
        ).squeeze(1)

        depth_np = depth_pred.squeeze().cpu().numpy()

        d_min, d_max = depth_np.min(), depth_np.max()
        if d_max - d_min > 1e-6:
            depth_np = (depth_np - d_min) / (d_max - d_min)

        return depth_np.astype(np.float32)

    def predict_meters(self, image: Union[Image.Image, np.ndarray], scale: float = 50.0) -> np.ndarray:
        """Return depth in approximate meters (relative scale)."""
        return self.predict(image) * scale
