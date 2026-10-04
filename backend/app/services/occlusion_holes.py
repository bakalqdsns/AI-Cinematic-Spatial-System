"""
自动遮挡空洞检测 —— 从物体 mask / 深度关系生成可喂给 LaMa 的 inpaint mask。

Mask 语义（与 inpaint_utils / 前端约定一致）：
  - 白色 (255) = 待补全（空洞）
  - 黑色 (0)   = 保留

两种模式：
  - peel：空洞 = 目标物体完整 mask（与 Strip / computeSimpleMask 对齐）
  - occluded_interior：空洞 = 目标 mask ∩ 更近遮挡物 mask（仅重叠被挡区）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

import numpy as np
from PIL import Image

from app.utils.image_utils import base64_to_pil, pil_to_base64

OcclusionMode = Literal["peel", "occluded_interior"]


@dataclass
class OcclusionHole:
    object_id: str
    mask_data_url: str
    polygon: list[list[float]] = field(default_factory=list)
    white_ratio: float = 0.0
    occluder_ids: list[str] = field(default_factory=list)
    mode: str = "peel"


def _mask_from_object(obj: dict, size: tuple[int, int]) -> np.ndarray:
    """Decode object maskDataUrl → binary HxW uint8 (0/255). Falls back to empty."""
    w, h = size
    url = obj.get("maskDataUrl") or obj.get("mask_data_url") or ""
    if not url:
        return np.zeros((h, w), dtype=np.uint8)
    try:
        img = base64_to_pil(url, keep_alpha=True)
        if img.size != (w, h):
            img = img.resize((w, h), Image.NEAREST)
        if img.mode == "RGBA":
            arr = np.array(img.split()[3])
        elif img.mode == "L":
            arr = np.array(img)
        else:
            arr = np.array(img.convert("L"))
        return np.where(arr > 127, 255, 0).astype(np.uint8)
    except Exception:
        return np.zeros((h, w), dtype=np.uint8)


def _object_depth(obj: dict) -> float:
    raw = obj.get("depth")
    if raw is None:
        raw = obj.get("depthValue")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 9999.0


def _white_ratio(mask: np.ndarray) -> float:
    if mask.size == 0:
        return 0.0
    return float(np.count_nonzero(mask) / mask.size)


def _mask_to_rgba_data_url(mask: np.ndarray) -> str:
    """Binary HxW → RGBA PNG data URL (white opaque = hole, black transparent = keep)."""
    h, w = mask.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[..., 0:3] = 255
    rgba[..., 3] = mask  # alpha carries hole
    return pil_to_base64(Image.fromarray(rgba, mode="RGBA"))


def _polygon_of(obj: dict) -> list[list[float]]:
    poly = obj.get("polygon") or []
    if not isinstance(poly, list):
        return []
    out: list[list[float]] = []
    for p in poly:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            try:
                out.append([float(p[0]), float(p[1])])
            except (TypeError, ValueError):
                continue
    return out


def compute_occlusion_holes(
    objects: list[dict],
    *,
    image_width: int,
    image_height: int,
    target_object_ids: Optional[list[str]] = None,
    mode: OcclusionMode = "peel",
) -> list[OcclusionHole]:
    """
    为指定（或全部）物体生成 inpaint 空洞 mask。

    peel:
      hole = object mask
    occluded_interior:
      hole = object mask ∩ union(masks of objects with smaller depth = closer)
      若无更近遮挡物，回退为 peel（保证非空，可喂 LaMa）。
    """
    if image_width <= 0 or image_height <= 0:
        raise ValueError("image_width and image_height must be positive")
    if not objects:
        return []

    size = (image_width, image_height)
    id_set = set(target_object_ids) if target_object_ids else None

    # Precompute masks for all objects (needed for occluder union).
    masks: dict[str, np.ndarray] = {}
    depths: dict[str, float] = {}
    for obj in objects:
        oid = str(obj.get("id") or obj.get("objectId") or "")
        if not oid:
            continue
        masks[oid] = _mask_from_object(obj, size)
        depths[oid] = _object_depth(obj)

    holes: list[OcclusionHole] = []
    for obj in objects:
        oid = str(obj.get("id") or obj.get("objectId") or "")
        if not oid:
            continue
        if id_set is not None and oid not in id_set:
            continue

        target = masks.get(oid)
        if target is None:
            continue

        occluder_ids: list[str] = []
        if mode == "occluded_interior":
            target_depth = depths[oid]
            closer = np.zeros_like(target)
            for other_id, other_mask in masks.items():
                if other_id == oid:
                    continue
                # Smaller depth meters = closer to camera = occluder
                if depths[other_id] < target_depth - 1e-6:
                    closer = np.maximum(closer, other_mask)
                    if np.any(other_mask & target):
                        occluder_ids.append(other_id)
            hole = np.where((target > 0) & (closer > 0), 255, 0).astype(np.uint8)
            used_mode: str = "occluded_interior"
            # Fallback: empty intersection → peel so LaMa gets a usable mask
            if not np.any(hole):
                hole = target.copy()
                used_mode = "peel"
                occluder_ids = []
        else:
            hole = target.copy()
            used_mode = "peel"

        if not np.any(hole):
            continue

        holes.append(
            OcclusionHole(
                object_id=oid,
                mask_data_url=_mask_to_rgba_data_url(hole),
                polygon=_polygon_of(obj),
                white_ratio=round(_white_ratio(hole), 6),
                occluder_ids=occluder_ids,
                mode=used_mode,
            )
        )

    return holes


def merge_hole_masks(holes: list[OcclusionHole], size: tuple[int, int]) -> Optional[str]:
    """Union multiple hole masks into one RGBA data URL (for layer peel)."""
    if not holes:
        return None
    w, h = size
    merged = np.zeros((h, w), dtype=np.uint8)
    for hole in holes:
        m = _mask_from_object({"maskDataUrl": hole.mask_data_url}, size)
        merged = np.maximum(merged, m)
    if not np.any(merged):
        return None
    return _mask_to_rgba_data_url(merged)


def holes_to_dicts(holes: list[OcclusionHole]) -> list[dict[str, Any]]:
    return [
        {
            "objectId": h.object_id,
            "maskDataUrl": h.mask_data_url,
            "polygon": h.polygon,
            "whiteRatio": h.white_ratio,
            "occluderIds": h.occluder_ids,
            "mode": h.mode,
        }
        for h in holes
    ]
