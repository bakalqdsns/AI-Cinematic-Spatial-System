"""
LaMa (Large Mask Inpainting) Model Loader.

使用 simple-lama-inpainting 包加载本地 LaMa 模型进行图像修复。
LaMa 是 WACV 2022 论文 "Resolution-robust Large Mask Inpainting with Fourier Convolutions" 的实现。

参考: https://github.com/advimman/lama
pip: simple-lama-inpainting

启动时自动检测 big-lama.pt 是否存在；不存在则从 GitHub releases 自动下载。
"""

import glob
import os
import shutil
from typing import Optional

import numpy as np
import torch
from PIL import Image


# Source checkpoint — same URL simple_lama_inpainting uses internally
# (https://github.com/enesmsahin/simple-lama-inpainting/releases/download/v0.1.0/big-lama.pt).
DEFAULT_LAMA_URL = (
    "https://github.com/enesmsahin/simple-lama-inpainting/releases/download/"
    "v0.1.0/big-lama.pt"
)
LAMA_FILENAME = "big-lama.pt"


class LaMaModel:
    """
    LaMa 图像修复模型。

    支持 CPU/GPU 自动切换；启动时自动检测并下载权重（如果未缓存）。

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
        os.makedirs(self.checkpoint_dir, exist_ok=True)
        self._model = None

    # ── Cache discovery ────────────────────────────────────────────────────────

    def _local_checkpoint(self) -> Optional[str]:
        """Return a path to a cached big-lama.pt if one exists, else None.

        Searches (in order):
          1. <checkpoint_dir>/big-lama.pt       (project-local cache)
          2. ~/.cache/lama/big-lama.pt          (simple_lama_inpainting default)
          3. glob in either dir for big-lama*.pt (handles nested hash subdirs)
        """
        candidates = [
            os.path.join(self.checkpoint_dir, LAMA_FILENAME),
            os.path.join(os.path.expanduser("~"), ".cache", "lama", LAMA_FILENAME),
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        for root in [self.checkpoint_dir, os.path.join(os.path.expanduser("~"), ".cache", "lama")]:
            matches = glob.glob(os.path.join(root, "**", f"{LAMA_FILENAME}*"), recursive=True)
            if matches:
                return matches[0]
        return None

    def ensure_downloaded(self) -> str:
        """Ensure the LaMa checkpoint is on disk; downloads via simple_lama_inpainting's helper if missing.

        Returns the absolute path to the cached checkpoint.
        """
        cached = self._local_checkpoint()
        if cached:
            print(f"[LaMa] Found cached checkpoint: {cached}")
            return cached

        print(f"[LaMa] No cached checkpoint — downloading {DEFAULT_LAMA_URL}")

        # simple_lama_inpainting's own download_model uses urllib with no timeout.
        # Replace it with a direct requests-based download that has a configurable
        # timeout and automatic retries for transient errors.
        timeout_s = int(os.environ.get("LAMA_DOWNLOAD_TIMEOUT", "600"))
        max_retries = int(os.environ.get("LAMA_DOWNLOAD_RETRIES", "3"))
        import time as _time
        import requests as _requests

        for attempt in range(1, max_retries + 1):
            if attempt > 1:
                print(f"[LaMa] Retry {attempt}/{max_retries} ...")
                _time.sleep(2 ** attempt)  # exponential back-off
            try:
                print(f"[LaMa] Downloading (timeout={timeout_s}s, attempt={attempt}) ...")
                resp = _requests.get(DEFAULT_LAMA_URL, timeout=timeout_s, stream=True)
                resp.raise_for_status()
                downloaded_path = os.path.join(self.checkpoint_dir, LAMA_FILENAME + ".part")
                with open(downloaded_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                os.replace(downloaded_path, os.path.join(self.checkpoint_dir, LAMA_FILENAME))
                print(f"[LaMa] Downloaded: {os.path.join(self.checkpoint_dir, LAMA_FILENAME)}")
                return os.path.join(self.checkpoint_dir, LAMA_FILENAME)
            except Exception as exc:
                print(f"[LaMa] Attempt {attempt} failed: {type(exc).__name__}: {exc}")
                if attempt == max_retries:
                    raise RuntimeError(
                        f"LaMa checkpoint download failed after {max_retries} attempts "
                        f"for {DEFAULT_LAMA_URL}. Check network / proxy."
                    ) from exc

        # Mirror to our project-local cache so the file lives alongside the
        # rest of AICSS model weights. Best-effort: if the copy fails we just
        # fall back to the path simple_lama_inpainting returned.
        mirror = os.path.join(self.checkpoint_dir, LAMA_FILENAME)
        downloaded_path = os.path.join(self.checkpoint_dir, LAMA_FILENAME)
        if os.path.abspath(downloaded_path) != os.path.abspath(mirror):
            try:
                tmp = mirror + ".part"
                shutil.copy2(downloaded_path, tmp)
                os.replace(tmp, mirror)
                print(f"[LaMa] Mirrored checkpoint to {mirror}")
                return mirror
            except Exception as e:
                print(f"[LaMa] WARNING: mirror to {mirror} failed ({e}); using {downloaded_path}")
        return downloaded_path

    def load(self):
        """Load LaMa model. Auto-downloads checkpoint on first run if missing."""
        print(f"[LaMa] Loading LaMa on {self.device}...")

        try:
            from simple_lama_inpainting import SimpleLama
        except ImportError:
            raise ImportError(
                "simple-lama-inpainting not installed. "
                "Install with: pip install simple-lama-inpainting"
            )

        # Make sure the checkpoint is local (download if not), then point
        # SimpleLama at it via the LAMA_MODEL env var so it skips its own
        # internal downloader.
        ckpt = self.ensure_downloaded()
        os.environ["LAMA_MODEL"] = ckpt
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
