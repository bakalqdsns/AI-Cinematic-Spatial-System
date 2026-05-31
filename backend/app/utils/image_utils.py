"""
Utility functions for image/depth processing.
"""
import io
import base64
import numpy as np
from PIL import Image
from typing import Union


def pil_to_base64(img: Image.Image, format: str = "PNG") -> str:
    """Convert a PIL Image to a base64 data URL."""
    buf = io.BytesIO()
    img.save(buf, format=format)
    buf.seek(0)
    data = base64.b64encode(buf.read()).decode("utf-8")
    return f"data:image/{format.lower()};base64,{data}"


def base64_to_pil(data_url: str) -> Image.Image:
    """Convert a base64 data URL to a PIL Image."""
    if data_url.startswith("data:"):
        data_url = data64 = data_url.split(",", 1)[1]
    else:
        data64 = data_url
    raw = base64.b64decode(data64)
    return Image.open(io.BytesIO(raw)).convert("RGB")


def load_image_from_url_or_base64(url_or_base64: str) -> Image.Image:
    """
    Load an image from either:
      - A HTTP/HTTPS URL (fetched via httpx)
      - A base64 data URL
      - A plain base64 string
    Returns a PIL RGB image.
    """
    if url_or_base64.startswith("data:image"):
        return base64_to_pil(url_or_base64)
    elif url_or_base64.startswith("http"):
        import httpx
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url_or_base64)
            resp.raise_for_status()
            return Image.open(io.BytesIO(resp.content)).convert("RGB")
    else:
        # Assume plain base64
        return base64_to_pil(url_or_base64)


def numpy_to_pil_depth(depth: np.ndarray, cmap: str = "gray") -> Image.Image:
    """
    Convert a normalized depth array (0-1 or raw) to a PIL Image.
    Applies a colormap for visualization.
    """
    depth_vis = ((depth - depth.min()) / (depth.max() - depth.min() + 1e-6) * 255).astype(np.uint8)
    if cmap == "gray":
        return Image.fromarray(depth_vis, mode="L")
    else:
        import cv2
        depth_color = cv2.applyColorMap(depth_vis, cv2.COLORMAP_INFERNO)
        return Image.fromarray(depth_color[:, :, ::-1])


def depth_to_meters(depth_norm: np.ndarray, scale: float = 50.0) -> np.ndarray:
    """Scale normalized depth to approximate meters."""
    return depth_norm * scale


def create_layer_mask(
    depth_meters: np.ndarray,
    z_min: float,
    z_max: float,
) -> np.ndarray:
    """Create a binary mask for pixels within a depth range."""
    mask = (depth_meters >= z_min) & (depth_meters < z_max)
    return mask.astype(np.uint8) * 255


def apply_mask_to_image(
    image: Image.Image,
    mask: np.ndarray,
) -> Image.Image:
    """Apply a binary mask to an image (zero out masked-out regions)."""
    image_np = np.array(image)
    mask_3ch = np.stack([mask, mask, mask], axis=-1)
    masked = image_np * (mask_3ch > 0).astype(np.uint8)
    return Image.fromarray(masked)


def create_rgba_from_masked_image(
    image: Image.Image,
    mask: np.ndarray,
    bg_color: tuple[int, int, int] = (0, 0, 0),
) -> Image.Image:
    """
    Create an RGBA image from an RGB image + binary mask.
    Pixels outside the mask become transparent.
    """
    rgb = np.array(image.convert("RGB"))
    alpha = (mask > 0).astype(np.uint8) * 255
    rgba = np.dstack([rgb, alpha])
    return Image.fromarray(rgba, mode="RGBA")


def bbox_to_xywh(box: np.ndarray, image_width: int, image_height: int) -> dict:
    """Convert [x1,y1,x2,y2] to normalized {x,y,w,h}."""
    x1, y1, x2, y2 = box
    return {
        "x": float(x1 / image_width),
        "y": float(y1 / image_height),
        "w": float((x2 - x1) / image_width),
        "h": float((y2 - y1) / image_height),
    }


def estimate_depth_from_bbox(
    depth_map: np.ndarray,
    bbox: dict,
    image_width: int,
    image_height: int,
) -> float:
    """Estimate median depth within a bounding box region."""
    x1 = int(bbox["x"] * image_width)
    y1 = int(bbox["y"] * image_height)
    x2 = int((bbox["x"] + bbox["w"]) * image_width)
    y2 = int((bbox["y"] + bbox["h"]) * image_height)
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(image_width, x2), min(image_height, y2)
    if x2 <= x1 or y2 <= y1:
        return 10.0
    region = depth_map[y1:y2, x1:x2]
    return float(np.median(region))


def rotate_image_90(img: Image.Image, k: int) -> Image.Image:
    """Rotate image by k*90 degrees counterclockwise."""
    return img.rotate(k * 90, expand=True, fillcolor=(0, 0, 0, 0) if img.mode == "RGBA" else (0, 0, 0))


def flip_image(img: Image.Image, direction: str) -> Image.Image:
    """Flip image: 'horizontal', 'vertical', or 'both'."""
    if direction == "horizontal":
        return img.transpose(Image.FLIP_LEFT_RIGHT)
    elif direction == "vertical":
        return img.transpose(Image.FLIP_TOP_BOTTOM)
    elif direction == "both":
        return img.transpose(Image.FLIP_TOP_BOTTOM).transpose(Image.FLIP_LEFT_RIGHT)
    return img
