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
      1. Convert to grayscale → detect edges (Canny)
      2. Apply bilateral filter to preserve edges while smoothing colour
      3. Colour quantisation (k-means) for flat colour regions
      4. Composite: quantised colour × edge mask

    Parameters
    ----------
    image          : input PIL image (RGB)
    bilateral_filter_* : bilateral filter parameters (larger → smoother flat areas)
    edge_canny_*       : Canny edge detection thresholds
    color_quantization_levels : number of colour clusters (lower → flatter look)

    Returns
    -------
    PIL Image (RGB) — paper-illustration style
    """
    img = _pil_to_cv2(image)

    # ── Step 1: Edge detection ───────────────────────────────────────────────
    # 先对灰度图做一次轻微的双边滤波，作用是：
    # 去除高频噪声的同时保留边缘，使后续 Canny 边缘检测更稳定
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.bilateralFilter(gray, edge_Blurksize, 75, 75)
    edges = cv2.Canny(blurred, edge_canny_low, edge_canny_high)
    # Canny 检出的边缘为白色(255)，背景为黑色(0)
    # 反转后：边缘变成黑色(0)，物体内部变成白色(255)
    # 这样后续可以作为掩膜，将深色笔触叠加到白色纸面上
    edges_inv = cv2.bitwise_not(edges)

    # 轻微膨胀边缘，使线条在卡通化后更明显，避免细小的断线
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    edges_inv = cv2.dilate(edges_inv, kernel, iterations=1)

    # ── Step 2: Bilateral filter (preserves edges, smooths flat colour) ───────
    # 双边滤波的核心优势：空间距离 + 颜色相似度 双重加权
    #   - 空间核：靠近中心点的像素权重更大（保局部结构）
    #   - 颜色核：颜色相近的像素权重更大（跨边缘处不会模糊）
    # 结果：物体内部平滑，边缘被完整保留 — 这正是卡通插画需要的效果
    smoothed = cv2.bilateralFilter(
        img,
        bilateral_filter_d,
        bilateral_filter_sigma_color * 10,   # sigmaColor → scaled for uint8 range
        bilateral_filter_sigma_space * 10,   # sigmaSpace
    )

    # ── Step 3: Colour quantisation via k-means ─────────────────────────────
    # k-means 将颜色聚类到 K 个中心，使相近颜色被强制归并为同一色块
    # 效果：产生大面积扁平色区，消除色调渐变 — 接近手绘插画/剪纸的质感
    # 颜色数量越少 → 色块越扁平 → 纸张感越强
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

    # ── Step 4: Composite edges over quantised colour ───────────────────────
    result = quantized_flat.copy()

    # 用 [20, 20, 20] 而不是纯黑 (0,0,0) 绘制边缘：
    #   - 纯黑线条过于生硬，像墨水钢笔画
    #   - 略浅的深灰更接近铅笔/炭笔的质感，视觉上更柔和自然
    result[edges_inv == 0] = [20, 20, 20]

    return _cv2_to_pil(result)


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

    Intuition: paper cut edges are the tallest (lightest in height map),
    interior flat regions are the base (darkest in height map).

    Steps
    -----
      1. Compute distance transform from background → edges are farthest
      2. Compute gradient magnitude → strong gradients = steep "side walls"
      3. Combine edge distance + gradient into single height map
      4. Normalise to [0, 255] (uint8)

    Parameters
    ----------
    mask              : 0-255 uint8, 255 = object, 0 = background
    thickness_range_mm: (min, max) mm thickness range
    edge_brightness_factor: how bright to make the edges vs. flat regions

    Returns
    -------
    uint8 ndarray (H, W), 255 = tallest edge, 0 = base
    """
    # Ensure mask is binary
    _, binary = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)

    # dist_inside：对物体内部像素，计算其到最近背景点的距离
    #   远离边缘（靠近物体中心）的像素距离大 → 颜色更亮
    #   紧贴边缘的像素距离小 → 颜色更暗
    # dist_outside：对背景像素，计算其到最近物体边缘的距离
    #   这使得物体边缘两侧都有一圈"陡坡"
    dist_inside = cv2.distanceTransform(binary, cv2.DIST_L2, cv2.DIST_MASK_3)
    dist_outside = cv2.distanceTransform(cv2.bitwise_not(binary), cv2.DIST_L2, cv2.DIST_MASK_3)

    # 组合策略：边缘处两个距离都较大 → 叠加后最亮（纸边最厚）
    # 物体内部中心 dist_inside 大，但 dist_outside = 0 → 亮度适中（纸面平坦）
    # 背景区域两者都小 → 保持黑暗（作为基线）
    # edge_brightness_factor = 1.8：边缘处距离乘以 1.8，使边缘更突出
    # dist_outside * 0.5：外部陡坡权重较小，仅起平滑过渡作用
    height = dist_inside * edge_brightness_factor + dist_outside * 0.5

    # Normalise to 0–255
    if height.max() > 0:
        height = (height / height.max()) * 255.0
    height = height.astype(np.uint8)

    # 高斯模糊的作用：软化从边缘到内部的亮度突变
    # 不加模糊时，边缘到内部会产生明显的阶梯状过渡
    # 模糊后过渡更自然，类似纸张从切口到平面的柔和倾斜
    height = cv2.GaussianBlur(height, (3, 3), 0)

    return height


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
      1. Compute outer contour of the mask → draw white outline
      2. Compute inner contour (dilate → subtract) → draw dark outline
      3. Optional drop shadow offset below-right
      4. Composite onto original

    Parameters
    ----------
    image          : PIL RGB/RGBA image
    mask           : uint8 0-255, 255 = object
    outline_color  : RGB colour for the outer cut edge
    outline_width  : thickness in pixels of the outer edge
    shadow_offset  : pixels to offset shadow
    shadow_color   : RGB shadow colour
    add_shadow     : whether to add drop shadow

    Returns
    -------
    PIL Image (RGBA)
    """
    img = image.convert("RGBA")
    img_arr = np.array(img)
    binary = (mask > 127).astype(np.uint8) * 255

    result = cv2.cvtColor(img_arr, cv2.COLOR_RGBA2BGRA)

    # ── Drop shadow (PIL alpha-composite) ─────────────────────────────────────
    if add_shadow and shadow_offset > 0:
        shadow_arr = cv2.bitwise_and(result, result, mask=binary)
        M = np.float32([[1, 0, shadow_offset], [0, 1, shadow_offset]])
        shadow_shifted = cv2.warpAffine(shadow_arr, M, (img.width, img.height),
                                         borderMode=cv2.BORDER_REFLECT)
        shadow_rgba = Image.fromarray(cv2.cvtColor(shadow_shifted, cv2.COLOR_BGR2RGBA))
        shadow_rgba.putalpha(60)
        img = Image.alpha_composite(shadow_rgba, img)

    # ── Contour masks for drawing ─────────────────────────────────────────────
    h, w = binary.shape

    # Outer outline
    if outline_width_outer > 0:
        outer_contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        outer_mask = np.zeros((h, w), dtype=np.uint8)
        cv2.drawContours(outer_mask, outer_contours, -1, 255,
                         thickness=max(1, outline_width_outer), lineType=cv2.LINE_AA)
        oc_r, oc_g, oc_b = outline_color
        overlay = Image.new("RGBA", (w, h), (oc_r, oc_g, oc_b, 0))
        draw = ImageDraw.Draw(overlay)
        for cnt in outer_contours:
            pts = cnt.squeeze().reshape(-1, 2).tolist()
            if len(pts) >= 2:
                draw.line(pts, fill=(oc_r, oc_g, oc_b, 255), width=max(1, outline_width_outer))
        img = Image.alpha_composite(img, overlay)

    # Inner outline：通过先膨胀再相减，得到物体边界处的一个"内缩环"
    # 这个环代表物体内部的凹陷感——在剪纸中，边缘被切除后，
    # 内侧通常会有一个深色的压痕线，模拟纸张折叠或裁切的痕迹
    if outline_width_inner > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        dilated = cv2.dilate(binary, kernel, iterations=outline_width_inner)
        inner = cv2.subtract(dilated, binary)
        inner_contours, _ = cv2.findContours(inner, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if inner_contours:
            sc_r, sc_g, sc_b = shadow_color
            overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            for cnt in inner_contours:
                pts = cnt.squeeze().reshape(-1, 2).tolist()
                if len(pts) >= 2:
                    draw.line(pts, fill=(sc_r, sc_g, sc_b, 255), width=max(1, outline_width_inner))
            img = Image.alpha_composite(img, overlay)

    return img


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
    paper_style_url   : base64 PNG — illustrated paper style image
    thickness_url     : base64 PNG — thickness/height field (false colour)
    normal_map_url    : base64 PNG — surface normal map
    outlined_url      : base64 PNG — paper-style image with cut edges + shadow
    thickness_gray_url: base64 PNG — thickness as grayscale
    """
    from app.utils.image_utils import pil_to_base64

    # ── 1. Paper style transfer ───────────────────────────────────────────────
    styled = cartoonize_image(
        image,
        color_quantization_levels=color_levels,
        bilateral_filter_sigma_color=style_strength * 10,
        bilateral_filter_sigma_space=style_strength * 10,
    )

    # ── 2. Thickness map ─────────────────────────────────────────────────────
    thickness = generate_thickness_map(mask, thickness_range_mm=thickness_range_mm)
    thickness_gray_pil = Image.fromarray(thickness)

    # ── 3. Normal map ─────────────────────────────────────────────────────────
    normal = generate_normal_map(thickness)

    # ── 4. Paper outline ─────────────────────────────────────────────────────
    # outline_width_inner = outline_width // 2：内轮廓比外轮廓细一半
    # 外轮廓代表纸张切割边（最显眼），内轮廓模拟折叠压痕（辅助感）
    outlined = apply_paper_outline(
        styled,
        mask,
        outline_width_outer=outline_width,
        outline_width_inner=max(1, outline_width // 2),
    )

    # Convert styled + mask to RGBA for outlined composite
    styled_rgba = styled.convert("RGBA")
    outlined = outlined  # already RGBA

    return {
        "paper_style_url":    pil_to_base64(styled, fmt="PNG"),
        "thickness_url":     pil_to_base64(generate_thickness_map_rgb(thickness), fmt="PNG"),
        "normal_map_url":     pil_to_base64(Image.fromarray(normal), fmt="PNG"),
        "outlined_url":       pil_to_base64(outlined, fmt="PNG"),
        "thickness_gray_url": pil_to_base64(thickness_gray_pil, fmt="PNG"),
    }
