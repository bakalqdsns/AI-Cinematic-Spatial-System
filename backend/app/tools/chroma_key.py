"""抠像工具 —— 绿幕 chroma key 与 SAM2 人物分割。

包装 ``app.services.motion_extractor`` 的抠像函数。纯 CPU 路径
（chroma key）不需要任何模型；SAM2 路径需要显式传模型句柄或退回
``app.models.model_manager`` 懒加载。
"""
from __future__ import annotations

from typing import Optional

import numpy as np

__all__ = [
    "key_greenscreen",
    "chroma_key_rgba_array",
    "is_greenscreen_frame",
    "segment_person",
    "stabilize_frames",
]

#: 默认绿幕色（BGR 纯绿 #00FF00）。
GREEN_KEY_BGR = (0, 255, 0)


def key_greenscreen(
    frame_paths: list[str],
    output_dir: str,
    threshold: int = 80,
    softness: int = 20,
) -> list[str]:
    """把一组绿幕帧抠成 RGBA PNG 序列（seg_0001.png ...）。

    幕布颜色从帧边缘自适应采样，不是写死的纯绿；只有与画面边缘连通的
    绿色区域才会变透明，衣服上的绿块不会被误抠。

    输入:
        frame_paths: 输入帧路径列表（如 ``extract_frames`` 的输出）。
        output_dir: RGBA 输出目录（自动创建）。
        threshold: 与幕布色的距离阈值，小于它 alpha 变 0。
        softness: 羽化带宽，alpha 在这段距离内从 0 渐变到 255。
    输出:
        写出的 RGBA PNG 路径列表（不可读的帧会被跳过）。
    副作用:
        向 output_dir 写 seg_*.png。
    模型:
        无（纯 numpy/OpenCV，CPU）。
    """
    from app.services.motion_extractor import chroma_key_frames_sequence

    return chroma_key_frames_sequence(
        list(frame_paths),
        output_dir,
        chroma_threshold=threshold,
        chroma_softness=softness,
    )


def chroma_key_rgba_array(
    rgba_bgr: np.ndarray,
    threshold: int = 80,
    softness: int = 20,
    key_color: tuple[int, int, int] = GREEN_KEY_BGR,
) -> np.ndarray:
    """对单张 BGRA uint8 数组做绿幕抠像（内存内，纯函数）。

    输入:
        rgba_bgr: HxWx4 uint8，BGR + alpha 通道顺序（OpenCV 约定）。
        threshold / softness: 同 ``key_greenscreen``。
        key_color: 参考幕布色（BGR），用于判定边缘是不是绿幕。
    输出:
        新的 HxWx4 uint8 数组；颜色通道原样拷贝，alpha 与输入取 min
        （已有 alpha 只会变更透明，不会被涂回来）。边缘不像绿幕时
        原样返回。
    副作用:
        无。
    模型:
        无。
    """
    from app.services.motion_extractor import chroma_key_rgba

    return chroma_key_rgba(
        rgba_bgr,
        key_color=key_color,
        threshold=threshold,
        softness=softness,
    )


def is_greenscreen_frame(
    frame_path: str,
    threshold: int = 80,
    min_ratio: float = 0.7,
) -> bool:
    """判断一帧的背景是不是绿幕（看边缘色带）。

    输入:
        frame_path: 帧文件路径。
        threshold: 与默认绿幕色的距离阈值。
        min_ratio: 边缘像素中绿幕占比达到该值才判 True。
    输出:
        bool。读不出图像时返回 False。
    副作用:
        无。
    模型:
        无。
    """
    from app.services.motion_extractor import frame_background_is_greenscreen

    return frame_background_is_greenscreen(
        frame_path,
        threshold=threshold,
        min_ratio=min_ratio,
    )


def segment_person(
    frame_path: str,
    output_path: str,
    sam2_model=None,
    min_area: int = 1000,
    feather_edges: bool = True,
    greenscreen: bool = False,
    threshold: int = 80,
    softness: int = 20,
) -> bool:
    """用 SAM2 从单帧里抠出人物，写 RGBA PNG。

    输入:
        frame_path: 输入帧路径。
        output_path: 输出 RGBA PNG 路径。
        sam2_model: 预加载的 SAM2 模型句柄（``model_manager.sam2``）。
            None 时尝试从 ``app.models.model_manager`` 懒加载——显式传
            句柄可以避免依赖全局单例，也便于测试注入假模型。
        min_area: 小于该面积的 mask 丢弃。
        feather_edges: 是否把 SAM2 mask 吸附到附近 Canny 边缘。
        greenscreen: True 时在 SAM2 alpha 上再叠一次 chroma key。
        threshold / softness: chroma key 参数（greenscreen=True 时生效）。
    输出:
        bool，是否成功写出文件。
    副作用:
        成功时向 output_path 写 RGBA PNG。
    模型:
        SAM2（GPU）；sam2_model=None 且模型未加载/缺失时返回 False。
    """
    from app.services.motion_extractor import segment_person_from_frame

    if sam2_model is None:
        try:
            from app.models.model_manager import model_manager

            sam2_model = model_manager.sam2
        except Exception:
            return False

    return segment_person_from_frame(
        frame_path,
        output_path,
        sam2_model,
        min_area=min_area,
        feather_edges=feather_edges,
        greenscreen=greenscreen,
        chroma_threshold=threshold,
        chroma_softness=softness,
    )


def stabilize_frames(
    frame_paths: list[str],
    output_dir: Optional[str] = None,
    anchor_x: float = 0.5,
    anchor_y: float = 0.95,
) -> list[str]:
    """钉住抠像序列里人物的位置和大小（纯 CPU，无模型）。

    对每张 RGBA seg 帧取 ``alpha > 0`` 的人物包围盒，先把所有帧包围盒
    高度等比缩放到全序列中位高度（人物不再忽大忽小），再整数像素平移，
    使包围盒底边中点（脚底）落在画布 ``(anchor_x*W, anchor_y*H)`` 处。
    帧内人物被钉死后，横向位移可以完全交给 Blender 平面的 X 线性动画，
    人物看起来就是稳定地平行横过画面。移出画布的部分裁掉，空出区域
    alpha 为 0；没有 alpha 像素的帧原样写出并记日志。

    输入:
        frame_paths: 抠好的 RGBA PNG 序列（``seg_0001.png`` …，如
            ``key_greenscreen`` 的输出）。
        output_dir: 输出目录；None 时写到原目录下 ``stabilized/``
            子目录。文件名保持 ``seg_XXXX.png``，传原目录即原地覆盖。
        anchor_x / anchor_y: 脚底锚点的归一化画布坐标（默认水平居中、
            纵向 95% 处）。
    输出:
        写出的 PNG 路径列表。
    副作用:
        向 output_dir 写 PNG。
    模型:
        无（纯 numpy/OpenCV，CPU）。
    """
    from app.services.motion_extractor import stabilize_segmented_frames

    return stabilize_segmented_frames(
        list(frame_paths),
        output_dir,
        anchor_x=anchor_x,
        anchor_y=anchor_y,
    )
