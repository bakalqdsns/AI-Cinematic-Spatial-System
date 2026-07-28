"""
Grounding DINO Loader.

Grounding DINO performs open-set object detection — given a text prompt
and an image, it returns bounding boxes for matching objects.

We use it to get initial detections, then pass boxes to SAM2 for masks.
"""
import torch
import numpy as np
from PIL import Image
from typing import Union, Optional
from dataclasses import dataclass

try:
    from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
except ImportError:
    raise ImportError("Please install transformers: pip install transformers")

from app.config import settings
from app.models.hf_compat import auth_kwargs


def _snapshot_download_hf(model_name: str) -> str:
    """Download a HuggingFace model via snapshot_download and return the snapshot dir."""
    import os as _os
    _os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "600")
    _os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    _os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

    from huggingface_hub import snapshot_download
    token_kwargs = auth_kwargs(settings.hf_token)
    cache_dir = str(settings.grounding_dino_checkpoint_dir)
    local_dir = snapshot_download(
        repo_id=model_name,
        cache_dir=cache_dir,
        **token_kwargs,
    )
    return local_dir


@dataclass
class Detection:
    box: np.ndarray  # [x1, y1, x2, y2] in pixels
    label: str
    score: float
    object_id: str


class GroundingDinoModel:
    """
    Grounding DINO zero-shot object detector.

    Usage:
        model = GroundingDinoModel("IDEA-Research/grounding-dino-base", device="cuda")
        model.load()
        detections = model.detect(image, prompt="person,car,building")
    """

    def __init__(
        self,
        model_name: str = "IDEA-Research/grounding-dino-base",
        device: str = "cuda",
    ):
        self.model_name = model_name
        _effective = device if torch.cuda.is_available() else "cpu"
        self.device = torch.device(_effective)
        if _effective != device:
            print(f"[GroundingDINO] CUDA unavailable — fell back to CPU (requested: {device})")
        self._processor = None
        self._model = None

    def ensure_downloaded(self) -> str:
        """
        Ensure the Grounding DINO checkpoint is on disk.  Returns the snapshot
        directory path for ``from_pretrained`` with ``local_files_only=True``.
        """
        print(f"[GroundingDINO] Ensuring {self.model_name} is on disk ...")
        path = _snapshot_download_hf(self.model_name)
        print(f"[GroundingDINO] Snapshot ready: {path}")
        return path

    def load(self):
        """Load model. Tries online download first, falls back to local cache."""
        print(f"[GroundingDINO] Loading {self.model_name} on {self.device}...")
        token_kwargs = auth_kwargs(settings.hf_token)
        loaded = False

        for phase, local_only in enumerate(["online (auto-download)", "local cache"], 1):
            try:
                print(f"[GroundingDINO]   phase {phase}: {local_only}...")
                self._processor = AutoProcessor.from_pretrained(
                    self.model_name,
                    trust_remote_code=True,
                    local_files_only=local_only,
                    **token_kwargs,
                )
                self._model = AutoModelForZeroShotObjectDetection.from_pretrained(
                    self.model_name,
                    trust_remote_code=True,
                    local_files_only=local_only,
                    **token_kwargs,
                )
                self._model.to(self.device)
                self._model.eval()
                print(f"[GroundingDINO]   ✓ loaded from {local_only}")
                loaded = True
                break
            except FileNotFoundError:
                print(f"[GroundingDINO]   ✗ not found in {local_only}, trying next...")
                self._processor = None
                self._model = None
                continue

        if not loaded:
            raise FileNotFoundError(
                f"Grounding DINO '{self.model_name}' not found locally and could not be "
                f"downloaded. Check network / HF_TOKEN / proxy settings."
            )
        print("[GroundingDINO] Loaded.")

    def detect(
        self,
        image: Union[Image.Image, np.ndarray],
        prompt: str,
        threshold: float = 0.3,
    ) -> list[Detection]:
        """
        Detect objects matching the text prompt.

        Args:
            image: RGB PIL Image or numpy array
            prompt: comma-separated class names, e.g. "person,car,lamp"
            threshold: confidence threshold

        Returns:
            List of Detection objects with bounding boxes and labels
        """
        if self._model is None:
            raise RuntimeError("Model not loaded. Call load() first.")

        if isinstance(image, np.ndarray):
            image = Image.fromarray(image.astype(np.uint8))

        # Ensure RGB (RGBA images from frontend cause
        # "Unable to infer channel dimension format" in transformers >= 4.51)
        if image.mode != 'RGB':
            image = image.convert('RGB')

        # Normalize prompt for Grounding DINO format
        text_prompt = prompt.strip()
        if not text_prompt.endswith("."):
            text_prompt += "."

        inputs = self._processor(
            text=text_prompt,
            images=image,
            return_tensors="pt",
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self._model(**inputs)

        results = self._processor.post_process_grounded_object_detection(
            outputs,
            threshold=threshold,
            text_threshold=threshold,
            target_sizes=[(image.height, image.width)],
        )[0]

        w, h = image.size
        detections = []
        # scores/boxes are GPU tensors — move to CPU before Python iteration.
        # labels may be strings (old transformers <4.51) or tensor-of-ints (new >=4.51).
        # For v4.51+, transformers changed `labels` to return integer IDs and added
        # `text_labels` for string names. We prefer `text_labels` when available.
        scores = results["scores"].cpu()
        boxes = results["boxes"].cpu()
        raw_labels = results.get("text_labels", results.get("labels"))
        if hasattr(raw_labels, "cpu"):
            raw_labels = raw_labels.cpu()
        if hasattr(raw_labels, "tolist"):
            raw_labels = raw_labels.tolist()
        labels = raw_labels

        for score, label, box in zip(scores, labels, boxes):
            # box is [x1, y1, x2, y2] in pixel coords
            x1, y1, x2, y2 = box
            # Clip to image bounds
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            if x2 <= x1 or y2 <= y1:
                continue

            label_str = label.lower().strip() if isinstance(label, str) else str(label).lower().strip()
            detections.append(Detection(
                box=np.array([x1, y1, x2, y2]),
                label=label_str,
                score=float(score),
                object_id=f"obj_{label_str}_{len(detections)}",
            ))

        return detections
