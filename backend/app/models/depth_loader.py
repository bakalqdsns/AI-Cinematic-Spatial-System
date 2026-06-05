"""
Depth Model Loader — Depth Anything V2 via HuggingFace Transformers.

本地优先：使用离线缓存；可通过 AICSS_OFFLINE_ONLY=1 强制离线模式。
"""
import os
import torch
import numpy as np
from PIL import Image
from typing import Union

from transformers import AutoImageProcessor, AutoModelForDepthEstimation


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
        self.device = torch.device(device if torch.cuda.is_available() else "cpu")
        self._processor = None
        self._model = None

    def load(self):
        """Load model, first from local cache then with download fallback."""
        print(f"[DepthModel] Loading {self.model_name} on {self.device}...")
        local_only = os.environ.get("AICSS_OFFLINE_ONLY", "").lower() in ("1", "true", "yes")

        for local_only_flag in ([True, False] if not local_only else [True]):
            try:
                self._processor = AutoImageProcessor.from_pretrained(
                    self.model_name,
                    local_files_only=local_only_flag,
                )
                self._model = AutoModelForDepthEstimation.from_pretrained(
                    self.model_name,
                    local_files_only=local_only_flag,
                )
                self._model.to(self.device)
                self._model.eval()
                mode = "local cache" if local_only_flag else "downloaded"
                print(f"[DepthModel] Loaded ({mode}).")
                return
            except FileNotFoundError:
                if local_only_flag:
                    raise RuntimeError(
                        f"Depth model '{self.model_name}' not found in local cache. "
                        f"Run 'huggingface-cli download {self.model_name}' to cache it, "
                        f"or unset AICSS_OFFLINE_ONLY to allow download."
                    )
                continue
        raise RuntimeError(f"Failed to load Depth model '{self.model_name}'.")

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
