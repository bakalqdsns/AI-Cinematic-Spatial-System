"""
Grounding DINO Loader.

Grounding DINO performs open-set object detection — given a text prompt
and an image, it returns bounding boxes for matching objects.

We use it to get initial detections, then pass boxes to SAM2 for masks.
"""
import torch
import numpy as np
from PIL import Image
from pathlib import Path
from typing import Union, Optional
from dataclasses import dataclass

try:
    from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
except ImportError:
    raise ImportError("Please install transformers: pip install transformers")

from app.config import settings
from app.models.hf_compat import auth_kwargs


def _snapshot_download_hf(model_name: str, progress_key: str | None = None) -> str:
    """Download a HuggingFace model via snapshot_download and return the snapshot dir."""
    import os as _os
    _os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "600")
    _os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    _os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

    from huggingface_hub import snapshot_download
    token_kwargs = auth_kwargs(settings.hf_token)
    cache_dir = str(settings.grounding_dino_checkpoint_dir)
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

    def ensure_downloaded(self, progress_key: str | None = None) -> str:
        """
        Ensure the Grounding DINO checkpoint is on disk.  Returns the snapshot
        directory path for ``from_pretrained`` with ``local_files_only=True``.

        progress_key: when supplied, progress is reported to the
                      download-jobs registry under this key.
        """
        print(f"[GroundingDINO] Ensuring {self.model_name} is on disk ...")
        path = _snapshot_download_hf(self.model_name, progress_key=progress_key)
        print(f"[GroundingDINO] Snapshot ready: {path}")
        return path

    def load(self):
        """Load model. Tries online download first, falls back to local cache."""
        print(f"[GroundingDINO] Loading {self.model_name} on {self.device}...")
        token_kwargs = auth_kwargs(settings.hf_token)
        loaded = False

        # Resolve the snapshot directory up-front so we can pass an absolute
        # path to ``from_pretrained``. This sidesteps the case where the
        # ``cached_file`` machinery inside transformers tries to re-download
        # ``config.json`` / ``preprocessor_config.json`` even when the files
        # are clearly on disk (network calls hang for HF_HUB_DOWNLOAD_TIMEOUT
        # seconds before giving up).
        import os as _os
        snapshot_dir = None
        for candidate in (
            _os.environ.get("HF_HUB_CACHE"),
            str(Path(_os.environ.get("HF_HOME", "")) / "hub") if _os.environ.get("HF_HOME") else None,
        ):
            if not candidate:
                continue
            base = Path(candidate) / f"models--{self.model_name.replace('/', '--')}"
            if not base.is_dir():
                continue
            for snap_dir in (base / "snapshots").glob("*"):
                if snap_dir.is_dir() and (snap_dir / "config.json").is_file():
                    snapshot_dir = str(snap_dir)
                    break
            if snapshot_dir:
                break
        forced_offline = _os.environ.get("HF_HUB_OFFLINE") == "1"
        if forced_offline and snapshot_dir is None:
            print("[GroundingDINO] HF_HUB_OFFLINE=1 but no local snapshot found; falling back to repo name")
            forced_offline = False

        # When offline mode is on AND we have a local snapshot, pass the
        # snapshot path directly so ``from_pretrained`` doesn't have to
        # resolve the cache again. Otherwise behave as before.
        load_target = snapshot_dir if (forced_offline and snapshot_dir) else self.model_name
        phase_list = (
            ["local cache"] if forced_offline
            else ["online (auto-download)", "local cache"]
        )
        for phase, local_only in enumerate(phase_list, 1):
            try:
                print(f"[GroundingDINO]   phase {phase}: {local_only} (target={load_target})...")
                self._processor = AutoProcessor.from_pretrained(
                    load_target,
                    trust_remote_code=True,
                    local_files_only=local_only,
                    **token_kwargs,
                )
                self._model = AutoModelForZeroShotObjectDetection.from_pretrained(
                    load_target,
                    trust_remote_code=True,
                    local_files_only=local_only,
                    **token_kwargs,
                )
                self._model.to(self.device)
                self._model.eval()
                print(f"[GroundingDINO]   ✓ loaded from {local_only}")
                loaded = True
                break
            except (FileNotFoundError, OSError) as _load_err:
                print(f"[GroundingDINO]   ✗ failed in {local_only}: {type(_load_err).__name__}: {_load_err}")
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
                # Some detectors echo the class name twice when the same word
                # appears more than once in the prompt — collapse to a single
                # token so ``object_id`` stays unique and filesystem-safe.
                object_id=f"obj_{(label_str.split()[-1] if label_str else 'obj')}_{len(detections)}",
            ))

        return detections
