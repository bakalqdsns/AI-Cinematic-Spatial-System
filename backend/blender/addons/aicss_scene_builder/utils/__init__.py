"""Utility helpers package (Phase 1.2)."""
from .scene_utils import (
    Z_OFFSETS,
    LAYER_ORDER,
    DEFAULT_SCENE_WIDTH,
    DEFAULT_SCENE_HEIGHT,
    DEFAULT_CAMERA_FOV,
    read_manifest,
    normalize_manifest,
    layer_z_offset,
)

__all__ = (
    "Z_OFFSETS",
    "LAYER_ORDER",
    "DEFAULT_SCENE_WIDTH",
    "DEFAULT_SCENE_HEIGHT",
    "DEFAULT_CAMERA_FOV",
    "read_manifest",
    "normalize_manifest",
    "layer_z_offset",
)