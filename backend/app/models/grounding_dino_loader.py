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
        """Load model from HuggingFace."""
        print(f"[GroundingDINO] Loading {self.model_name} on {self.device}...")
        self._processor = AutoProcessor.from_pretrained(
            self.model_name,
            trust_remote_code=True,
        )
        self._model = AutoModelForZeroShotObjectDetection.from_pretrained(
            self.model_name,
            trust_remote_code=True,
        )
        self._model.to(self.device)
        self._model.eval()
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
            inputs["input_ids"],
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
