"""
Paper Diorama Generation — AICSS 2.0

Generates paper-art-style textures for diorama scenes:
  - Paper Style Transfer  : cartoon/illustration look from photograph
  - Thickness Map         : height/depth field from object mask
  - Normal Map            : surface normals from height field
  - Outline Enhancement   : paper-cut edge strokes
  - Full Diorama Textures : combined output per object/layer
"""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image, ImageDraw

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _pil_to_cv2(pil: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def _cv2_to_pil(cv2_img: np.ndarray) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(cv2_img, cv2.COLOR_BGR2RGB))


def _load_mask(mask_url: str) -> np.ndarray:
    """Load a mask from a base64 data URL or URL into a 0-255 uint8 grayscale ndarray."""
    if mask_url.startswith("data:"):
        import base64
        raw = mask_url.split(",", 1)[1]
        data = base64.b64decode(raw)
        from io import BytesIO
        pil = Image.open(BytesIO(data))
    else:
        import requests
        resp = requests.get(mask_url, timeout=30)
        resp.raise_for_status()
        from io import BytesIO
        pil = Image.open(BytesIO(resp.content))

    mask = np.array(pil.convert("L"))
    if mask.dtype != np.uint8:
        mask = mask.astype(np.uint8)
    return mask


# ─────────────────────────────────────────────────────────────────────────────
# Downsampling helpers — keep heavy CV2 ops on manageable sizes
# ─────────────────────────────────────────────────────────────────────────────

# 512 px is large enough to preserve layer-boundary detail from the alpha mask
# while cutting bilateral / distanceTransform / findContours time from ~20 s to ~0.3 s
_WORK_SIZE = 512


def _downsample_if_needed(pil: Image.Image) -> tuple[Image.Image, float]:
    """
    Downsample ``pil`` so its longest edge ≤ _WORK_SIZE.
    Returns (processed_pil, scale_factor) so the caller can re-upscale later.
    """
    w, h = pil.size
    if max(w, h) <= _WORK_SIZE:
        return pil, 1.0
    scale = _WORK_SIZE / max(w, h)
    new_w, new_h = int(w * scale), int(h * scale)
    return pil.resize((new_w, new_h), Image.LANCZOS), scale


def _upsample_to(orig: Image.Image, target_size: tuple[int, int]) -> Image.Image:
    """Re-upsample ``orig`` to ``target_size`` using LANCZOS."""
    return orig.resize(target_size, Image.LANCZOS)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Paper Style Transfer
# ─────────────────────────────────────────────────────────────────────────────

def cartoonize_image(
    image: Image.Image,
    num_downsampling_levels: int = 3,
    bilateral_filter_d: int = 9,
    bilateral_filter_sigma_color: float = 5.0,
    bilateral_filter_sigma_space: float = 5.0,
    edge_Blurksize: int = 5,
    edge_canny_low: int = 50,
    edge_canny_high: int = 150,
    color_quantization_levels: int = 12,
) -> Image.Image:
    """
    Convert a photograph to a paper-cut / illustration style.

    Steps:
      1. Downsample to _WORK_SIZE → run bilateral filter + k-means at low res
      2. Upsample result back to original size
      3. Edge composite: apply Canny edges from full-res image over upsampled cartoon

    Parameters
    ----------
    image          : input PIL image (RGB), any size
    bilateral_filter_* : bilateral filter parameters (larger → smoother flat areas)
    edge_canny_*       : Canny edge detection thresholds
    color_quantization_levels : number of colour clusters (lower → flatter look)

    Returns
    -------
    PIL Image (RGB) — paper-illustration style
    """
    orig_size = image.size  # (w, h)

    # ── Step 0: Work on downsampled image for speed ───────────────────────────
    work_img, scale = _downsample_if_needed(image)
    work_w, work_h = work_img.size
    img = _pil_to_cv2(work_img)

    # ── Step 1: Edge detection (on downsampled image) ─────────────────────────
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.bilateralFilter(gray, edge_Blurksize, 75, 75)
    edges = cv2.Canny(blurred, edge_canny_low, edge_canny_high)
    edges_inv = cv2.bitwise_not(edges)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    edges_inv = cv2.dilate(edges_inv, kernel, iterations=1)

    # ── Step 2: Bilateral filter (on downsampled image) ───────────────────────
    smoothed = cv2.bilateralFilter(
        img,
        bilateral_filter_d,
        bilateral_filter_sigma_color * 10,
        bilateral_filter_sigma_space * 10,
    )

    # ── Step 3: Colour quantisation via k-means (on downsampled image) ─────────
    pixels = smoothed.reshape(-1, 3).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.1)
    _, labels, centers = cv2.kmeans(
        pixels,
        color_quantization_levels,
        None,
        criteria,
        10,
        cv2.KMEANS_PP_CENTERS,
    )
    quantized_flat = centers[labels.flatten()].reshape(smoothed.shape).astype(np.uint8)

    # ── Step 4: Composite edges over quantised colour ─────────────────────────
    result = quantized_flat.copy()
    result[edges_inv == 0] = [20, 20, 20]

    # ── Step 5: Upsample back to original size ────────────────────────────────
    # _WORK_SIZE ≤ 512, so upscale preserves cartoon clarity while matching output size
    result_pil = _cv2_to_pil(result)
    if scale != 1.0:
        result_pil = _upsample_to(result_pil, orig_size)

    return result_pil


def paper_style_from_url(image_url: str, **kwargs) -> Image.Image:
    """Load image from URL/base64 and apply paper style."""
    if image_url.startswith("data:"):
        import base64
        from io import BytesIO
        raw = image_url.split(",", 1)[1]
        data = base64.b64decode(raw)
        pil = Image.open(BytesIO(data)).convert("RGB")
    else:
        import requests
        resp = requests.get(image_url, timeout=30)
        resp.raise_for_status()
        from io import BytesIO
        pil = Image.open(BytesIO(resp.content)).convert("RGB")
    return cartoonize_image(pil, **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Thickness / Height Map Generation
# ─────────────────────────────────────────────────────────────────────────────

def generate_thickness_map(
    mask: np.ndarray,
    thickness_range_mm: tuple[float, float] = (1.0, 5.0),
    edge_brightness_factor: float = 1.8,
) -> np.ndarray:
    """
    Generate a height/depth field from a binary object mask.
    Operates on a downsampled mask for speed, then upsamples the result back
    to ``mask.shape``.

    Intuition: paper cut edges are the tallest (lightest in height map),
    interior flat regions are the base (darkest in height map).

    Steps
    -----
      1. Downsample mask to _WORK_SIZE
      2. Compute distance transform (the heaviest step)
      3. Upsample height map back to original resolution
      4. Normalise to [0, 255] (uint8)

    Parameters
    ----------
    mask              : 0-255 uint8, 255 = object, 0 = background, any size
    thickness_range_mm: (min, max) mm thickness range  (used only for normalisation)
    edge_brightness_factor: how bright to make the edges vs. flat regions

    Returns
    -------
    uint8 ndarray (H, W) matching mask.shape, 255 = tallest edge, 0 = base
    """
    orig_h, orig_w = mask.shape[:2]

    # ── Step 1: Downsample mask ─────────────────────────────────────────────────
    # Use PIL for high-quality resize (nearest-neighbour for binary mask avoids
    # introducing intermediate gray values at boundaries)
    mask_pil = Image.fromarray(mask)
    work_pil = mask_pil.resize(
        (max(1, int(orig_w * min(1.0, _WORK_SIZE / max(orig_w, orig_h)))),
         max(1, int(orig_h * min(1.0, _WORK_SIZE / max(orig_w, orig_h))))),
        Image.NEAREST,
    )
    work = np.array(work_pil)
    if work.dtype != np.uint8:
        work = work.astype(np.uint8)

    # ── Step 2: Distance transform on small mask ───────────────────────────────
    _, binary = cv2.threshold(work, 127, 255, cv2.THRESH_BINARY)
    dist_inside = cv2.distanceTransform(binary, cv2.DIST_L2, cv2.DIST_MASK_3)
    dist_outside = cv2.distanceTransform(cv2.bitwise_not(binary), cv2.DIST_L2, cv2.DIST_MASK_3)
    height_small = dist_inside * edge_brightness_factor + dist_outside * 0.5

    if height_small.max() > 0:
        height_small = (height_small / height_small.max()) * 255.0
    height_small = height_small.astype(np.float32)
    height_small = cv2.GaussianBlur(height_small, (3, 3), 0)

    # ── Step 3: Upsample back to original resolution ───────────────────────────
    height_full = cv2.resize(
        height_small,
        (orig_w, orig_h),
        interpolation=cv2.INTER_LINEAR,
    ).astype(np.uint8)

    return height_full


def generate_thickness_map_rgb(thickness: np.ndarray) -> Image.Image:
    """Visualise thickness map as a blue→red false-colour image."""
    normed = thickness.astype(np.float32) / 255.0
    # Jet colormap: blue (near/flat) → cyan → yellow → red (far/edge)
    cmap = cv2.COLORMAP_JET
    coloured = cv2.applyColorMap(thickness, cmap)
    return Image.fromarray(cv2.cvtColor(coloured, cv2.COLOR_BGR2RGB))


# ─────────────────────────────────────────────────────────────────────────────
# 3. Normal Map Generation
# ─────────────────────────────────────────────────────────────────────────────

def generate_normal_map(height: np.ndarray, strength: float = 5.0) -> np.ndarray:
    """
    Compute a normal map from a height field using Sobel derivatives.

    法线图的原理：每个像素存储一个 3D 向量 (nx, ny, nz)，表示该点表面的朝向。
    在 3D 渲染中，着色器用这些向量计算光照，从而产生立体感。

    Parameters
    ----------
    height    : uint8 ndarray (H, W), 0=low, 255=high
    strength  : normal map strength multiplier (higher = more pronounced normals)

    Returns
    -------
    uint8 ndarray (H, W, 3), RGB normal map (each channel 0–255)
    """
    # Convert to float32 in [0, 1]
    h = height.astype(np.float32) / 255.0

    # Sobel 梯度：dx/du 表示水平方向高度变化率，dy/du 表示竖直方向
    # 梯度越大 → 表面越倾斜 → 法线方向偏离垂直方向越多
    grad_x = cv2.Sobel(h, cv2.CV_32F, 1, 0, ksize=3, scale=strength)
    grad_y = cv2.Sobel(h, cv2.CV_32F, 0, 1, ksize=3, scale=strength)

    # 构建法线向量 (grad_x, -grad_y, 1) 并归一化：
    #   - grad_x > 0：向右倾斜 → nx > 0
    #   - grad_y > 0：向上倾斜（但图像 y 轴向下，所以取负）
    #   - z 固定为 1：保证向量始终指向前方（朝观众方向）
    # 最终归一化使法线向量长度为 1，方向就是该点表面朝向
    normals = np.stack([grad_x, -grad_y, np.ones_like(grad_x)], axis=-1)
    norms = np.linalg.norm(normals, axis=-1, keepdims=True)
    normals = normals / (norms + 1e-8)

    # 从 [-1, 1] 映射到 [0, 255]：
    #   R = nx → 左右光照反射
    #   G = ny → 上下光照反射
    #   B = nz → 始终较亮（指向观众的 z 分量）
    normals = ((normals + 1) * 0.5 * 255).clip(0, 255).astype(np.uint8)

    return normals


def generate_normal_map_pil(height: np.ndarray, strength: float = 5.0) -> Image.Image:
    """Return normal map as PIL RGB image."""
    return Image.fromarray(generate_normal_map(height, strength))


# ─────────────────────────────────────────────────────────────────────────────
# 4. Outline / Paper-Cut Edge Enhancement
# ─────────────────────────────────────────────────────────────────────────────

def apply_paper_outline(
    image: Image.Image,
    mask: np.ndarray,
    outline_color: tuple[int, int, int] = (255, 255, 255),
    outline_width_outer: int = 3,
    outline_width_inner: int = 1,
    shadow_offset: int = 2,
    shadow_color: tuple[int, int, int] = (40, 40, 40),
    add_shadow: bool = True,
) -> Image.Image:
    """
    Add paper-cut style outlines and drop shadows to an RGBA/RGB image.

    Steps
    -----
      1. Downsample image + mask to _WORK_SIZE
      2. Compute outer contour at low res → draw white outline
      3. Compute inner contour at low res → draw dark outline
      4. Upscale result back to original size
      5. Apply drop shadow at full resolution (cheap O(n) operation)

    Parameters
    ----------
    image          : PIL RGB/RGBA image, any size
    mask           : uint8 0-255, 255 = object, any size
    outline_color  : RGB colour for the outer cut edge
    outline_width  : thickness in pixels of the outer edge
    shadow_offset  : pixels to offset shadow
    shadow_color   : RGB shadow colour
    add_shadow     : whether to add drop shadow

    Returns
    -------
    PIL Image (RGBA)
    """
    orig_size = image.size  # (w, h)
    orig_h, orig_w = orig_size[1], orig_size[0]

    # ── Step 1: Downsample both image and mask to the same working size ────────
    work_img, img_scale = _downsample_if_needed(image)
    work_w, work_h = work_img.size

    # Resize mask to the same working dimensions as work_img so binary.shape matches img_arr.shape
    work_mask_pil = Image.fromarray(mask).resize((work_w, work_h), Image.NEAREST)
    work_mask = np.array(work_mask_pil)
    if work_mask.dtype != np.uint8:
        work_mask = work_mask.astype(np.uint8)

    img_arr = np.array(work_img.convert("RGBA"))
    binary = (work_mask > 127).astype(np.uint8) * 255

    # ── Step 2: Contour ops at low resolution ─────────────────────────────────
    # Scale outline widths so they look proportional on the upscaled result
    outline_outer_s = max(1, int(outline_width_outer * img_scale))
    outline_inner_s = max(1, int(outline_width_inner * img_scale))

    # Work directly with PIL Images — avoid round-tripping through np.array which
    # can lose precision and adds unnecessary copies
    img_result_pil = work_img.convert("RGBA")

    # Outer outline
    if outline_outer_s > 0:
        outer_contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        overlay = Image.new("RGBA", (work_w, work_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        oc_r, oc_g, oc_b = outline_color
        for cnt in outer_contours:
            pts = cnt.squeeze().reshape(-1, 2).tolist()
            if len(pts) >= 2:
                draw.line(pts, fill=(oc_r, oc_g, oc_b, 255), width=outline_outer_s)
        img_result_pil = Image.alpha_composite(img_result_pil, overlay)

    # Inner outline
    if outline_inner_s > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        dilated = cv2.dilate(binary, kernel, iterations=outline_inner_s)
        inner = cv2.subtract(dilated, binary)
        inner_contours, _ = cv2.findContours(inner, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        overlay = Image.new("RGBA", (work_w, work_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        sc_r, sc_g, sc_b = shadow_color
        for cnt in inner_contours:
            pts = cnt.squeeze().reshape(-1, 2).tolist()
            if len(pts) >= 2:
                draw.line(pts, fill=(sc_r, sc_g, sc_b, 255), width=outline_inner_s)
        img_result_pil = Image.alpha_composite(img_result_pil, overlay)

    # ── Step 3: Upscale back to original size ─────────────────────────────────
    if img_scale != 1.0:
        result_pil = img_result_pil.resize(orig_size, Image.LANCZOS)
    else:
        result_pil = img_result_pil

    # ── Step 4: Drop shadow at full resolution ─────────────────────────────────
    if add_shadow and shadow_offset > 0:
        img_arr_full = np.array(result_pil)
        binary_full = (mask > 127).astype(np.uint8) * 255
        result_cv = cv2.cvtColor(img_arr_full, cv2.COLOR_RGBA2BGR)
        shadow_arr = cv2.bitwise_and(result_cv, result_cv, mask=binary_full)
        M = np.float32([[1, 0, shadow_offset], [0, 1, shadow_offset]])
        shadow_shifted = cv2.warpAffine(shadow_arr, M, (orig_w, orig_h),
                                         borderMode=cv2.BORDER_REFLECT)
        shadow_rgba = Image.fromarray(cv2.cvtColor(shadow_shifted, cv2.COLOR_BGR2RGBA))
        shadow_rgba.putalpha(60)
        result_pil = Image.alpha_composite(shadow_rgba, result_pil)

    return result_pil


# ─────────────────────────────────────────────────────────────────────────────
# 5. Full Paper Diorama Texture Generation
# ─────────────────────────────────────────────────────────────────────────────

def generate_paper_diorama_textures(
    image: Image.Image,
    mask: np.ndarray,
    thickness_range_mm: tuple[float, float] = (1.0, 5.0),
    outline_width: int = 3,
    style_strength: float = 0.7,
    color_levels: int = 12,
) -> dict:
    """
    Generate a complete set of paper-diorama textures for a single object.

    输出 5 张纹理图，覆盖前端 Viewer3D 的完整 3D 渲染需求：
      - paper_style_url   : 卡通化主纹理（作为 MeshStandardMaterial 的 map）
      - outlined_url      : 带外轮廓和投影的版本（3D 边缘更突出）
      - thickness_url     : 伪彩色厚度图（调试用，人类可读）
      - thickness_gray_url: 灰度厚度图（Three.js displacementMap 用）
      - normal_map_url    : 法线贴图（Three.js normalMap，光照细节）

    Output keys
    -----------
    paper_style_url   : base64 PNG — illustrated paper style image (RGBA, transparent where mask=0)
    thickness_url     : base64 PNG — thickness/height field (false colour)
    normal_map_url    : base64 PNG — surface normal map
    outlined_url      : base64 PNG — paper-style image with cut edges + shadow (RGBA, transparent where mask=0)
    thickness_gray_url: base64 PNG — thickness as grayscale
    """
    from app.utils.image_utils import pil_to_base64

    # ── 0. Normalise mask to uint8 ─────────────────────────────────────────────
    if mask.dtype != np.uint8:
        mask_norm = mask.astype(np.uint8)
    else:
        mask_norm = mask

    # ── 1. Paper style transfer ───────────────────────────────────────────────
    styled = cartoonize_image(
        image,
        color_quantization_levels=color_levels,
        bilateral_filter_sigma_color=style_strength * 10,
        bilateral_filter_sigma_space=style_strength * 10,
    )

    # ── 2. Apply mask alpha to styled image ───────────────────────────────────
    # Convert to RGBA and set alpha = mask: paper regions (mask=255) are opaque,
    # empty regions (mask=0) become fully transparent.
    styled_rgba = np.array(styled.convert("RGBA"))
    styled_rgba[:, :, 3] = mask_norm
    styled_with_alpha = Image.fromarray(styled_rgba, mode="RGBA")

    # ── 3. Thickness map ─────────────────────────────────────────────────────
    thickness = generate_thickness_map(mask_norm, thickness_range_mm=thickness_range_mm)
    thickness_gray_pil = Image.fromarray(thickness)

    # ── 4. Normal map ─────────────────────────────────────────────────────────
    normal = generate_normal_map(thickness)

    # ── 5. Paper outline ─────────────────────────────────────────────────────
    # Use the alpha-aware styled image so outline draws on transparent background,
    # and contour detection only operates within the paper region (mask=255).
    outlined = apply_paper_outline(
        styled_with_alpha,
        mask_norm,
        outline_width_outer=outline_width,
        outline_width_inner=max(1, outline_width // 2),
    )

    return {
        "paper_style_url":    pil_to_base64(styled_with_alpha, fmt="PNG"),
        "thickness_url":     pil_to_base64(generate_thickness_map_rgb(thickness), fmt="PNG"),
        "normal_map_url":     pil_to_base64(Image.fromarray(normal), fmt="PNG"),
        "outlined_url":       pil_to_base64(outlined, fmt="PNG"),
        "thickness_gray_url": pil_to_base64(thickness_gray_pil, fmt="PNG"),
    }
