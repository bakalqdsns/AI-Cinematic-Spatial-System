"""深度估计工具 —— Depth Anything V2 米制深度。

包装 ``app.models.depth_loader.DepthModel.predict_meters``。模型句柄显式传，
``None`` 时才退回 ``app.models.model_manager`` 懒加载。
"""
from __future__ import annotations

import numpy as np

from app.tools._shared import ImageLike, to_pil

__all__ = ["estimate_depth"]


def estimate_depth(
    image: ImageLike,
    scale: float = 50.0,
    depth_model=None,
) -> np.ndarray:
    """估计单张图像的米制深度图。

    输入:
        image: PIL 图像 / numpy 数组（HxWx3）/ 图像文件路径。
        scale: 深度映射的最远米数；输出 0 附近为近处，最大约 ``scale`` 米。
        depth_model: 预加载的 DepthModel 句柄（需有
            ``predict_meters(pil_image, scale=...)`` 方法）。None 时从
            ``app.models.model_manager`` 懒加载——显式传句柄可以避免依赖
            全局单例，也便于测试注入假模型。
    输出:
        HxW float32 numpy 数组，单位米，数值越大越远。
    副作用:
        无（首次懒加载模型会占显存）。
    模型:
        Depth Anything V2 Large（GPU）。
    """
    pil = to_pil(image, mode="RGB")
    if depth_model is None:
        from app.models.model_manager import model_manager

        depth_model = model_manager.depth_model
    return depth_model.predict_meters(pil, scale=scale)
