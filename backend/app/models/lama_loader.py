"""
LaMa (Large Mask Inpainting) Model Loader.

使用 simple-lama-inpainting 包加载本地 LaMa 模型进行图像修复。
LaMa 是 WACV 2022 论文 "Resolution-robust Large Mask Inpainting with Fourier Convolutions" 的实现。

参考: https://github.com/advimman/lama
pip: simple-lama-inpainting
"""

import torch
import numpy as np
from PIL import Image
from typing import Optional
import os


class LaMaModel:
    """
    LaMa 图像修复模型。

    支持 CPU/GPU 自动切换，首次使用时自动下载模型权重。

    Usage:
        model = LaMaModel(device="cuda")
        model.load()
        result = model.predict(image, mask)  # mask: 255=待修复区域
    """

    def __init__(self, device: str = "cuda", checkpoint_dir: Optional[str] = None):
        _effective = device if torch.cuda.is_available() else "cpu"
        self.device = torch.device(_effective)
        if _effective != device:
            print(f"[LaMa] CUDA unavailable — fell back to CPU (requested: {device})")

        default_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            ".cache", "lama"
        )
        self.checkpoint_dir = checkpoint_dir or default_dir
        self._model = None

    def load(self):
        """Load LaMa model. Downloads checkpoint on first run."""
        print(f"[LaMa] Loading LaMa on {self.device}...")

        try:
            from simple_lama_inpainting import SimpleLama
        except ImportError:
            raise ImportError(
                "simple-lama-inpainting not installed. "
                "Install with: pip install simple-lama-inpainting"
            )

        self._model = SimpleLama()
        print("[LaMa] Loaded.")

    def predict(
        self,
        image: Image.Image,
        mask: Image.Image,
    ) -> Image.Image:
        """
        使用 LaMa 模型进行图像修复。

        Args:
            image: RGB PIL Image，原始图像
            mask: PIL Image (L mode 或 RGBA mode)
                  - L mode: 255=待修复区域, 0=保留区域
                  - RGBA mode: alpha=255=待修复区域, alpha=0=保留区域
                  内部会自动转换为 L mode

        Returns:
            PIL Image (RGB)，修复后的图像

        Note:
            LaMa 是盲修复模型，prompt 参数会保留但不影响修复结果。
            模型会自动根据 mask 区域的内容和周围上下文进行修复。
        """
        if self._model is None:
            raise RuntimeError("LaMa model not loaded. Call load() first.")

        if isinstance(image, Image.Image):
            # 确保 RGB 模式
            if image.mode == "RGBA":
                rgb = Image.new("RGB", image.size, (255, 255, 255))
                rgb.paste(image, mask=image.split()[3])
                image = rgb
            elif image.mode != "RGB":
                image = image.convert("RGB")
        else:
            image = Image.fromarray(image).convert("RGB")

        if isinstance(mask, Image.Image):
            # 支持 RGBA mask (使用 alpha 通道) 或 L mode mask
            if mask.mode == "RGBA":
                mask = mask.split()[3]
            elif mask.mode != "L":
                mask = mask.convert("L")
        else:
            mask = Image.fromarray(mask).convert("L")

        # simple-lama-inpainting 期望 mask 中 255 表示待修复区域
        result = self._model(image, mask)

        return result

    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._model is not None


# Singleton instance
_lama_model: Optional[LaMaModel] = None


def get_lama_model(device: str = "cuda") -> LaMaModel:
    """Get or create singleton LaMa model instance."""
    global _lama_model
    if _lama_model is None:
        _lama_model = LaMaModel(device=device)
        _lama_model.load()
    return _lama_model
