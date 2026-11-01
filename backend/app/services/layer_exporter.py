"""
Layer PNG Exporter — exports each depth layer (foreground/midground/background/sky/ground)
as an independent RGBA PNG with the layer's visible region preserved and everything
else transparent.

Phase 1 deliverable: `POST /api/aicss/layers/export` endpoint, plus a helper that
scene generators can call directly to embed `layeredImages` in the scene manifest.

Per the Implementation Plan (2026-08-10), this is the P0 blocker for the Blender
plugin (Module 6) — the layer PNGs this function produces are what the Blender plugin
imports and places at the canonical Z-axis offsets (sky=-20, background=-12,
midground=-8, ground=-4, foreground=-2).

场景归层（物件 → 场景类 → 匹配表 + 深度中位数）
------------------------------------------------
已检测物件先按场景类匹配表进入 sky / background / midground / foreground / ground。
表里没有的物件，用深度均值去贴已经归好的各层深度中位数，不再把未知标签全部丢进前景。
物件 mask 以外的剩余像素也按这个距离归层，不再用全图 P10/P50/P85 切成横条。
天空只有该场景允许天空、像素在上半幅、并且比已归背景更远时才进 sky。
重叠时更近的语义层拿走可见像素：foreground 近于 ground，ground 近于 midground，
midground 近于 background，background 近于 sky。

没有传入场景类、也没有物件时，仍保留旧的固定深度区间，方便无锚点的旧调用。
归档路径会传入场景类，走上面的新规则。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

import numpy as np
from PIL import Image, ImageFilter

from app.config import settings

logger = logging.getLogger("aicss.layers")


# 沿相机方向摆放层平面。数值越大（没那么负）越靠近相机。
# 地面比前景远、比中景近，避免地面平面挡住人物。
# sky=-20，background=-12，midground=-8，ground=-4，foreground=-2。
LAYER_Z_OFFSETS: dict[str, float] = {
    "sky": -20.0,
    "background": -12.0,
    "midground": -8.0,
    "ground": -4.0,
    "foreground": -2.0,
}

# 固定米制区间，只留给「没有场景类、也没有物件」的旧调用。
# 新归层按匹配表和各层深度中位数，不再用这些区间，也不再按全图分位数切条。
# 这张表仍写进清单，方便旧的 Blender 插件读取 zMin / zMax。
LAYER_Z_RANGES: dict[str, tuple[float, float]] = {
    "foreground": (0.0, 5.0),
    "midground": (5.0, 15.0),
    "background": (15.0, 50.0),
    "sky": (50.0, float("inf")),
    "ground": (0.0, float("inf")),
}

# 从远到近。地面在中景和前景之间，人物所在的前景最后画，重叠时盖住地面。
LAYER_ORDER: tuple[str, ...] = ("sky", "background", "midground", "ground", "foreground")

# 剩余像素进天空时，行号要落在上半幅。
SKY_UPPER_FRACTION = 0.5


# ──────────────────────────────────────────────────────────────────────────────
# Sky mask
# ──────────────────────────────────────────────────────────────────────────────


def compute_sky_mask(rgb: np.ndarray, depth_meters: Optional[np.ndarray] = None) -> np.ndarray:
    """Return a bool mask of likely sky pixels.

    Heuristic: upper half of the image AND low saturation AND high brightness.
    When the depth map is available we additionally require the pixel to be
    in the far-depth tail (>= P85 of the residual distribution) — that filters
    out a bright white building facade that would otherwise look "sky-like".
    """
    H, W = rgb.shape[:2]
    if H == 0 or W == 0:
        return np.zeros((H, W), dtype=bool)

    # Upper-half mask
    upper = np.zeros((H, W), dtype=bool)
    upper[: int(H * 0.55)] = True

    # Color mask: HSV saturation < 0.4 AND brightness > 0.5.
    img = Image.fromarray(rgb.astype(np.uint8), mode="RGB")
    hsv = np.array(img.convert("HSV"), dtype=np.float32)  # H 0..255, S 0..255, V 0..255
    sat = hsv[..., 1] / 255.0
    val = hsv[..., 2] / 255.0
    color = (sat < 0.4) & (val > 0.5)

    sky = upper & color

    # Far-depth tail — only apply when we have a depth map and the mask is
    # still larger than 1% of the image (so we don't kill the entire sky in
    # flat-depth scenes where the percentile bucket is degenerate).
    if depth_meters is not None and depth_meters.shape == (H, W):
        valid = depth_meters > 0
        if valid.any():
            p85 = float(np.percentile(depth_meters[valid], 85))
            far = depth_meters >= p85
            refined = sky & far
            # If refining collapses sky to < 1% of the image, keep the loose
            # version so a flat / overexposed sky still gets separated.
            if refined.sum() > max(50, H * W * 0.01):
                sky = refined
    return sky


# ──────────────────────────────────────────────────────────────────────────────
# Core bucketing
# ──────────────────────────────────────────────────────────────────────────────


def layers_far_to_near() -> list[str]:
    """按 Z 从远到近。数值越小越远。"""
    return sorted(LAYER_Z_OFFSETS, key=lambda name: LAYER_Z_OFFSETS[name])


def layers_near_to_far() -> list[str]:
    return list(reversed(layers_far_to_near()))


# 近处至少离相机 1 米。层与层之间至少隔开这么多米，避免两张卡片贴在同一深度。
_MIN_LAYER_DEPTH_M = 1.0
_MIN_LAYER_GAP_M = 0.5
# 和归档清单里的默认相机一致：相机在 +Z，离目标 12 米，朝 -Z 看。
PERSPECTIVE_CAMERA_DISTANCE_M = 12.0


def perspective_offsets(
    depth_meters: Optional[np.ndarray],
    masks: dict[str, np.ndarray],
) -> list[dict]:
    """按 Depth Anything 的米制深度摆层，并给出近大远小的平面缩放。

    深度数值越大越远。平面 Z 取负的深度：相机在 +Z、朝 -Z 看，越负越远。
    顺序固定为天空、背景、中景、地面、前景，和渲染从远到近一致。
    测量到的中位数如果把近层放到了远层后面，就把远层再推远，不交换层名。
    ``scale`` 按到相机的距离放大远处的面片：最近一层是 1，越远越大，
    这样在默认相机位置看，远层不会被透视缩成一个点。
    """
    order = layers_far_to_near()
    measured: dict[str, float] = {}
    if depth_meters is not None:
        for name in order:
            mask = masks.get(name)
            if mask is None or mask.shape != depth_meters.shape or not np.any(mask):
                continue
            values = depth_meters[mask]
            values = values[np.isfinite(values) & (values > 0)]
            if values.size:
                measured[name] = float(np.median(values))
    depths = _align_layer_depths(measured, order)
    nearest = min(depths.values())
    near_distance = PERSPECTIVE_CAMERA_DISTANCE_M + nearest
    rows = []
    for name in order:
        depth = depths[name]
        distance = PERSPECTIVE_CAMERA_DISTANCE_M + depth
        scale = distance / near_distance if near_distance > 0 else 1.0
        rows.append({
            "layer": name,
            "depthMeters": round(depth, 4),
            "zOffset": round(-depth, 4),
            "zMin": round(depth, 4),
            "zMax": round(depth, 4),
            "scale": round(scale, 4),
        })
    return rows


def _align_layer_depths(measured: dict[str, float], order: list[str]) -> dict[str, float]:
    """远到近的深度必须单调变小。缺测的层用默认 Z 的绝对值。"""
    canonical = [abs(float(LAYER_Z_OFFSETS[name])) for name in order]
    if not measured:
        values = canonical
    else:
        values = [
            measured[name] if name in measured else canonical[index]
            for index, name in enumerate(order)
        ]
    values = [max(_MIN_LAYER_DEPTH_M, float(value)) for value in values]
    for index in range(len(values) - 2, -1, -1):
        floor = values[index + 1] + _MIN_LAYER_GAP_M
        if values[index] < floor:
            values[index] = floor
    return {name: values[index] for index, name in enumerate(order)}


def _object_depth(obj: object) -> Optional[float]:
    """有效深度均值。缺测或非正数不当成一层的深度中心。"""
    raw = getattr(obj, "depth_mean", None)
    if raw is None:
        return None
    try:
        depth = float(raw)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(depth) or depth <= 0:
        return None
    return depth


def _object_mask(obj: object, height: int, width: int) -> Optional[np.ndarray]:
    mask = getattr(obj, "mask", None)
    if mask is None:
        return None
    arr = np.asarray(mask)
    if arr.ndim == 3 and arr.shape[-1] == 1:
        arr = arr[..., 0]
    arr = arr.astype(bool)
    if arr.shape != (height, width):
        return None
    return arr


def _depth_medians(pairs: list[tuple[object, str]]) -> dict[str, float]:
    """只统计已经归到该层、并且有有效深度的物件。空层不造深度中心。"""
    buckets: dict[str, list[float]] = {}
    for obj, layer in pairs:
        depth = _object_depth(obj)
        if depth is None:
            continue
        buckets.setdefault(layer, []).append(depth)
    return {
        layer: float(np.median(np.asarray(values, dtype=np.float64)))
        for layer, values in buckets.items()
        if values
    }


def _nearest_layer(depth: Optional[float], medians: dict[str, float]) -> Optional[str]:
    """贴到深度中位数最近的一层。距离相同则更近的语义层优先。"""
    if depth is None or not medians:
        return None
    ranks = {name: index for index, name in enumerate(layers_near_to_far())}
    return min(
        medians,
        key=lambda name: (abs(depth - medians[name]), ranks.get(name, 99)),
    )


def _assign_object_layers(objects: list, spec) -> list[tuple[object, str]]:
    """先按匹配表归层，表里没有的再贴已归层的深度中位数。"""
    from app.services.scene_layer_table import layer_for_label

    matched: list[tuple[object, str]] = []
    pending: list[object] = []
    for obj in objects:
        layer = layer_for_label(spec, str(getattr(obj, "label", "") or ""))
        if layer == "sky" and not spec.has_sky:
            layer = None
        if layer == "ground" and not spec.has_ground:
            layer = None
        if layer:
            matched.append((obj, layer))
        else:
            pending.append(obj)

    # 中位数只来自匹配表已经归好的物件，避免未知物先污染中心。
    medians = _depth_medians(matched)
    assigned = list(matched)
    for obj in pending:
        layer = _nearest_layer(_object_depth(obj), medians)
        if layer is None:
            # 还没有任何已归层时，不把未知物丢进前景。
            layer = "midground"
        assigned.append((obj, layer))
    return assigned


def _resolve_scene_class(object_assets: Optional[list], scene_class: Optional[str]) -> str:
    from app.services.scene_layer_table import SCENE_CLASS_NAMES, classify_scene

    if scene_class is not None and str(scene_class).strip():
        name = str(scene_class).strip().lower()
        if name in SCENE_CLASS_NAMES:
            return name
        logger.warning("[layers] 场景类 %r 不在闭集，改用 unknown", scene_class)
        return "unknown"
    if object_assets:
        try:
            return classify_scene(object_assets)
        except Exception as exc:
            logger.warning("[layers] 场景分类失败，改用 unknown: %s", exc)
            return "unknown"
    return "unknown"


def _use_scene_assignment(
    object_assets: Optional[list],
    ground_asset,
    sky_mask: Optional[np.ndarray],
    scene_class: Optional[str],
) -> bool:
    if scene_class is not None:
        return True
    return bool(object_assets) or ground_asset is not None or sky_mask is not None


def build_scene_layer_masks(
    *,
    height: int,
    width: int,
    depth_meters: Optional[np.ndarray],
    object_assets: Optional[list],
    scene_class: str,
) -> dict[str, np.ndarray]:
    """按场景匹配表和深度中位数生成互斥的五层 mask。没有像素的层是全 False。"""
    from app.services.scene_layer_table import get_scene_spec

    spec = get_scene_spec(scene_class)
    pairs = _assign_object_layers(list(object_assets or []), spec)
    codes = {name: index for index, name in enumerate(LAYER_ORDER)}
    code = np.full((height, width), -1, dtype=np.int16)

    # 从远到近画。更近的层覆盖重叠像素，每个像素只属于一层。
    for layer in layers_far_to_near():
        for obj, assigned in pairs:
            if assigned != layer:
                continue
            mask = _object_mask(obj, height, width)
            if mask is None:
                continue
            code[mask] = codes[layer]

    # 剩余像素跟已归物件的深度中位数走，不看画面上下位置。
    # 天空不参与“最近中心”竞选，只有场景允许、位于上半幅、并且比已归背景更远才晋升。
    medians = _depth_medians(pairs)
    centers = {name: value for name, value in medians.items() if name != "sky"}
    if (
        depth_meters is not None
        and depth_meters.shape == (height, width)
        and centers
    ):
        valid = (code < 0) & np.isfinite(depth_meters) & (depth_meters > 0)
        if np.any(valid):
            names = list(centers)
            center_values = np.asarray([centers[name] for name in names], dtype=np.float64)
            ranks = np.asarray(
                [layers_near_to_far().index(name) for name in names],
                dtype=np.float64,
            )
            values = depth_meters[valid].astype(np.float64)
            distance = np.abs(values[:, None] - center_values[None, :])
            pick = np.argmin(distance + ranks[None, :] * 1e-6, axis=1)
            chosen = np.asarray([codes[names[index]] for index in pick], dtype=np.int16)
            background_median = medians.get("background")
            if spec.has_sky and background_median is not None:
                rows = np.nonzero(valid)[0]
                upper = rows < height * SKY_UPPER_FRACTION
                farther_than_background = values > float(background_median)
                chosen[upper & farther_than_background] = codes["sky"]
            code[valid] = chosen

    return {name: code == codes[name] for name in LAYER_ORDER}


def _legacy_range_masks(
    depth_meters: Optional[np.ndarray],
    layers: list[str],
    height: int,
    width: int,
) -> dict[str, np.ndarray]:
    """没有物件也没有场景类时的旧路径：按固定米制区间切，不使用分位数横条。"""
    masks: dict[str, np.ndarray] = {}
    for layer in layers:
        if depth_meters is not None and layer in LAYER_Z_RANGES:
            z_min, z_max = LAYER_Z_RANGES[layer]
            masks[layer] = (depth_meters >= z_min) & (depth_meters < z_max)
        else:
            masks[layer] = np.ones((height, width), dtype=bool)
    return masks


def _layer_masks_for(
    *,
    height: int,
    width: int,
    depth_meters: Optional[np.ndarray],
    object_assets: Optional[list],
    ground_asset,
    sky_mask: Optional[np.ndarray],
    scene_class: Optional[str],
    layers: list[str],
) -> dict[str, np.ndarray]:
    if _use_scene_assignment(object_assets, ground_asset, sky_mask, scene_class):
        resolved = _resolve_scene_class(object_assets, scene_class)
        logger.info("[layers] 场景类 %s，按匹配表和深度中位数归层", resolved)
        return build_scene_layer_masks(
            height=height,
            width=width,
            depth_meters=depth_meters,
            object_assets=object_assets,
            scene_class=resolved,
        )
    return _legacy_range_masks(depth_meters, layers, height, width)


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────


def export_layers(
    image: Image.Image,
    depth_meters: Optional[np.ndarray] = None,
    *,
    layers: Optional[list[str]] = None,
    feather_px: int = 1,
    object_assets: Optional[list] = None,
    ground_asset=None,
    sky_mask: Optional[np.ndarray] = None,
    scene_class: Optional[str] = None,
) -> dict[str, Image.Image]:
    """按场景类导出五张 RGBA 层图。

    属于该层的像素保留原图 RGB，其余全透明。没有像素的层仍返回全透明图。
    传入 ``scene_class`` 或物件时走匹配表和深度中位数；两者都没有时才用固定米制区间。

    Args:
        image: 场景原图。
        depth_meters: (H, W) 米制深度。形状必须和图像一致。
        layers: 要导出的层名。默认五层都导出。
        feather_px: 边缘羽化半径。0 表示硬边。
        object_assets: GroundingDINO + SAM2 的物件。归层看匹配表，不看 layer_hint。
        ground_asset: 地面拟合结果。像素归层不使用它的 cutout，避免地面盖住人物。
        sky_mask: 保留参数。新规则不再用低饱和度上半幅直接涂天空。
        scene_class: 闭集场景类。不传且已有物件时，会现场分类。
    """
    if image is None:
        raise ValueError("image is required")

    if layers is None:
        layers = list(LAYER_ORDER)
    else:
        layers = [layer.lower() for layer in layers]

    rgb = image.convert("RGB")
    w, h = rgb.size
    rgb_np = np.array(rgb)

    if depth_meters is not None and depth_meters.shape != (h, w):
        raise ValueError(
            f"depth_meters shape {depth_meters.shape} does not match image ({h}, {w})"
        )

    layer_masks = _layer_masks_for(
        height=h,
        width=w,
        depth_meters=depth_meters,
        object_assets=object_assets,
        ground_asset=ground_asset,
        sky_mask=sky_mask,
        scene_class=scene_class,
        layers=layers,
    )

    # 合成每层 RGBA。
    out: dict[str, Image.Image] = {}
    for layer in layers:
        mask = layer_masks.get(layer, np.zeros((h, w), dtype=bool))
        alpha = (mask.astype(np.uint8) * 255)
        alpha_img = Image.fromarray(alpha, mode="L")
        if feather_px > 0:
            blurred = alpha_img.filter(
                ImageFilter.GaussianBlur(radius=float(feather_px))
            )
            blurred_np = np.array(blurred)
            alpha = (blurred_np > 127).astype(np.uint8) * 255
            alpha_img = Image.fromarray(alpha, mode="L")
        rgba = np.dstack([rgb_np, alpha])
        out[layer] = Image.fromarray(rgba, mode="RGBA")
    return out


def inpaint_occluded_layers(
    image: Image.Image,
    layer_imgs: dict[str, Image.Image],
    depth_meters: Optional[np.ndarray],
    *,
    object_assets: Optional[list] = None,
    ground_asset=None,
    sky_mask: Optional[np.ndarray] = None,
    scene_class: Optional[str] = None,
    inpaint_fn: Optional[Callable] = None,
) -> dict[str, Image.Image]:
    """把更近层挡住的区域用 LaMa 补进更远的层。

    顺序跟 Z 一致：前景最近，不被补全；地面比前景远，不再当成最近的遮挡。
    近层自己的像素不动。远层在被挡住的像素上写入补全结果并变为不透明。
    ``inpaint_fn`` 默认是 ``app.utils.inpaint_utils.generate_inpaint``。
    """
    if not layer_imgs:
        return layer_imgs

    rgb = image.convert("RGB")
    h, w = rgb.size[1], rgb.size[0]
    layer_masks = _layer_masks_for(
        height=h,
        width=w,
        depth_meters=depth_meters,
        object_assets=object_assets,
        ground_asset=ground_asset,
        sky_mask=sky_mask,
        scene_class=scene_class,
        layers=list(layer_imgs),
    )

    # Z 越小越远。前景 -2 在最后，地面 -4 排在它前面，所以地面要补前景挡住的洞。
    names = [name for name in layer_imgs if name in LAYER_Z_OFFSETS]
    names.sort(key=lambda name: LAYER_Z_OFFSETS[name])

    if inpaint_fn is None:
        from app.utils.inpaint_utils import generate_inpaint
        inpaint_fn = generate_inpaint

    for index, name in enumerate(names):
        own = layer_masks.get(name)
        if own is None or own.shape != (h, w):
            own = np.zeros((h, w), dtype=bool)
        closer = np.zeros((h, w), dtype=bool)
        for nearer in names[index + 1:]:
            nearer_mask = layer_masks.get(nearer)
            if nearer_mask is not None and nearer_mask.shape == (h, w):
                closer |= nearer_mask.astype(bool)
        hole = closer & ~own
        ratio = float(hole.mean()) if hole.size else 0.0
        if ratio < 0.001:
            logger.info("[layers] %s: no occluder to inpaint (%.4f)", name, ratio)
            continue
        logger.info("[layers] LaMa fill %s occluded %.1f%%", name, ratio * 100)
        mask_img = Image.fromarray((hole.astype(np.uint8) * 255), mode="L")
        try:
            filled = inpaint_fn(rgb, mask_img, "occluded background")
        except Exception as exc:
            logger.warning("[layers] LaMa failed for %s: %s", name, exc)
            continue
        filled_np = np.array(filled.convert("RGB"))
        if filled_np.shape[:2] != (h, w):
            filled_np = np.array(
                Image.fromarray(filled_np).resize((w, h), Image.LANCZOS)
            )
        layer = np.array(layer_imgs[name].convert("RGBA"))
        layer[hole, 0:3] = filled_np[hole]
        layer[hole, 3] = 255
        layer_imgs[name] = Image.fromarray(layer, mode="RGBA")
    return layer_imgs


def export_layers_to_data_uris(
    image: Image.Image,
    depth_meters: Optional[np.ndarray] = None,
    *,
    layers: Optional[list[str]] = None,
    feather_px: int = 1,
    fmt: str = "PNG",
    object_assets: Optional[list] = None,
    ground_asset=None,
    sky_mask: Optional[np.ndarray] = None,
    scene_class: Optional[str] = None,
) -> dict[str, str]:
    """Convenience wrapper — returns ``data:image/png;base64,...`` URIs.

    Useful for embedding layer PNGs directly in JSON responses without
    persisting to disk.
    """
    layer_imgs = export_layers(
        image, depth_meters, layers=layers, feather_px=feather_px,
        object_assets=object_assets, ground_asset=ground_asset, sky_mask=sky_mask,
        scene_class=scene_class,
    )
    import base64
    import io

    out: dict[str, str] = {}
    for layer, img in layer_imgs.items():
        buf = io.BytesIO()
        img.save(buf, format=fmt)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        out[layer] = f"data:image/{fmt.lower()};base64,{b64}"
    return out


def export_layers_to_disk(
    image: Image.Image,
    out_dir: Path,
    depth_meters: Optional[np.ndarray] = None,
    *,
    layers: Optional[list[str]] = None,
    feather_px: int = 1,
    name_prefix: str = "layer",
    object_assets: Optional[list] = None,
    ground_asset=None,
    sky_mask: Optional[np.ndarray] = None,
    scene_class: Optional[str] = None,
) -> dict[str, Path]:
    """Persist each layer PNG to ``out_dir`` and return their file paths."""
    layer_imgs = export_layers(
        image, depth_meters, layers=layers, feather_px=feather_px,
        object_assets=object_assets, ground_asset=ground_asset, sky_mask=sky_mask,
        scene_class=scene_class,
    )
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}
    for layer, img in layer_imgs.items():
        path = out_dir / f"{name_prefix}_{layer}.png"
        img.save(path, format="PNG")
        out[layer] = path
        logger.info("[layers] wrote %s (%d KB)", path, path.stat().st_size // 1024)
    return out


def build_z_offset_table() -> list[dict]:
    """Return the canonical Z-offset table for the 5 layers.

    The Blender plugin reads this exact table (via its manifest JSON) to know
    where to place each layer plane in 3D space.
    """
    table = []
    for layer in LAYER_ORDER:
        z_min, z_max = LAYER_Z_RANGES[layer]
        table.append({
            "layer": layer,
            "zOffset": LAYER_Z_OFFSETS[layer],
            "zMin": float(z_min),
            "zMax": float(z_max) if z_max != float("inf") else 9999.0,
        })
    return table