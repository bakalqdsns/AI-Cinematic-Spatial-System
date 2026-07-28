"""
Qwen3-VL Loader.

Qwen3-VL-4B-Instruct is a vision-language model from Alibaba.
We use it locally as a replacement for the DashScope remote VLM API,
providing scene classification and object detection prompts for Grounding DINO.

Usage:
    model = Qwen3VLModel(model_name="Qwen/Qwen3-VL-4B-Instruct", device="cuda")
    model.load()
    text = model.chat(image, system_prompt, user_prompt)
"""
import torch
from PIL import Image
from typing import Union

from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

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
    cache_dir = str(settings.vlm_checkpoint_dir)
    local_dir = snapshot_download(
        repo_id=model_name,
        cache_dir=cache_dir,
        **token_kwargs,
    )
    return local_dir


class Qwen3VLModel:
    """
    Qwen3-VL-4B-Instruct via HuggingFace Transformers.

    本地优先：加载时使用 local_files_only=True，避免离线时触发 HuggingFace Hub 检查。
    与 DepthAnything / Grounding DINO loader 风格保持一致。
    """

    def __init__(
        self,
        model_name: str = "Qwen/Qwen3-VL-4B-Instruct",
        device: str = "cuda",
        max_new_tokens: int = 256,
    ):
        self.model_name = model_name
        _effective = device if torch.cuda.is_available() else "cpu"
        self.device = torch.device(_effective)
        if _effective != device:
            print(f"[Qwen3VL] CUDA unavailable — fell back to CPU (requested: {device})")
        self.max_new_tokens = max_new_tokens
        self._processor = None
        self._model = None

    def ensure_downloaded(self) -> str:
        """
        Ensure the Qwen3-VL checkpoint is on disk.  Returns the snapshot
        directory path for ``from_pretrained`` with ``local_files_only=True``.
        """
        print(f"[Qwen3VL] Ensuring {self.model_name} is on disk ...")
        path = _snapshot_download_hf(self.model_name)
        print(f"[Qwen3VL] Snapshot ready: {path}")
        return path

    def load(self):
        """Load processor and model. Tries online download first, falls back to local cache."""
        print(f"[Qwen3VL] Loading {self.model_name} on {self.device}...")
        token_kwargs = auth_kwargs(settings.hf_token)
        loaded = False

        for phase, local_only in enumerate(["online (auto-download)", "local cache"], 1):
            try:
                print(f"[Qwen3VL]   phase {phase}: {local_only}...")
                self._processor = AutoProcessor.from_pretrained(
                    self.model_name,
                    local_files_only=local_only,
                    **token_kwargs,
                )
                self._model = Qwen3VLForConditionalGeneration.from_pretrained(
                    self.model_name,
                    dtype=torch.bfloat16,
                    local_files_only=local_only,
                    **token_kwargs,
                ).to(self.device).eval()
                print(f"[Qwen3VL]   ✓ loaded from {local_only}")
                loaded = True
                break
            except FileNotFoundError:
                print(f"[Qwen3VL]   ✗ not found in {local_only}, trying next...")
                self._processor = None
                self._model = None
                continue

        if not loaded:
            raise FileNotFoundError(
                f"Qwen3-VL '{self.model_name}' not found locally and could not be "
                f"downloaded. Check network / HF_TOKEN / proxy settings."
            )
        print("[Qwen3VL] Loaded.")

    @torch.no_grad()
    def chat(
        self,
        image: Union[Image.Image, str],
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """
        Single-turn chat with the vision-language model.

        Args:
            image: PIL Image (RGB preferred) or a local file path / URL string
            system_prompt: system role instruction
            user_prompt: user role text instruction

        Returns:
            The model's text completion (decoded, with special tokens stripped).
        """
        if self._model is None or self._processor is None:
            raise RuntimeError("Qwen3-VL model not loaded. Call load() first.")

        if isinstance(image, str):
            image = Image.open(image).convert("RGB")
        elif isinstance(image, Image.Image) and image.mode != "RGB":
            image = image.convert("RGB")

        messages = [
            {
                "role": "system",
                "content": [{"type": "text", "text": system_prompt}],
            },
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": user_prompt},
                ],
            },
        ]

        inputs = self._processor.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
        )
        inputs = inputs.to(self.device)

        generated_ids = self._model.generate(
            **inputs,
            max_new_tokens=self.max_new_tokens,
            do_sample=False,
        )
        generated_ids_trimmed = [
            out_ids[len(in_ids):]
            for in_ids, out_ids in zip(inputs["input_ids"], generated_ids)
        ]
        output_text = self._processor.batch_decode(
            generated_ids_trimmed,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )
        # batch_decode returns a list — flatten to first element
        return output_text[0] if output_text else ""