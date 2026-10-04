"""
Depth Model Loader — Depth Anything V2 via HuggingFace Transformers.

本地优先：加载时使用 local_files_only=True，避免离线时触发 HuggingFace Hub 检查。
"""
import torch
import numpy as np
from PIL import Image
from typing import Union

from transformers import AutoImageProcessor, AutoModelForDepthEstimation

from app.config import settings, CACHE_DIR
from app.models.hf_compat import auth_kwargs


def _snapshot_download_hf(model_name: str, progress_key: str | None = None) -> str:
    """
    Download a HuggingFace model via snapshot_download (through hf-mirror.com)
    and return the local snapshot directory.  Raises on failure.

    progress_key: optional download-jobs registry key (e.g. "depth"). When
                  provided, the snapshot download feeds real-time progress to
                  the registry so the frontend can render a progress bar.
    """
    import os as _os
    _os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "600")
    _os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    _os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

    from huggingface_hub import snapshot_download
    token_kwargs = auth_kwargs(settings.hf_token)
    cache_dir = str(settings.depth_checkpoint_dir)

    tqdm_class = None
    if progress_key:
        from app.services.download_progress import make_tqdm_callback
        tqdm_class = make_tqdm_callback(progress_key)

    local_dir = snapshot_download(
        repo_id=model_name,
        cache_dir=cache_dir,
        tqdm_class=tqdm_class,
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

    def ensure_downloaded(self, progress_key: str | None = None) -> str:
        """
        Ensure the DepthAnything V2 checkpoint is on disk.  Returns the
        snapshot directory path that ``from_pretrained`` can use with
        ``local_files_only=True``.

        progress_key: when supplied, progress is reported to the
                      download-jobs registry under this key.
        """
        print(f"[DepthModel] Ensuring {self.model_name} is on disk ...")
        path = _snapshot_download_hf(self.model_name, progress_key=progress_key)
        print(f"[DepthModel] Snapshot ready: {path}")
        return path

    def load(self):
        """Load model and processor. Tries local cache first, then online download."""
        print(f"[DepthModel] Loading {self.model_name} on {self.device}...")
        token_kwargs = auth_kwargs(settings.hf_token)
        loaded = False

        # Phase 1: try local HuggingFace cache snapshot directly
        # snapshot_download uses the HF cache dir (not depth_checkpoint_dir).
        import os as _os
        _hf_cache = _os.path.join(str(CACHE_DIR), "huggingface", "hub")
        _repo_id = self.model_name.replace("/", "--")
        _repo_dir = _os.path.join(_hf_cache, f"models--{_repo_id}", "snapshots")
        print(f"[DepthModel]   phase 1: checking local HF cache: {_repo_dir}")
        if _os.path.isdir(_repo_dir):
            _found_snap = None
            for _snap_hash in _os.listdir(_repo_dir):
                _local_path = _os.path.join(_repo_dir, _snap_hash)
                if _os.path.isdir(_local_path) and _os.path.isfile(
                    _os.path.join(_local_path, "model.safetensors")
                ):
                    _found_snap = _local_path
                    break
            if _found_snap:
                try:
                    print(f"[DepthModel]   phase 1: loading from {_found_snap}...")
                    self._processor = AutoImageProcessor.from_pretrained(
                        _found_snap,
                        local_files_only=True,
                        **token_kwargs,
                    )
                    self._model = AutoModelForDepthEstimation.from_pretrained(
                        _found_snap,
                        local_files_only=True,
                        **token_kwargs,
                    )
                    self._model.to(self.device)
                    self._model.eval()
                    print(f"[DepthModel]   ✓ loaded from local snapshot")
                    loaded = True
                except Exception as e:
                    print(f"[DepthModel]   ✗ snapshot load failed: {e}")
                    self._processor = None
                    self._model = None
        if loaded:
            print("[DepthModel] Loaded.")
            return
        print("[DepthModel]   phase 1: no local snapshot found, falling back to from_pretrained...")

        # Phase 2: from_pretrained (online download if not cached)
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
