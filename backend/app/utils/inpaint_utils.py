"""
图像修复 (Inpainting) 工具。

使用本地 LaMa 模型进行图像修复，替换了之前的 DashScope WanEdit API。
LaMa 是基于 Fourier 卷积的高质量图像修复模型。

参考: https://github.com/advimman/lama
pip: simple-lama-inpainting

Mask 语义：
  - 白色区域 (255) = 待修复区域（生成内容）
  - 黑色区域 (0)   = 保留区域（保持原样）
"""

import base64
import io
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

from app.models.model_manager import model_manager

DEBUG_INPAINT_MASK = os.environ.get("DEBUG_INPAINT_MASK") == "1"
DEBUG_INPAINT_OUTPUT_DIR = os.environ.get("AICSS_INPAINT_DEBUG_DIR", "")


def _write_debug_image(filename: str, image: Image.Image, *, format: str | None = None) -> Path | None:
    """在启用调试时，将图像写入临时目录或指定目录。"""
    if not DEBUG_INPAINT_MASK and not DEBUG_INPAINT_OUTPUT_DIR:
        return None

    target_dir = Path(DEBUG_INPAINT_OUTPUT_DIR) if DEBUG_INPAINT_OUTPUT_DIR else Path(tempfile.gettempdir()) / "aicss_inpaint_debug"
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / filename
    image.save(path, format=format)
    return path


def _compute_resize_ratio(
    img_size: tuple[int, int],
    target_max_dim: int = 1024,
) -> float:
    """
    计算缩放比例，使图像不超过 target_max_dim 像素的边长。
    如果图像已经在限制内，返回 1.0。

    LaMa 模型对输入尺寸有限制，默认限制为 1024。
    """
    w, h = img_size
    longest = max(w, h)
    if longest <= target_max_dim:
        return 1.0
    return target_max_dim / longest


def _encode_image_for_lama(img: Image.Image, target_max_dim: int = 1024) -> tuple[Image.Image, tuple[int, int]]:
    """
    为 LaMa 模型准备图像。
    
    1. RGBA → RGB 转换（白色背景合成）
    2. 按比例缩放以满足尺寸限制
    
    Returns:
        (processed_image, original_size) - 处理后的图像和原始尺寸
    """
    orig_size = img.size
    
    # RGBA → RGB：白色背景合成（alpha 混合）
    if img.mode == "RGBA":
        rgb = Image.new("RGB", img.size, (255, 255, 255))
        rgb.paste(img, mask=img.split()[3])
        img = rgb
    elif img.mode != "RGB":
        img = img.convert("RGB")
    
    # 计算缩放比例
    ratio = _compute_resize_ratio(img.size, target_max_dim)
    
    if ratio < 1.0:
        new_w = max(256, int(img.size[0] * ratio))
        new_h = max(256, int(img.size[1] * ratio))
        img = img.resize((new_w, new_h), Image.LANCZOS)
    
    return img, orig_size


def _encode_mask_for_lama(mask_img: Image.Image, target_size: tuple[int, int]) -> Image.Image:
    """
    将 mask 图像调整为与目标图像相同的尺寸。
    
    Args:
        mask_img: 原始 mask 图像
                  - RGBA: alpha=255（物体=待修复），alpha=0（背景=保留）
                  - L: 255=待修复, 0=保留
        target_size: 目标尺寸 (width, height)
    
    Returns:
        调整大小后的 L 模式 mask 图像，白色区域=待修复
    """
    if mask_img.mode == "RGBA":
        alpha = mask_img.split()[3]
    elif mask_img.mode == "L":
        alpha = mask_img
    else:
        alpha = mask_img.convert("L")
    
    # 调整为与原图相同的尺寸
    if alpha.size != target_size:
        alpha = alpha.resize(target_size, Image.NEAREST)
    
    return alpha


def compute_mask_white_ratio(mask_image: Image.Image) -> float:
    """
    统计 mask 中"待修复区域"占比。
    """
    if mask_image.mode == "RGBA":
        alpha = mask_image.split()[3]
    else:
        alpha = mask_image.convert("L")
    arr = np.array(alpha)
    return float((arr > 0).mean())


def generate_inpaint(
    base_image: Image.Image,
    mask_image: Image.Image,
    prompt: str,
) -> Image.Image:
    """
    使用本地 LaMa 模型进行图像修复。

    Args:
        base_image: 原始 RGB 图像（PIL Image）
        mask_image:  mask 图像
                     - RGBA: alpha=255（物体=待修复），alpha=0（背景=保留）
                     - L: 255=待修复, 0=保留
        prompt:      描述 mask 白色区域应填充的内容（LaMa 忽略此参数，但保留以兼容 API）

    Returns:
        修复后的 PIL Image (RGB)
    """
    w, h = base_image.size
    if w < 128 or h < 128:
        raise ValueError(
            f"Image too small: {w}x{h}px. LaMa requires at least 128x128 pixels."
        )

    logger.debug("[inpaint] base_image: %s, mode=%s", base_image.size, base_image.mode)
    logger.debug("[inpaint] mask_image: %s, mode=%s", mask_image.size, mask_image.mode)

    # 分析原始 mask
    if mask_image.mode == "RGBA":
        alpha = mask_image.split()[3]
    else:
        alpha = mask_image.convert("L")
    alpha_arr = np.array(alpha)
    white_ratio = (alpha_arr > 0).mean()
    logger.debug("[inpaint] mask non-zero ratio: %.4f", white_ratio)

    if white_ratio < 0.001:
        raise ValueError(
            f"Mask is empty or nearly empty ({white_ratio*100:.2f}% non-zero pixels). "
            "Please select an area to inpaint before submitting."
        )

    if white_ratio < 0.05:
        logger.warning("[inpaint] mask is very small (%.2f%% of pixels). "
                      "Results may be similar to the original image.", white_ratio * 100)

    # 准备图像和 mask
    processed_image, orig_size = _encode_image_for_lama(base_image)
    processed_mask = _encode_mask_for_lama(mask_image, processed_image.size)

    # 保存调试文件
    try:
        if DEBUG_INPAINT_MASK or DEBUG_INPAINT_OUTPUT_DIR:
            debug_mask_path = _write_debug_image("lama_mask.png", processed_mask)
            if debug_mask_path:
                logger.debug("[inpaint DEBUG] mask saved: %s", debug_mask_path)
            
            debug_image_path = _write_debug_image("lama_image.png", processed_image)
            if debug_image_path:
                logger.debug("[inpaint DEBUG] image saved: %s", debug_image_path)
    except Exception as e:
        logger.debug("[inpaint DEBUG] debug save failed: %s", e)

    # 调用 LaMa 模型
    lama = model_manager.lama_model
    result = lama.predict(processed_image, processed_mask)

    # 如果处理后的图像尺寸与原始尺寸不同，需要将结果调整回原始尺寸
    if result.size != orig_size:
        logger.debug("[inpaint] Resizing result from %s to %s", result.size, orig_size)
        result = result.resize(orig_size, Image.LANCZOS)

    # 保存结果调试文件
    try:
        if DEBUG_INPAINT_MASK or DEBUG_INPAINT_OUTPUT_DIR:
            result_path = _write_debug_image("lama_result.png", result)
            if result_path:
                logger.debug("[inpaint DEBUG] result saved: %s", result_path)
    except Exception as e:
        logger.debug("[inpaint DEBUG] debug save failed: %s", e)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Prompt & mode guidance (保留用于兼容性和文档)
# ─────────────────────────────────────────────────────────────────────────────

WEAK_PROMPT_KEYWORDS_ZH = {
    "补全", "补", "修复", "还原", "自然背景", "背景", "填补",
    "继续", "延伸", "保持原", "原样", "原画面", "原构图",
}
WEAK_PROMPT_KEYWORDS_EN = {
    "inpaint", "fill", "fix", "restore", "natural background",
    "background", "continue", "extend", "keep original", "same as before",
    "repair",
}


def detect_weak_prompt(prompt: str) -> dict | None:
    """
    检测 prompt 是否属于"弱 prompt"——即根据经验几乎只引导模型做延续式修补。

    注意：LaMa 是盲修复模型，不使用 prompt 参数。但保留此函数以兼容 API。
    """
    if not prompt:
        return {
            "code": "empty_prompt",
            "reason": "Prompt is empty. LaMa will perform blind inpainting based on context.",
            "matched": [],
            "suggested": "LaMa ignores prompts and fills based on surrounding context.",
        }

    normalized = prompt.strip().lower()
    tokens = set()
    for kw in WEAK_PROMPT_KEYWORDS_ZH:
        if kw in prompt:
            tokens.add(kw)
    for kw in WEAK_PROMPT_KEYWORDS_EN:
        if kw in normalized:
            tokens.add(kw)

    if tokens and len(prompt.strip()) < 12:
        return {
            "code": "weak_prompt",
            "reason": (
                f"Prompt is very short and contains filler keywords ({sorted(tokens)!r}). "
                "LaMa ignores prompts anyway and fills based on surrounding context."
            ),
            "matched": sorted(tokens),
            "suggested": "LaMa performs context-based inpainting; the prompt is not used.",
        }

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Image & Video Generation wrappers (DashScope) - 保留用于其他图像生成功能
# ─────────────────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)


async def generate_image(
    prompt: str,
    model: str = "wanx-v1",
    size: str = "1024*1024",
    n: int = 1,
) -> Optional[dict]:
    """
    Generate image via DashScope text-to-image API.
    Returns dict with 'url' or 'base64' key.
    """
    try:
        from dashscope import ImageSynthesis

        response = ImageSynthesis.call(
            model=model,
            prompt=prompt,
            size=size,
            n=n,
        )

        if response.status_code == 200:
            result = response.output
            if hasattr(result, "images") and result.images:
                return {"url": result.images[0].url, "model": model}
            elif hasattr(result, "image_url"):
                return {"url": result.image_url, "model": model}
        else:
            logger.warning(f"Image generation failed: {response.message}")
    except Exception as e:
        logger.warning(f"Image generation error: {e}")
    return None


async def generate_video(
    prompt: str,
    model: str = "wanx-i2v",
    first_frame_b64: Optional[str] = None,
    last_frame_b64: Optional[str] = None,
    duration: float = 5.0,
) -> Optional[dict]:
    """
    Generate video via DashScope Wan 2.7-i2v.
    Returns dict with 'task_id', 'status', 'video_url' (when completed).
    """
    try:
        import dashscope
        from dashscope.api.entities.dashscope import FilmConcurrentRequest

        request = FilmConcurrentRequest(
            model=model,
            prompt=prompt,
        )

        if first_frame_b64:
            request.add_clip_first_frame(
                image=first_frame_b64,
                duration=duration,
            )

        if last_frame_b64:
            request.add_clip_last_frame(
                image=last_frame_b64,
                duration=1.0,
            )

        task_response = dashscope.Film.call(request=request)

        if task_response.status == 200:
            return {
                "task_id": task_response.output.task_id,
                "status": "pending",
                "model": model,
            }
        else:
            logger.warning(f"Video generation task failed: {task_response.message}")
    except Exception as e:
        logger.warning(f"Video generation error: {e}")
    return None


async def poll_video_task(task_id: str, max_wait: int = 300) -> Optional[dict]:
    """
    Poll DashScope video task until completion.
    Uses exponential backoff: [5, 10, 15, 20, 30, 30, ...]
    Returns dict with 'status', 'video_url' or 'error'.
    """
    try:
        import dashscope
        import time

        # 指数退避轮询间隔序列
        poll_intervals = [5, 10, 15, 20, 30]
        elapsed = 0
        poll_idx = 0

        while elapsed < max_wait:
            status_resp = dashscope.Film.fetch(task_id=task_id)
            task_status = status_resp.output.task_status

            if task_status == "succeed":
                return {"status": "succeed", "video_url": status_resp.output.video.video_url}
            elif task_status in ("failed", "error"):
                return {"status": task_status, "error": str(status_resp.output)}

            # 获取当前轮询间隔（指数退避）
            interval = poll_intervals[min(poll_idx, len(poll_intervals) - 1)]
            time.sleep(interval)
            elapsed += interval
            poll_idx += 1

        return {"status": "timeout", "error": f"Task did not complete within {max_wait}s"}
    except Exception as e:
        return {"status": "error", "error": str(e)}
