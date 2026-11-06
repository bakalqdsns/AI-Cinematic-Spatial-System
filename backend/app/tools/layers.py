"""分层工具 —— 把场景图按深度和语义切成五层 RGBA。

包装 ``app.services.layer_exporter``。输出五张 PIL RGBA 图或五张互斥
bool mask：sky / background / midground / ground / foreground。
纯计算，不需要 GPU 模型（深度图和物件由调用方喂入）。
"""
from __future__ import annotations

from typing import Optional

import numpy as np
from PIL import Image

from app.tools._shared import ImageLike, to_pil

__all__ = ["split_layers", "layer_masks"]

#: 层名固定五层，从远到近。
LAYER_NAMES = ("sky", "background", "midground", "ground", "foreground")


def split_layers(
    image: ImageLike,
    depth_meters: Optional[np.ndarray] = None,
    object_assets: Optional[list] = None,
    scene_class: Optional[str] = None,
    feather_px: int = 1,
    layers: Optional[list[str]] = None,
) -> dict[str, Image.Image]:
    """把场景图切成五层 RGBA（属于该层的像素保留 RGB，其余全透明）。

    归层规则：物件先按场景类匹配表归层，表里没有的贴各层深度中位数；
    剩余像素跟已归物件的深度中位数走。重叠时更近的层拿走可见像素，
    各层可见像素互斥。

    输入:
        image: PIL 图像 / numpy 数组 / 图像文件路径。
        depth_meters: HxW 米制深度（``estimate_depth`` 的输出），形状
            必须与图像一致；None 时走固定米制区间的旧路径。
        object_assets: ``detect_objects(...).objects``；None 或空列表时
            同样走旧路径。
        scene_class: 闭集场景类名（``classify_scene`` 的输出）。None 且
            传了物件时会现场调 LLM 分类——离线/测试请显式传类名。
        feather_px: 层间边界羽化半径，0 为硬边。
        layers: 只导出这些层；None 时五层全导出。
    输出:
        dict，{层名: PIL RGBA 图}；没有像素的层是全透明图。
    副作用:
        无。
    模型:
        无（scene_class=None 且有物件时例外：会现场调本地 LLM 分类）。
    """
    from app.services.layer_exporter import export_layers

    pil = to_pil(image, mode="RGB")
    return export_layers(
        pil,
        depth_meters,
        layers=layers,
        feather_px=feather_px,
        object_assets=object_assets,
        scene_class=scene_class,
    )


def layer_masks(
    height: int,
    width: int,
    depth_meters: Optional[np.ndarray] = None,
    object_assets: Optional[list] = None,
    scene_class: str = "unknown",
) -> dict[str, np.ndarray]:
    """生成互斥的五层 bool mask（纯函数，不调 LLM）。

    输入:
        height / width: 图像尺寸。
        depth_meters: HxW 米制深度；形状不是 (height, width) 时剩余像素
            不按深度分配。
        object_assets: ``detect_objects(...).objects``。
        scene_class: 闭集场景类名（必须显式给；未知就传 "unknown"）。
    输出:
        dict，{层名: (height, width) bool numpy 数组}；任一像素最多
        属于一层，没有像素的层全 False。
    副作用:
        无。
    模型:
        无。
    """
    from app.services.layer_exporter import build_scene_layer_masks

    return build_scene_layer_masks(
        height=int(height),
        width=int(width),
        depth_meters=depth_meters,
        object_assets=object_assets,
        scene_class=scene_class,
    )
