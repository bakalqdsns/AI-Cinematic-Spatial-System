"""app.tools 工具层测试：注册表一致性 + 纯计算工具假数据冒烟。

不碰真实模型 / GPU / LLM / ffmpeg：
- chroma_key / perspective / classify / layers 用假数据直接跑通；
- script / prompts / images / video 的 LLM、出图、视频工具只断言
  是 coroutine function 且可 import；
- video.extract_frames 需要 ffmpeg 和真实视频文件，跳过。
"""
from __future__ import annotations

import importlib
import inspect
from types import SimpleNamespace

import numpy as np
import pytest

import app.tools as tools

_LAYER_NAMES = ("sky", "background", "midground", "ground", "foreground")

#: 设计约定：LLM / 出图 / 视频类工具是 async，纯计算工具是 sync。
_EXPECTED_ASYNC = {
    "normalize_script_text",
    "parse_script_text",
    "extract_characters",
    "generate_shots",
    "character_visual_prompt",
    "scene_visual_prompt",
    "scene_keyframes",
    "character_three_view",
    "character_variation",
    "action_video",
}


# ---------------------------------------------------------------------------
# 注册表：__all__ / _TOOL_TABLE / list_tools
# ---------------------------------------------------------------------------

def test___all__与_TOOL_TABLE一致且每个名字都能getattr():
    assert sorted(tools._TOOL_TABLE) == sorted(tools.__all__)
    assert len(tools.__all__) == 31
    for name in tools.__all__:
        value = getattr(tools, name)  # 触发懒加载，不能抛 AttributeError
        module_name, attr = tools._TOOL_TABLE[name]
        module = importlib.import_module(module_name)
        assert value is getattr(module, attr)


def test_list_tools返回全部工具且async标记正确():
    table = tools.list_tools()
    assert set(table) == set(tools.__all__)
    for name, meta in table.items():
        assert meta["module"] == tools._TOOL_TABLE[name][0]
        assert meta["async"] == (name in _EXPECTED_ASYNC), name
        assert isinstance(meta["summary"], str) and meta["summary"]


# ---------------------------------------------------------------------------
# chroma_key：纯绿帧变透明、绿衣服不连边保留（纯 numpy，CPU）
# ---------------------------------------------------------------------------

def test_chroma_key_纯绿帧背景变透明():
    from app.tools import chroma_key_rgba_array

    rgba = np.zeros((48, 48, 4), dtype=np.uint8)
    rgba[:, :, 1] = 255  # 纯绿
    rgba[:, :, 3] = 255
    rgba[16:32, 16:32] = (40, 40, 180, 255)  # 中间一个人

    out = chroma_key_rgba_array(rgba, threshold=80, softness=20)
    assert int(out[0, 0, 3]) == 0
    assert int(out[-1, -1, 3]) == 0
    assert int(out[24, 24, 3]) == 255


def test_chroma_key_绿衣服不连边保留():
    """人身上那块绿不接触画面边缘，不能被幕布一起挖掉。"""
    from app.tools import chroma_key_rgba_array

    rgba = np.zeros((64, 64, 4), dtype=np.uint8)
    rgba[:, :] = (0, 255, 0, 255)          # 绿幕
    rgba[16:48, 16:48] = (40, 40, 180, 255)  # 红色的人
    rgba[24:40, 24:40] = (0, 255, 0, 255)  # 人身上的绿衣服

    out = chroma_key_rgba_array(rgba, threshold=80, softness=20)
    assert int(out[0, 0, 3]) == 0       # 幕布抠掉
    assert int(out[18, 18, 3]) == 255   # 人保留
    assert int(out[32, 32, 3]) == 255   # 绿衣服保留


def test_key_greenscreen与is_greenscreen_frame(tmp_path):
    import cv2

    from app.tools import is_greenscreen_frame, key_greenscreen

    frame = np.zeros((64, 64, 3), dtype=np.uint8)
    frame[:] = (0, 255, 0)
    frame[16:48, 16:48] = (40, 40, 180)
    frame_path = tmp_path / "frame_0001.png"
    ok, buf = cv2.imencode(".png", frame)
    assert ok
    frame_path.write_bytes(buf.tobytes())

    assert is_greenscreen_frame(str(frame_path))

    written = key_greenscreen([str(frame_path)], str(tmp_path / "seg"))
    assert len(written) == 1
    assert written[0].endswith("seg_0001.png")

    raw = np.frombuffer((tmp_path / "seg" / "seg_0001.png").read_bytes(),
                        dtype=np.uint8)
    rgba = cv2.imdecode(raw, cv2.IMREAD_UNCHANGED)
    assert rgba is not None and rgba.shape[2] == 4
    assert int(rgba[0, 0, 3]) == 0
    assert int(rgba[32, 32, 3]) == 255


# ---------------------------------------------------------------------------
# perspective：顺序固定、深度远→近单调、近大远小（远层放大）
# ---------------------------------------------------------------------------

def test_perspective_offsets_顺序单调与缩放():
    from app.tools import perspective_offsets

    h, w = 8, 8
    depth = np.full((h, w), 3.0, dtype=np.float32)
    sky = np.zeros((h, w), dtype=bool)
    sky[0:2, :] = True
    depth[sky] = 40.0
    foreground = np.zeros((h, w), dtype=bool)
    foreground[6:8, :] = True
    depth[foreground] = 2.0
    masks = {"sky": sky, "foreground": foreground}

    rows = perspective_offsets(depth, masks)
    # 顺序固定：sky → background → midground → ground → foreground。
    assert [r["layer"] for r in rows] == list(_LAYER_NAMES)
    # 深度远→近严格单调减小；zOffset 是负深度。
    depths = [r["depthMeters"] for r in rows]
    assert all(远 > 近 for 远, 近 in zip(depths, depths[1:]))
    for r in rows:
        assert r["zOffset"] == -r["depthMeters"]
        assert r["zMin"] == r["depthMeters"] == r["zMax"]
    # 近大远小：最近层 scale=1，远层放大（scale > 1）。
    assert rows[-1]["scale"] == 1.0
    assert all(r["scale"] >= 1.0 for r in rows)
    assert rows[0]["scale"] > rows[-1]["scale"]


def test_z_offset_table_默认兜底表():
    from app.tools import z_offset_table

    rows = z_offset_table()
    assert [r["layer"] for r in rows] == list(_LAYER_NAMES)
    按名 = {r["layer"]: r for r in rows}
    assert 按名["sky"]["zOffset"] == -20.0
    assert 按名["background"]["zOffset"] == -12.0
    assert 按名["midground"]["zOffset"] == -8.0
    assert 按名["ground"]["zOffset"] == -4.0
    assert 按名["foreground"]["zOffset"] == -2.0
    for r in rows:
        for key in ("layer", "zOffset", "zMin", "zMax", "thicknessM",
                    "yawDeg", "pitchDeg", "shiftXM", "shiftYM"):
            assert key in r


# ---------------------------------------------------------------------------
# classify：假物件打分；假 LLM 乱答时退回最高分
# ---------------------------------------------------------------------------

_SCENE_CLASSES = {
    "school_playground", "park", "street", "courtyard",
    "indoor_room", "nature", "unknown",
}


def _fake_obj(label: str, area: float = 100.0, depth: float = 5.0):
    return SimpleNamespace(
        label=label, meta={"area_px": area}, depth_mean=depth, mask=None,
    )


def test_scene_class_scores_假物件打分():
    from app.tools import scene_class_scores

    objs = [_fake_obj("bench"), _fake_obj("flower"), _fake_obj("dog")]
    scores = scene_class_scores(objs)
    assert set(scores) == _SCENE_CLASSES
    # bench/flower/dog 全部命中 park 匹配表，park 严格最高。
    assert all(
        scores["park"] > value
        for name, value in scores.items() if name != "park"
    )


def test_classify_scene_假LLM乱答时用最高分():
    from app.tools import classify_scene

    objs = [_fake_obj("bench"), _fake_obj("flower"), _fake_obj("dog")]
    assert classify_scene(objs, llm_call=lambda o, s: "我觉得是火星基地") == "park"
    # 假 LLM 答得靠谱时采纳 LLM。
    assert classify_scene(objs, llm_call=lambda o, s: "street") == "street"


def test_classify_scene_空列表返回unknown且不调LLM():
    from app.tools import classify_scene

    def boom(objects, scores):
        raise AssertionError("空列表不该调 LLM")

    assert classify_scene([], llm_call=boom) == "unknown"


# ---------------------------------------------------------------------------
# layers：假物件 + 假深度归层，各层互斥、近层拿走重叠像素
# ---------------------------------------------------------------------------

def test_layer_masks_假物件假深度归层互斥():
    from app.tools import layer_masks

    h, w = 16, 16
    depth = np.full((h, w), 8.0, dtype=np.float32)

    tree_mask = np.zeros((h, w), dtype=bool)
    tree_mask[0:8, :] = True
    person_mask = np.zeros((h, w), dtype=bool)
    person_mask[4:12, 4:12] = True  # 与树在 4:8 行重叠
    grass_mask = np.zeros((h, w), dtype=bool)
    grass_mask[12:16, :] = True

    objs = [
        SimpleNamespace(label="tree", mask=tree_mask, depth_mean=12.0, meta={}),
        SimpleNamespace(label="person", mask=person_mask, depth_mean=3.0, meta={}),
        SimpleNamespace(label="grass", mask=grass_mask, depth_mean=5.0, meta={}),
    ]
    masks = layer_masks(h, w, depth, objs, scene_class="park")

    assert set(masks) == set(_LAYER_NAMES)
    for name, mask in masks.items():
        assert mask.shape == (h, w) and mask.dtype == bool, name

    # 互斥：任一像素最多属于一层。
    stack = sum(mask.astype(np.int16) for mask in masks.values())
    assert int(stack.max()) <= 1

    # 树 → background，人 → foreground，草 → ground。
    assert masks["background"][1, 1]
    assert masks["ground"][14, 1]
    # 重叠区（树与人）：更近的人拿走可见像素。
    assert masks["foreground"][5, 5]
    assert not masks["background"][5, 5]
    # 人不重叠的部分也在 foreground。
    assert masks["foreground"][10, 10]


# ---------------------------------------------------------------------------
# script / prompts / images / video：async 且可 import（不调用，不碰 LLM）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(_EXPECTED_ASYNC))
def test_llm出图视频工具是coroutine且可import(name):
    fn = getattr(tools, name)
    assert inspect.iscoroutinefunction(fn), name


@pytest.mark.skip(reason="extract_frames 需要 ffmpeg 与真实视频文件，工具层测试不覆盖")
def test_extract_frames_跳过():
    pass
