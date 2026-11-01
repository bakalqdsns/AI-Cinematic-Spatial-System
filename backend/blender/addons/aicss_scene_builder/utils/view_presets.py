"""观察视角预设 —— 纯 Python（不 import bpy），Blender 脚本和 pytest 共用。

第 4 轮「分层明显化」在 front / side / top 之外新增三个观察角度：

  * ``front_three_quarter`` —— 经典 3/4 视角：右侧、略高，仍能看到正面内容，
    同时露出卡片切边。
  * ``layer_separation`` —— 低角度贴着层堆右侧看，卡片边缘和缝隙最清楚。
  * ``exploded`` —— 拆解视图：层片先沿 X 方向拉开（``exploded_x_offsets``），
    再从略高的前上方整体看。

render_three_views.py 按 ``VIEW_NAMES`` 的顺序逐一出图。
"""
from __future__ import annotations

# 出图顺序。exploded 需要临时移动层片，排在最后。
VIEW_NAMES: tuple[str, ...] = (
    "front",
    "side",
    "top",
    "front_three_quarter",
    "layer_separation",
    "exploded",
)

# 拆解视图里相邻层沿 X 拉开的距离（米）。
EXPLODED_X_GAP_M = 14.0


def exploded_x_offsets(layers_far_to_near, gap: float = EXPLODED_X_GAP_M) -> dict:
    """拆解布局：远层在左、近层在右，中间层不动。返回 ``{layer: dx}``。

    单调错开，渲完由调用方把层片移回原位。
    """
    names = list(layers_far_to_near)
    if not names:
        return {}
    mid = (len(names) - 1) / 2.0
    return {name: (index - mid) * float(gap) for index, name in enumerate(names)}


def view_camera(name, center, near_z, span_z, extent_x: float = 0.0):
    """返回 ``(location, target)``，各是 ``(x, y, z)`` 三元组。

    Args:
        name: ``VIEW_NAMES`` 里的视角名。
        center: 层堆中心（通常 x/y 为 0，z 为各层 Z 的均值）。
        near_z: 最近一层的 Z（相机一侧）。
        span_z: 最远到最近的 Z 跨度。
        extent_x: 仅 ``exploded`` 用 —— 层片沿 X 拉开后布局的 X 半宽，
            相机按它拉远，保证整个拆解布局进取景框。
    """
    cx, cy, cz = (float(v) for v in center)
    near_z = float(near_z)
    span_z = max(0.0, float(span_z))
    front = max(18.0, span_z + 8.0)

    if name == "front":
        return (cx, cy, near_z + front), (cx, cy, cz)
    if name == "side":
        # 纯侧面只能看到切边，带一点朝向正面的角度。
        return (cx + 24.0, cy + 2.0, near_z + 10.0), (cx, cy, cz)
    if name == "top":
        return (cx + 4.0, cy + 22.0, near_z + 8.0), (cx, cy, cz)
    if name == "front_three_quarter":
        # 右侧、略高的 3/4 位置，正面内容和卡片切边都看得见。
        d = max(20.0, span_z + 10.0)
        return (cx + d * 0.55, cy + d * 0.30, near_z + d * 0.75), (cx, cy, cz)
    if name == "layer_separation":
        # 低角度贴右侧看层堆，缝隙和每层厚度的阶梯感最清楚。
        return (cx + 30.0, cy + 10.0, near_z + 4.0), (cx, cy, cz)
    if name == "exploded":
        # 相机拉远到能装下整个拆解布局（FOV 35°，水平半角 tan ≈ 0.315，
        # 留 25% 余量），位置略偏、略高，能看出卡片的前后次序。
        half_tan = 0.315
        d = max(front, float(extent_x) * 1.25 / half_tan)
        return (cx + d * 0.18, cy + d * 0.22, near_z + d), (cx, cy, cz)
    raise ValueError(f"未知视角: {name}")
