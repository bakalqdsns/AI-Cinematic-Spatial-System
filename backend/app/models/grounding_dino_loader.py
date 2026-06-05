"""
Grounding DINO Loader.

We use it to get initial detections, then pass boxes to SAM2 for masks.
"""
import os
import torch
import numpy as np
from PIL import Image
from typing import Union, Optional
from dataclasses import dataclass

try:
    from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
except ImportError:
    raise ImportError("Please install transformers: pip install transformers")


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
        self.device = torch.device(device if torch.cuda.is_available() else "cpu")
        self._processor = None
        self._model = None

    def load(self):
        """Load model, first from local cache then with download fallback."""
        print(f"[GroundingDINO] Loading {self.model_name} on {self.device}...")
        local_only = os.environ.get("AICSS_OFFLINE_ONLY", "").lower() in ("1", "true", "yes")

        for local_only_flag in ([True, False] if not local_only else [True]):
            try:
                self._processor = AutoProcessor.from_pretrained(
                    self.model_name,
                    trust_remote_code=True,
                    local_files_only=local_only_flag,
                )
                self._model = AutoModelForZeroShotObjectDetection.from_pretrained(
                    self.model_name,
                    trust_remote_code=True,
                    local_files_only=local_only_flag,
                )
                self._model.to(self.device)
                self._model.eval()
                mode = "local cache" if local_only_flag else "downloaded"
                print(f"[GroundingDINO] Loaded ({mode}).")
                return
            except FileNotFoundError:
                if local_only_flag:
                    raise RuntimeError(
                        f"Grounding DINO model '{self.model_name}' not found in local cache. "
                        f"Run 'huggingface-cli download {self.model_name}' to cache it, "
                        f"or unset AICSS_OFFLINE_ONLY to allow download."
                    )
                # First attempt was online and failed; retry offline to use cache
                continue
        raise RuntimeError(f"Failed to load Grounding DINO model '{self.model_name}'.")

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

        # Normalize prompt for Grounding DINO format
        text_prompt = prompt.strip()
        if not text_prompt.endswith("."):
            text_prompt += "."

        # Hard cap: Grounding DINO base supports max 256 text tokens internally.
        # If the prompt is longer, truncate to the first ~200 tokens so there is
        # room for the BOS/EOS special tokens the tokenizer adds.
        _MAX_TEXT_TOKENS = 200
        text_inputs = self._processor.tokenizer(
            text_prompt,
            return_tensors="pt",
            truncation=True,
            max_length=_MAX_TEXT_TOKENS,
            add_special_tokens=False,
        )
        token_count = int(text_inputs["input_ids"].shape[1])
        if token_count >= _MAX_TEXT_TOKENS:
            print(f"[GroundingDINO] Prompt truncated to {token_count} tokens (max {_MAX_TEXT_TOKENS})")
            text_prompt = self._processor.tokenizer.decode(
                text_inputs["input_ids"][0], skip_special_tokens=True
            )

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
        for score, label, box in zip(
            results["scores"],
            results["labels"],
            results["boxes"],
        ):
            # box is [x1, y1, x2, y2] in pixel coords
            x1, y1, x2, y2 = box
            # Clip to image bounds
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            if x2 <= x1 or y2 <= y1:
                continue

            detections.append(Detection(
                box=np.array([x1, y1, x2, y2]),
                label=label.lower().strip(),
                score=float(score),
                object_id=f"obj_{label.lower().strip()}_{len(detections)}",
            ))

        return detections
