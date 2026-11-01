"""第 4 轮「分层明显化」：透视表带纸雕呈现字段，三视图脚本有 3/4 视角和拆解视图。

只测纯 Python 部分（不 import bpy、不跑 Blender、不动深度归层语义）：
- perspective_offsets / build_z_offset_table 每行带 thicknessM/yawDeg/pitchDeg/
  shiftXM/shiftYM，且 zOffset 仍等于 -depthMeters、最近层 scale 仍是 1。
- Blender 插件 scene_utils 的呈现默认值与后端镜像一致，读取函数清单优先、
  越界回退默认。
- view_presets.VIEW_NAMES 在 front/side/top 之外包含 front_three_quarter、
  layer_separation、exploded；exploded_x_offsets 沿 X 单调拉开、中间层不动。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

from app.services.layer_exporter import (
    LAYER_PITCH_DEG,
    LAYER_SHIFT_X_M,
    LAYER_SHIFT_Y_M,
    LAYER_THICKNESS_M,
    LAYER_YAW_DEG,
    build_z_offset_table,
    perspective_offsets,
)

_REPO = Path(__file__).resolve().parents[2]
_ADDON = _REPO / "backend" / "blender" / "addons" / "aicss_scene_builder"
_LAYER_NAMES = ("sky", "background", "midground", "ground", "foreground")


def _加载模块(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # dataclass 处理字符串注解时要按模块名查 sys.modules，先注册再执行。
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def 插件():
    return _加载模块(
        _ADDON / "utils" / "scene_utils.py", "aicss_scene_utils_round4",
    )


@pytest.fixture(scope="module")
def 视角():
    return _加载模块(
        _ADDON / "utils" / "view_presets.py", "aicss_view_presets_round4",
    )


def _透视表() -> dict:
    高, 宽 = 8, 8
    深度 = np.full((高, 宽), 3.0, dtype=np.float32)
    天空 = np.zeros((高, 宽), dtype=bool)
    天空[0:2, :] = True
    深度[天空] = 40.0
    前景 = np.zeros((高, 宽), dtype=bool)
    前景[6:8, :] = True
    深度[前景] = 2.0
    遮罩 = {
        "sky": 天空,
        "background": np.zeros((高, 宽), dtype=bool),
        "midground": np.zeros((高, 宽), dtype=bool),
        "ground": np.zeros((高, 宽), dtype=bool),
        "foreground": 前景,
    }
    return {行["layer"]: 行 for 行 in perspective_offsets(深度, 遮罩)}


def test_透视表带纸雕呈现字段且深度语义不变():
    按名 = _透视表()
    for 层 in _LAYER_NAMES:
        行 = 按名[层]
        # 深度归层语义不动：Z 仍是负深度，缩放仍是近大远小。
        assert 行["zOffset"] == -行["depthMeters"]
        # 纸雕呈现字段齐全：厚度、偏航、俯仰、水平错位。
        assert 行["thicknessM"] == LAYER_THICKNESS_M[层] > 0.0
        assert 行["yawDeg"] == LAYER_YAW_DEG[层]
        assert 行["pitchDeg"] == LAYER_PITCH_DEG[层]
        assert 行["shiftXM"] == LAYER_SHIFT_X_M[层]
        assert 行["shiftYM"] == LAYER_SHIFT_Y_M[层]
    assert 按名["foreground"]["scale"] == 1.0
    assert 按名["sky"]["scale"] > 按名["foreground"]["scale"]


def test_z_offset表也带呈现字段():
    按名 = {行["layer"]: 行 for 行 in build_z_offset_table()}
    for 层 in _LAYER_NAMES:
        行 = 按名[层]
        assert 行["thicknessM"] == LAYER_THICKNESS_M[层]
        assert 行["yawDeg"] == LAYER_YAW_DEG[层]
        assert 行["pitchDeg"] == LAYER_PITCH_DEG[层]
        assert 行["shiftXM"] == LAYER_SHIFT_X_M[层]
        assert 行["shiftYM"] == LAYER_SHIFT_Y_M[层]


def test_呈现参数不会让相邻层穿插():
    """所有层同向偏航/俯仰，幅度差不超过 0.5°，错位不超过 3m。"""
    偏航 = [LAYER_YAW_DEG[层] for 层 in _LAYER_NAMES]
    俯仰 = [LAYER_PITCH_DEG[层] for 层 in _LAYER_NAMES]
    assert max(偏航) - min(偏航) <= 0.5
    assert max(俯仰) - min(俯仰) <= 0.5
    assert all(值 > 0 for 值 in 偏航)  # 同向，不左右对转
    for 层 in _LAYER_NAMES:
        assert abs(LAYER_SHIFT_X_M[层]) <= 3.0
        assert abs(LAYER_SHIFT_Y_M[层]) <= 3.0
        # 厚度必须小于最小层间距 0.5m，且沿背面挤出才安全。
        assert 0.0 < LAYER_THICKNESS_M[层] < 0.5


def test_插件呈现默认值与后端镜像一致(插件):
    assert 插件.LAYER_THICKNESS_M == LAYER_THICKNESS_M
    assert 插件.LAYER_YAW_DEG == LAYER_YAW_DEG
    assert 插件.LAYER_PITCH_DEG == LAYER_PITCH_DEG
    assert 插件.LAYER_SHIFT_X_M == LAYER_SHIFT_X_M
    assert 插件.LAYER_SHIFT_Y_M == LAYER_SHIFT_Y_M


def test_插件读取呈现字段清单优先且越界回退(插件):
    清单 = {"zOffsets": [
        {"layer": "foreground", "zOffset": -2.0,
         "thicknessM": 0.2, "yawDeg": -3.0, "pitchDeg": 4.0,
         "shiftXM": 1.5, "shiftYM": -0.5},
        {"layer": "sky", "zOffset": -20.0,
         "thicknessM": 0.0, "yawDeg": 60.0, "shiftXM": 99.0},
    ]}
    # 清单写了就按清单。
    assert 插件.layer_thickness(清单, "foreground") == 0.2
    assert 插件.layer_yaw_deg(清单, "foreground") == -3.0
    assert 插件.layer_pitch_deg(清单, "foreground") == 4.0
    assert 插件.layer_shift(清单, "foreground") == (1.5, -0.5)
    # 越界（厚度 0、偏航 60°、错位 99m）回退默认。
    assert 插件.layer_thickness(清单, "sky") == LAYER_THICKNESS_M["sky"]
    assert 插件.layer_yaw_deg(清单, "sky") == LAYER_YAW_DEG["sky"]
    assert 插件.layer_shift(清单, "sky") == (
        LAYER_SHIFT_X_M["sky"], LAYER_SHIFT_Y_M["sky"],
    )
    # 清单没写的层用默认值。
    assert 插件.layer_thickness({}, "midground") == LAYER_THICKNESS_M["midground"]
    assert 插件.layer_yaw_deg({}, "ground") == LAYER_YAW_DEG["ground"]
    assert 插件.layer_pitch_deg({}, "ground") == LAYER_PITCH_DEG["ground"]
    assert 插件.layer_shift({}, "ground") == (
        LAYER_SHIFT_X_M["ground"], LAYER_SHIFT_Y_M["ground"],
    )


def test_视角列表含三四视角层分离和拆解视图(视角):
    名字 = set(视角.VIEW_NAMES)
    # 旧三视角保留。
    assert {"front", "side", "top"} <= 名字
    # 第 4 轮新增：3/4 视角、层分离视角、拆解视图。
    assert "front_three_quarter" in 名字
    assert "layer_separation" in 名字
    assert "exploded" in 名字


def test_拆解布局沿X单调拉开且中间层不动(视角):
    偏移 = 视角.exploded_x_offsets(_LAYER_NAMES)
    值 = [偏移[层] for 层 in _LAYER_NAMES]
    # 沿 X 单调递增（远层在左、近层在右），且真正错开。
    assert all(后 > 前 for 前, 后 in zip(值, 值[1:]))
    # 五层时中间层（midground）不动，整体左右对称。
    assert 值[2] == 0.0
    assert 值[0] == -值[-1]
    assert 值[1] == -值[-2]
    # 间距就是预设的拆解间隔。
    assert 值[1] - 值[0] == 视角.EXPLODED_X_GAP_M
    assert 视角.exploded_x_offsets([]) == {}


def test_各视角相机位置互不重叠且看向层堆中心(视角):
    中心 = (0.0, 0.0, -20.0)
    位置 = {}
    for 名字 in 视角.VIEW_NAMES:
        地点, 目标 = 视角.view_camera(名字, 中心, -2.0, 40.0, extent_x=60.0)
        assert tuple(目标) == 中心
        # 相机都在层堆靠相机的一侧（z 大于最近层）。
        assert 地点[2] > -2.0
        位置[名字] = tuple(round(v, 3) for v in 地点)
    assert len(set(位置.values())) == len(位置)
    # 拆解视角比正面拉得更远，才装得下拉开的层片。
    assert 位置["exploded"][2] > 位置["front"][2]
    # 3/4 视角和层分离视角都必须偏到一侧，否则看不到切边。
    assert 位置["front_three_quarter"][0] > 0.0
    assert 位置["layer_separation"][0] > 0.0
    with pytest.raises(ValueError):
        视角.view_camera("back", 中心, -2.0, 40.0)


def test_切边材质和层片加厚在插件里接好():
    材质 = _加载模块(
        _ADDON / "materials" / "paper_material.py", "aicss_paper_material_round4",
    )
    assert 材质.PAPER_EDGE_MATERIAL_NAME
    assert len(材质.PAPER_EDGE_COLOR) == 3
    assert callable(材质.apply_paper_edge_material)

    导入 = _加载模块(
        _ADDON / "operators" / "import_layers.py", "aicss_import_layers_round4",
    )
    assert callable(导入._add_card_thickness)
