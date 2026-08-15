"""
Image Generator Interface — abstracts image generation so callers can swap
implementations (local Z-Image / SDXL / cloud) without leaking concrete types.

Phase 1 architecture deliverable (Implementation Plan §1.4.3). This module:

  1. Defines `ImageGeneratorInterface` as a typing.Protocol so existing
     `LocalImageGenerator` is structurally compatible (no inheritance required).
  2. Provides `RLockImageGenerator` — a thread-safe wrapper that prevents
     `configure()` from running while a `generate()` call is in flight (the
     race condition flagged in `PROJECT_STATUS.md` §四.代码级耦合问题详解).
  3. Re-exports `get_image_generator()` / `configure_image_generator()` so
     existing callers don't need to change.

The interface intentionally does NOT change the public API of
`image_generator.py` — it's additive: existing module-level singletons
(`_img_gen`, `get_image_generator`, `configure_image_generator`) keep working,
and new callers can opt in by importing the interface or wrapper.

Design note on locking:
    The wrapper uses TWO primitives to avoid the classic "RLock deadlock"
    pattern (a method acquires the lock, then waits for a condition that
    can only be cleared by a different thread also acquiring the lock):

      * `_gate` (threading.Lock) — held by an in-flight generation. Only the
        generation thread holds it; `configure()`/`unload()` `acquire(blocking=True)`
        it, which blocks them until the generation releases it in `finally`.

      * `_generating` (int) — depth counter, mutated under `_gate` only.
        Allows re-entrant generate() calls without breaking.

    This avoids busy-spinning and is provably deadlock-free (only one
    direction of lock acquisition: generation acquires first, configure
    waits for it to release).
"""
from __future__ import annotations

import logging
import threading
from typing import Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class ImageGeneratorInterface(Protocol):
    """Structural interface every image generator must satisfy.

    The Protocol is decorated with ``@runtime_checkable`` so callers can
    do ``isinstance(generator, ImageGeneratorInterface)`` at runtime if
    they need to confirm a candidate object exposes the contract.
    """

    model_id: str
    dtype_name: str

    def generate(self, prompt: str, **kwargs) -> Optional["Image.Image"]:
        """Text-to-image generation. Returns a PIL.Image or None on failure."""
        ...

    def generate_with_image(
        self, prompt: str, reference_image: "Image.Image", **kwargs
    ) -> Optional["Image.Image"]:
        """Image-to-image generation guided by a reference image."""
        ...

    def generate_inpaint(
        self,
        prompt: str,
        reference_image: "Image.Image",
        mask_image: "Image.Image",
        **kwargs,
    ) -> Optional["Image.Image"]:
        """Inpainting. Some pipelines (Z-Image) may not support this and
        should return None — the caller is expected to fall back to LaMa."""
        ...

    def configure(self, model_id: str, dtype_name: str) -> None:
        """Hot-reload the underlying model. MUST NOT be called while a
        generate() call is in flight — use ``RLockImageGenerator`` if your
        deployment can race here."""
        ...

    def unload(self) -> None:
        """Release GPU memory. Idempotent — calling twice is a no-op."""
        ...

    def is_loaded(self) -> bool:
        """True iff the pipeline is currently resident in GPU memory."""
        ...


class RLockImageGenerator:
    """
    Thread-safe wrapper around an `ImageGeneratorInterface`.

    Serialises ``generate()`` / ``generate_with_image()`` / ``generate_inpaint()``
    so two concurrent generations don't fight for the same Diffusers pipeline
    (Diffusers pipelines are NOT safe for concurrent calls). Also blocks
    ``configure()`` and ``unload()`` while a generation is in flight, fixing
    the race condition the original ``configure_image_generator()`` exposed.

    The wrapper preserves the underlying object's attributes (model_id,
    dtype_name) by delegating to ``__getattr__`` so callers that read these
    fields see the live values from the wrapped generator.
    """

    def __init__(self, wrapped: ImageGeneratorInterface):
        self._wrapped = wrapped
        # Plain Lock: generation acquires it; configure/unload acquire it to wait.
        # No re-entrant acquire happens — generation releases it in finally.
        self._gate = threading.Lock()
        self._generating = 0  # depth counter for diagnostics; only mutated under _gate

    # ── Attribute delegation ────────────────────────────────────────────────

    def __getattr__(self, name: str):
        # __getattr__ is only called for attributes not found on self, so the
        # attributes we set on self (_wrapped, _gate, _generating) are safe.
        # Everything else delegates to the wrapped generator so callers can
        # still read ``wrapper.model_id`` etc.
        return getattr(self._wrapped, name)

    # ── Generation (gate-protected) ──────────────────────────────────────

    def generate(self, prompt: str, **kwargs):
        self._gate.acquire()
        self._generating += 1
        try:
            return self._wrapped.generate(prompt, **kwargs)
        finally:
            self._generating -= 1
            self._gate.release()

    def generate_with_image(self, prompt: str, reference_image, **kwargs):
        self._gate.acquire()
        self._generating += 1
        try:
            return self._wrapped.generate_with_image(
                prompt, reference_image, **kwargs
            )
        finally:
            self._generating -= 1
            self._gate.release()

    def generate_inpaint(self, prompt: str, reference_image, mask_image, **kwargs):
        self._gate.acquire()
        self._generating += 1
        try:
            return self._wrapped.generate_inpaint(
                prompt, reference_image, mask_image, **kwargs
            )
        finally:
            self._generating -= 1
            self._gate.release()

    # ── Configure / unload (must wait for in-flight generations) ───────────

    def configure(self, model_id: str, dtype_name: str) -> None:
        # First, wait for any in-flight generation to complete. If a
        # generation is running, log a warning and block until it
        # releases _gate.
        if not self._gate.acquire(blocking=False):
            logger.warning(
                "[ImageGen] configure(%s, %s) is waiting for %d in-flight "
                "generation(s) to complete",
                model_id, dtype_name, self._generating,
            )
            self._gate.acquire()  # blocks until generation finishes
        try:
            self._wrapped.configure(model_id, dtype_name)
        finally:
            self._gate.release()

    def unload(self) -> None:
        if not self._gate.acquire(blocking=False):
            logger.warning(
                "[ImageGen] unload() is waiting for %d in-flight "
                "generation(s) to complete",
                self._generating,
            )
            self._gate.acquire()
        try:
            self._wrapped.unload()
        finally:
            self._gate.release()

    def is_loaded(self) -> bool:
        return self._wrapped.is_loaded()

    @property
    def wrapped(self) -> ImageGeneratorInterface:
        """Expose the underlying generator for advanced callers (e.g. tests)."""
        return self._wrapped

    @property
    def is_generating(self) -> bool:
        """True iff at least one generation is currently in flight.

        Diagnostic helper — useful for tests and for callers that want to
        warn the user before kicking off a configure that would block.
        """
        # _gate is uncontended so acquire+release is cheap.
        return self._generating > 0 and self._gate.acquire(blocking=False) is False


def wrap_with_rlock(generator: ImageGeneratorInterface) -> RLockImageGenerator:
    """Convenience — wrap an existing generator with RLock protection.

    Returns the input unchanged if it's already an ``RLockImageGenerator``
    (idempotent) so callers can call this defensively without double-wrapping.
    """
    if isinstance(generator, RLockImageGenerator):
        return generator
    return RLockImageGenerator(generator)