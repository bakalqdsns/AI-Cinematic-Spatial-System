"""第 6 轮：人物行走轨迹和比例。

- 人物不再贴地面层（16m 深处太小），落到 ground 与 foreground 之间
  靠前景 0.35 处（当前分层约 -7.0m），1.6m 身高在画面里读得出来。
- 多帧角色带 walkFromX/walkToX 行走区间（默认 -3 → +3），Blender 端
  按帧线性插值出从左到右的位移。
- 人物缩放仍按真实身高（默认 1.6m）和帧内占比换算。
- Blender 插件的人物默认值与后端镜像一致。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from PIL import Image

from app.services.shot_archiver import (
    _CHARACTER_DEPTH_FROM_FOREGROUND,
    _CHARACTER_GROUND_CLEARANCE_M,
    _CHARACTER_WALK_FROM_X,
    _CHARACTER_WALK_TO_X,
    _DEFAULT_CHARACTER_HEIGHT_M,
    _place_characters_on_ground,
)

_REPO = Path(__file__).resolve().parents[2]
_ADDON = _REPO / "backend" / "blender" / "addons" / "aicss_scene_builder"


def _加载模块(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def 插件():
    return _加载模块(
        _ADDON / "operators" / "import_layers.py", "aicss_import_layers_round6",
    )


_Z_OFFSETS = [
    {"layer": "sky", "zOffset": -50.0},
    {"layer": "background", "zOffset": -38.0},
    {"layer": "midground", "zOffset": -16.8},
    {"layer": "ground", "zOffset": -16.3},
    {"layer": "foreground", "zOffset": -2.0},
]


def _帧目录(tmp_path: Path, *, 占比: float = 0.5, 尺寸: tuple[int, int] = (100, 100)) -> str:
    """造一个帧目录：中间帧 alpha 只在垂直方向中间 `占比` 一段不透明。"""
    frames = tmp_path / "frames"
    frames.mkdir()
    for i in range(3):
        im = Image.new("RGBA", 尺寸, (0, 0, 0, 0))
        顶 = int(尺寸[1] * (1 - 占比) / 2)
        底 = 顶 + int(尺寸[1] * 占比)
        for y in range(顶, 底):
            for x in range(尺寸[0] // 4, 尺寸[0] * 3 // 4):
                im.putpixel((x, y), (255, 255, 255, 255))
        im.save(frames / f"frame_{i:04d}.png")
    return str(frames)


def test_人物放在前景与地面之间更近的深度():
    chars = [{"id": "girl", "name": "小女孩", "framesDir": "", "frameCount": 1, "fps": 24}]
    placed = _place_characters_on_ground(chars, _Z_OFFSETS)
    assert len(placed) == 1
    z = placed[0]["position"][2]
    地面 = next(r["zOffset"] for r in _Z_OFFSETS if r["layer"] == "ground")
    前景 = next(r["zOffset"] for r in _Z_OFFSETS if r["layer"] == "foreground")
    # 在两层之间、从前景往地面走 0.35：-2 + (-16.3+2) * 0.35 ≈ -7.0。
    期望 = 前景 + (地面 - 前景) * _CHARACTER_DEPTH_FROM_FOREGROUND
    assert z == pytest.approx(期望)
    assert -9.0 < z < -5.0
    # 不再贴着 16m 深的地面层，也不越过前景层。
    assert abs(z - 地面) > 5.0
    assert abs(z - 前景) > 1.0


def test_多帧角色带行走轨迹字段且从起点落位():
    chars = [{"id": "girl", "framesDir": "", "frameCount": 45, "fps": 24}]
    placed = _place_characters_on_ground(chars, _Z_OFFSETS)
    row = placed[0]
    assert row["walkFromX"] == _CHARACTER_WALK_FROM_X == -3.0
    assert row["walkToX"] == _CHARACTER_WALK_TO_X == 3.0
    # position 的 X 取行走起点，首帧姿势和轨迹一致。
    assert row["position"][0] == _CHARACTER_WALK_FROM_X


def test_单帧角色不写行走字段():
    chars = [{"id": "girl", "framesDir": "", "frameCount": 1, "fps": 24}]
    placed = _place_characters_on_ground(chars, _Z_OFFSETS)
    assert "walkFromX" not in placed[0]
    assert "walkToX" not in placed[0]
    assert placed[0]["position"][0] == 0.0


def test_已写行走区间的角色不被覆盖():
    chars = [{
        "id": "girl",
        "framesDir": "",
        "frameCount": 24,
        "fps": 24,
        "walkFromX": -1.0,
        "walkToX": 1.5,
    }]
    placed = _place_characters_on_ground(chars, _Z_OFFSETS)
    assert placed[0]["walkFromX"] == -1.0
    assert placed[0]["walkToX"] == 1.5
    assert placed[0]["position"][0] == -1.0


def test_分层表缺前景层时回退贴地面层():
    缺前景 = [r for r in _Z_OFFSETS if r["layer"] != "foreground"]
    chars = [{"id": "girl", "framesDir": "", "frameCount": 1, "fps": 24}]
    placed = _place_characters_on_ground(chars, 缺前景)
    地面 = next(r["zOffset"] for r in 缺前景 if r["layer"] == "ground")
    z = placed[0]["position"][2]
    assert z == pytest.approx(地面 + _CHARACTER_GROUND_CLEARANCE_M)


def test_人物缩放按真实身高和帧内占比(tmp_path: Path):
    frames_dir = _帧目录(tmp_path, 占比=0.5)
    chars = [{"id": "girl", "framesDir": frames_dir, "frameCount": 3, "fps": 24}]
    placed = _place_characters_on_ground(chars, _Z_OFFSETS)
    sx, sy = placed[0]["scale"]
    # 人物占帧高一半 → 平面高 = 1.6 / 0.5 = 3.2m，方帧不拉变形。
    assert sy == pytest.approx(_DEFAULT_CHARACTER_HEIGHT_M / 0.5, abs=0.05)
    assert sx == pytest.approx(sy, abs=1e-6)
    # 不再是拍脑袋的 4.0。
    assert sy != 4.0


def test_没有帧目录时按默认占比给身高缩放():
    chars = [{"id": "girl", "framesDir": "", "frameCount": 0, "fps": 24}]
    placed = _place_characters_on_ground(chars, _Z_OFFSETS)
    sx, sy = placed[0]["scale"]
    期望 = _DEFAULT_CHARACTER_HEIGHT_M / 0.9
    assert sy == pytest.approx(期望, abs=0.01)
    assert sx == pytest.approx(期望, abs=0.01)


def test_已写位置和缩放的角色不动(tmp_path: Path):
    frames_dir = _帧目录(tmp_path)
    chars = [{
        "id": "girl",
        "framesDir": frames_dir,
        "position": [1.0, 2.0, -7.0],
        "scale": [2.5, 2.5],
    }]
    placed = _place_characters_on_ground(chars, _Z_OFFSETS)
    assert placed[0]["position"] == [1.0, 2.0, -7.0]
    assert placed[0]["scale"] == [2.5, 2.5]


def test_插件人物默认值与后端一致(插件):
    assert 插件.DEFAULT_CHARACTER_HEIGHT_M == _DEFAULT_CHARACTER_HEIGHT_M == 1.6
    assert 插件.CHARACTER_GROUND_CLEARANCE_M == _CHARACTER_GROUND_CLEARANCE_M == 0.3
    assert (
        插件.CHARACTER_DEPTH_FROM_FOREGROUND
        == _CHARACTER_DEPTH_FROM_FOREGROUND
        == 0.35
    )
    # 默认缩放 = 身高 / 默认占帧比，约 1.78，不是 4.0。
    默认 = 插件.DEFAULT_CHARACTER_HEIGHT_M / 插件.DEFAULT_CHARACTER_FILL
    assert 默认 == pytest.approx(1.78, abs=0.01)
    # 插件默认深度与后端同一条插值公式。
    manifest = {"zOffsets": [dict(r) for r in _Z_OFFSETS]}
    assert 插件.default_character_z(manifest) == pytest.approx(
        -2.0 + (-16.3 + 2.0) * 0.35
    )
    # 人物平面创建函数存在（bpy 缺席时不能调用，只校验签名）。
    assert callable(插件._create_plane_for_character)
