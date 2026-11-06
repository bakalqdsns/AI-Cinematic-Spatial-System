"""遮挡补全工具 —— LaMa 修复分层后被遮住的区域。

包装 ``app.services.layer_exporter.inpaint_occluded_layers`` 和
``app.utils.inpaint_utils.generate_inpaint``。

``fill_occlusions`` 的 ``inpaint_fn`` 显式可注入：测试时传一个假函数
即可完全避开 LaMa 模型；None 时才用全局 LaMa。
"""
from __future__ import annotations

from typing import Callable, Optional

import numpy as np
from PIL import Image

from app.tools._shared import ImageLike, to_pil

__all__ = ["fill_occlusions", "inpaint_image"]


def fill_occlusions(
    image: ImageLike,
    layer_imgs: dict[str, Image.Image],
    depth_meters: Optional[np.ndarray] = None,
    object_assets: Optional[list] = None,
    scene_class: Optional[str] = None,
    inpaint_fn: Optional[Callable] = None,
    reveal_band_px: Optional[int] = None,
) -> dict[str, Image.Image]:
    """把分层后被近层遮住的轮廓窄带用 inpaint 补进远层。

    可见像素保持互斥：远层在被近层遮住的像素上 alpha 仍是 0，只补两种
    洞——轮廓窄带（运镜/错位时会露出来的边）和全透明洞（只补到最远层）。

    输入:
        image: 场景原图（PIL / numpy / 路径）。
        layer_imgs: ``split_layers`` 的输出，{层名: RGBA 图}。
        depth_meters: HxW 米制深度。
        object_assets: ``detect_objects(...).objects``。
        scene_class: 闭集场景类名；None 且有物件时会现场分类（见
            ``split_layers`` 的说明）。
        inpaint_fn: 修复回调，签名
            ``inpaint_fn(rgb_image, mask_image, prompt) -> PIL Image``，
            mask 白色=待修复。None 时用本地 LaMa（``inpaint_image``）。
            测试时传 ``lambda img, mask, prompt: img`` 可避开模型。
        reveal_band_px: 轮廓窄带宽度；None 时约为图宽 2.5%。
    输出:
        dict，{层名: RGBA 图}，与输入同键；近层（foreground）不被补全。
    副作用:
        无。
    模型:
        LaMa（GPU），仅当 inpaint_fn=None 时。
    """
    from app.services.layer_exporter import inpaint_occluded_layers

    pil = to_pil(image, mode="RGB")
    return inpaint_occluded_layers(
        pil,
        dict(layer_imgs),
        depth_meters,
        object_assets=object_assets,
        scene_class=scene_class,
        inpaint_fn=inpaint_fn,
        reveal_band_px=reveal_band_px,
    )


def inpaint_image(
    base_image: ImageLike,
    mask_image: ImageLike,
    prompt: str = "occluded background",
) -> Image.Image:
    """对单张图做 LaMa 盲修复（mask 白色区域被重绘）。

    输入:
        base_image: 原始图像（PIL / numpy / 路径），至少 128x128。
        mask_image: mask 图（L 模式 255=待修复，或 RGBA 用 alpha）。
        prompt: 描述待修复区域的文本。LaMa 是盲修复模型，忽略该参数，
            保留只为兼容旧调用。
    输出:
        修复后的 PIL RGB 图，尺寸与输入一致。
    副作用:
        无（首次懒加载模型会占显存）。mask 为空或图小于 128px 抛
        ValueError。
    模型:
        LaMa big-lama（GPU），从 ``app.models.model_manager`` 懒加载。
    """
    from app.utils.inpaint_utils import generate_inpaint

    base = to_pil(base_image, mode="RGB")
    mask = mask_image if isinstance(mask_image, Image.Image) else to_pil(mask_image, mode="L")
    return generate_inpaint(base, mask, prompt)
