"""透视层距表工具 —— 按米制深度摆放五层平面的 Z / 缩放表。

包装 ``app.services.layer_exporter.perspective_offsets`` 和
``build_z_offset_table``。输出是 Blender 插件直接消费的 dict 列表。
纯函数，不需要模型。
"""
from __future__ import annotations

from typing import Optional

import numpy as np

__all__ = ["perspective_offsets", "z_offset_table"]


def perspective_offsets(
    depth_meters: Optional[np.ndarray] = None,
    masks: Optional[dict[str, np.ndarray]] = None,
) -> list[dict]:
    """按深度图和各层 mask 算每层的摆放深度与近大远小缩放。

    相机在 +Z 朝 -Z 看，平面 Z 取负的深度（越负越远）。实测中位数如果
    破坏远→近的单调性，就把远层再推远，不交换层名。最近一层 scale=1，
    越远越大，保证默认相机位置下远层不会缩成一个点。

    输入:
        depth_meters: HxW 米制深度；None 时全部用默认层距。
        masks: {层名: HxW bool mask}（``layer_masks`` 的输出）；缺的层
            用默认层距。
    输出:
        dict 列表，固定按 sky → background → midground → ground →
        foreground 顺序，每行含:
        layer / depthMeters / zOffset / zMin / zMax / scale /
        thicknessM / yawDeg / pitchDeg / shiftXM / shiftYM。
        后五个是纸雕呈现字段，只给 Blender 摆层片用。
    副作用:
        无。
    模型:
        无。
    """
    from app.services.layer_exporter import perspective_offsets as _offsets

    return _offsets(depth_meters, dict(masks or {}))


def z_offset_table() -> list[dict]:
    """返回五层的默认 Z 偏移表（Blender 插件的兜底表）。

    输入: 无。
    输出:
        dict 列表，字段与 ``perspective_offsets`` 相同，但深度取自
        固定默认（sky=-20, background=-12, midground=-8, ground=-4,
        foreground=-2），zMin/zMax 用旧的固定米制区间。
    副作用:
        无。
    模型:
        无。
    """
    from app.services.layer_exporter import build_z_offset_table

    return build_z_offset_table()
