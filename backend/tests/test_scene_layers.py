"""场景类打分、深度归层和遮挡补全。不调用真实 LLM，也不跑 LaMa。"""
from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import numpy as np
from PIL import Image

from app.services.layer_exporter import (
    LAYER_Z_OFFSETS,
    export_layers,
    inpaint_occluded_layers,
)
from app.services.object_assets import GroundAsset
from app.services.object_detector import _default_z
from app.services.scene_layer_table import (
    classify_scene,
    get_scene_spec,
    layer_for_label,
    scene_class_from_scores,
    score_scene_classes,
)

_LAYER_NAMES = ("sky", "background", "midground", "foreground", "ground")
_REPO = Path(__file__).resolve().parents[2]


class 假物件:
    """测试用物件。保留标签、mask、框、深度均值、垂直位置和面积。"""

    def __init__(
        self,
        label: str,
        *,
        area_px: int = 1000,
        mask: np.ndarray | None = None,
        depth_mean: float = 5.0,
        vertical_pos: float = 0.5,
        bbox: tuple[int, int, int, int] | None = None,
    ):
        self.label = label
        self.mask = mask
        self.depth_mean = depth_mean
        self.bbox = bbox if bbox is not None else (0, 0, 10, 10)
        if mask is not None:
            area = int(np.asarray(mask).sum())
        else:
            area = int(area_px)
        self.meta = {"area_px": area, "vertical_pos": vertical_pos}


def _操场物件() -> list[假物件]:
    return [
        假物件("操场", area_px=5000, vertical_pos=0.72),
        假物件("跑道", area_px=4000, vertical_pos=0.68),
        假物件("教学楼", area_px=3000, depth_mean=28.0, vertical_pos=0.35),
        假物件("person", area_px=800, depth_mean=4.0, vertical_pos=0.62),
        假物件("bench", area_px=400, depth_mean=8.0, vertical_pos=0.7),
    ]


def _空白(高: int, 宽: int, 颜色: tuple[int, int, int] = (30, 40, 50)) -> Image.Image:
    return Image.new("RGB", (宽, 高), 颜色)


def _深度(高: int, 宽: int, 值: float = 5.0) -> np.ndarray:
    return np.full((高, 宽), 值, dtype=np.float32)


def _导出(image: Image.Image, depth: np.ndarray, objects: list, scene: str) -> dict:
    return export_layers(
        image,
        depth,
        object_assets=objects,
        scene_class=scene,
        feather_px=0,
    )


def _加载模块(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_操场标签打分选中school_playground():
    物件 = _操场物件()
    得分 = score_scene_classes(物件)
    assert scene_class_from_scores(得分) == "school_playground", 得分
    assert 得分["school_playground"] > 得分["park"]
    assert 得分["school_playground"] > 得分["street"]
    assert 得分["school_playground"] > 得分["unknown"]

    操场 = get_scene_spec("school_playground")
    assert layer_for_label(操场, "操场") == "ground"
    assert layer_for_label(操场, "跑道") == "ground"
    assert layer_for_label(操场, "track") == "ground"
    assert layer_for_label(操场, "court") == "ground"
    assert layer_for_label(操场, "教学楼") == "background"
    assert layer_for_label(操场, "building") == "background"
    assert layer_for_label(操场, "tree") == "background"
    assert layer_for_label(操场, "人") == "foreground"
    assert layer_for_label(操场, "person") == "foreground"
    assert layer_for_label(操场, "bench") == "midground"
    assert 操场.has_sky is True
    assert 操场.has_ground is True

    室内 = get_scene_spec("indoor_room")
    assert layer_for_label(室内, "floor") == "ground"
    assert layer_for_label(室内, "地板") == "ground"
    assert layer_for_label(室内, "wall") == "background"
    assert layer_for_label(室内, "墙") == "background"
    assert layer_for_label(室内, "chair") == "midground"
    assert layer_for_label(室内, "床") == "midground"
    assert 室内.has_sky is False
    assert layer_for_label(get_scene_spec("unknown"), "雕像") is None


def test_室内大面积天空会被扣分():
    物件 = [
        假物件("天空", area_px=8000),
        假物件("椅子", area_px=500),
        假物件("地板", area_px=1000),
    ]
    得分 = score_scene_classes(物件)
    assert 得分["indoor_room"] < 0
    assert scene_class_from_scores(得分) != "indoor_room"
    assert 得分["indoor_room"] < 得分["nature"]


def test_LLM乱回答时用最高分():
    def 乱回答(objects, scores):
        assert scene_class_from_scores(scores) == "school_playground"
        return "我不知道，也许是月球基地"

    assert classify_scene(_操场物件(), llm_call=乱回答) == "school_playground"

    def 超时(objects, scores):
        raise TimeoutError("llm timeout")

    assert classify_scene(_操场物件(), llm_call=超时) == "school_playground"


def test_LLM给出闭集类名时采用该结果():
    def 选公园(objects, scores):
        assert "school_playground" in scores
        return "park"

    assert classify_scene(_操场物件(), llm_call=选公园) == "park"


def test_人物即使深度很远也在前景():
    高, 宽 = 24, 24
    人遮罩 = np.zeros((高, 宽), dtype=bool)
    人遮罩[6:20, 6:20] = True
    树遮罩 = np.zeros((高, 宽), dtype=bool)
    树遮罩[0:4, 0:4] = True
    物件 = [
        假物件("人", mask=人遮罩, depth_mean=80.0, vertical_pos=0.5),
        假物件("树", mask=树遮罩, depth_mean=10.0, vertical_pos=0.1),
    ]
    层 = _导出(_空白(高, 宽), _深度(高, 宽, 80.0), 物件, "school_playground")
    前景 = np.array(层["foreground"])
    背景 = np.array(层["background"])
    assert 前景[10, 10, 3] == 255
    assert 背景[10, 10, 3] == 0
    assert 背景[1, 1, 3] == 255
    assert 前景[1, 1, 3] == 0
    assert 物件[0].depth_mean > 物件[1].depth_mean


def test_人和地面重叠时可见像素属于前景地面待补():
    高, 宽 = 48, 48
    人遮罩 = np.zeros((高, 宽), dtype=bool)
    人遮罩[10:30, 10:34] = True
    地面遮罩 = np.zeros((高, 宽), dtype=bool)
    地面遮罩[22:40, 6:40] = True
    重叠 = 人遮罩 & 地面遮罩
    assert 重叠.any()
    物件 = [
        假物件("人", mask=人遮罩, depth_mean=40.0),
        假物件("跑道", mask=地面遮罩, depth_mean=6.0),
    ]
    原图 = _空白(高, 宽, (30, 40, 50))
    分层前 = _导出(原图, _深度(高, 宽), 物件, "school_playground")

    透明度 = np.stack([np.array(分层前[名字])[..., 3] for 名字 in _LAYER_NAMES], axis=0)
    合计 = 透明度.sum(axis=0)
    assert np.all((合计 == 0) | (合计 == 255))
    assert np.all(np.array(分层前["foreground"])[重叠, 3] == 255)
    assert np.all(np.array(分层前["ground"])[重叠, 3] == 0)

    调用的洞: list[np.ndarray] = []

    def 假补全(base, mask, prompt):
        调用的洞.append(np.array(mask.convert("L")))
        return Image.new("RGB", base.size, (7, 8, 9))

    分层后 = inpaint_occluded_layers(
        原图,
        分层前,
        _深度(高, 宽),
        object_assets=物件,
        scene_class="school_playground",
        inpaint_fn=假补全,
    )
    人洞 = (人遮罩.astype(np.uint8) * 255)
    assert sum(np.array_equal(洞, 人洞) for 洞 in 调用的洞) == 1
    assert np.all(人洞[重叠] == 255)

    地面 = np.array(分层后["ground"])
    仅地面 = 地面遮罩 & ~人遮罩
    assert np.all(地面[重叠, 3] == 255)
    assert np.all(地面[重叠, 0] == 7)
    assert np.all(地面[重叠, 1] == 8)
    assert np.all(地面[重叠, 2] == 9)
    assert np.all(地面[仅地面, 3] == 255)
    assert np.all(地面[仅地面, 0] == 30)
    assert np.array_equal(np.array(分层后["foreground"]), np.array(分层前["foreground"]))


def test_剩余像素跟随地面物件深度而不是上下位置():
    高, 宽 = 32, 40
    图 = _空白(高, 宽, (255, 255, 255))
    深度 = _深度(高, 宽, 5.0)
    跑道 = np.zeros((高, 宽), dtype=bool)
    跑道[10:14, 20:24] = True
    教学楼 = np.zeros((高, 宽), dtype=bool)
    教学楼[10:14, 2:6] = True
    深度[教学楼] = 30.0
    深度[30, 38] = 30.0
    深度[1, 38] = 45.0
    物件 = [
        假物件("跑道", mask=跑道, depth_mean=5.0, vertical_pos=0.4),
        假物件("教学楼", mask=教学楼, depth_mean=30.0, vertical_pos=0.4),
    ]
    层 = _导出(图, 深度, 物件, "school_playground")
    天空 = np.array(层["sky"])[..., 3]
    地面 = np.array(层["ground"])[..., 3]
    背景 = np.array(层["background"])[..., 3]
    前景 = np.array(层["foreground"])[..., 3]

    # 上半幅、颜色像天空，但深度贴着跑道，应进地面。
    assert 地面[1, 1] == 255
    assert 天空[1, 1] == 0
    assert 前景[1, 1] == 0
    # 画面底部、同样的地面深度，不能因为靠下就变成前景。
    assert 地面[30, 1] == 255
    assert 前景[30, 1] == 0
    # 底部像素深度贴着教学楼，进背景，而不是因为靠下就铺成地面。
    assert 背景[30, 38] == 255
    assert 地面[30, 38] == 0
    # 上半幅且比已归背景更远，才进天空。
    assert 天空[1, 38] == 255
    assert 地面[1, 38] == 0


def test_未知标签按深度就近不进前景():
    高, 宽 = 24, 24
    雕像遮罩 = np.zeros((高, 宽), dtype=bool)
    雕像遮罩[8:16, 8:16] = True
    只有雕像 = [假物件("雕像", mask=雕像遮罩, depth_mean=12.0)]
    仅雕像层 = _导出(_空白(高, 宽), _深度(高, 宽, 12.0), 只有雕像, "unknown")
    assert int(np.array(仅雕像层["foreground"])[..., 3].sum()) == 0
    assert np.array(仅雕像层["midground"])[10, 10, 3] == 255

    树遮罩 = np.zeros((高, 宽), dtype=bool)
    树遮罩[0:4, 0:4] = True
    带树 = [
        假物件("树", mask=树遮罩, depth_mean=12.0),
        假物件("雕像", mask=雕像遮罩, depth_mean=12.0),
    ]
    层 = _导出(_空白(高, 宽), _深度(高, 宽, 12.0), 带树, "unknown")
    assert np.array(层["background"])[10, 10, 3] == 255
    assert np.array(层["foreground"])[10, 10, 3] == 0
    assert int(np.array(层["foreground"])[..., 3].sum()) == 0


def test_室内不产生天空实心像素():
    高, 宽 = 32, 32
    深度 = _深度(高, 宽, 3.0)
    墙遮罩 = np.zeros((高, 宽), dtype=bool)
    墙遮罩[0:4, 0:4] = True
    地板遮罩 = np.zeros((高, 宽), dtype=bool)
    地板遮罩[20:28, 4:12] = True
    深度[墙遮罩] = 8.0
    深度[1, 20] = 100.0
    物件 = [
        假物件("墙", mask=墙遮罩, depth_mean=8.0, vertical_pos=0.05),
        假物件("地板", mask=地板遮罩, depth_mean=3.0, vertical_pos=0.75),
    ]
    层 = _导出(_空白(高, 宽, (250, 250, 250)), 深度, 物件, "indoor_room")
    assert int(np.array(层["sky"])[..., 3].sum()) == 0
    assert np.array(层["background"])[1, 20, 3] == 255
    assert np.array(层["ground"])[24, 8, 3] == 255


def test_没有检测结果时仍写出五张全透明层(tmp_path, monkeypatch):
    项目 = tmp_path / "proj"
    (项目 / "scenes").mkdir(parents=True)
    Image.new("RGB", (16, 16), (12, 24, 36)).save(项目 / "scenes" / "wide.png")

    假模块 = types.ModuleType("app.models.model_manager")

    class _假深度:
        def predict_meters(self, image, scale=50.0):
            宽, 高 = image.size
            return np.ones((高, 宽), np.float32) * 6.0

    假模块.model_manager = types.SimpleNamespace(depth_model=_假深度())
    monkeypatch.setitem(sys.modules, "app.models.model_manager", 假模块)

    def _检测失败(*args, **kwargs):
        raise RuntimeError("检测失败")

    def _地面失败(*args, **kwargs):
        raise RuntimeError("地面失败")

    def _分类失败(*args, **kwargs):
        raise RuntimeError("分类失败")

    monkeypatch.setattr("app.services.object_detector.detect_objects", _检测失败)
    monkeypatch.setattr("app.services.ground_reconstructor.reconstruct_ground", _地面失败)
    monkeypatch.setattr("app.services.scene_layer_table.classify_scene", _分类失败)

    from app.services.shot_archiver import ensure_depth_layers

    写出 = ensure_depth_layers(项目)
    assert sorted(写出) == sorted(f"{名字}.png" for 名字 in _LAYER_NAMES)
    for 名字 in _LAYER_NAMES:
        路径 = 项目 / "layers" / f"{名字}.png"
        assert 路径.is_file() and 路径.stat().st_size > 0
        透明度 = np.array(Image.open(路径).convert("RGBA"))[..., 3]
        assert int(透明度.sum()) == 0
    标记 = json.loads((项目 / "layers" / "_fill.json").read_text(encoding="utf-8"))
    assert 标记["method"] == "scene_table_perspective_v2"
    assert 标记["sceneClass"] == "unknown"


def test_地面Z位于前景和中景之间():
    assert LAYER_Z_OFFSETS["sky"] == -20.0
    assert LAYER_Z_OFFSETS["background"] == -12.0
    assert LAYER_Z_OFFSETS["midground"] == -8.0
    assert LAYER_Z_OFFSETS["ground"] == -4.0
    assert LAYER_Z_OFFSETS["foreground"] == -2.0
    assert LAYER_Z_OFFSETS["foreground"] > LAYER_Z_OFFSETS["ground"] > LAYER_Z_OFFSETS["midground"]
    assert _default_z("ground") == -4.0
    assert _default_z("midground") == -8.0
    assert GroundAsset().z_offset == -4.0

    from app.services.mesh_exporter import _LAYER_Z_TABLE
    from app.services.shot_archiver import _DEFAULT_Z_OFFSETS

    assert _LAYER_Z_TABLE["ground"] == -4.0
    assert _LAYER_Z_TABLE["midground"] == -8.0
    归档表 = {项["layer"]: 项["zOffset"] for 项 in _DEFAULT_Z_OFFSETS}
    assert 归档表["ground"] == -4.0
    assert 归档表["foreground"] == -2.0
    assert 归档表["midground"] == -8.0

    插件 = _加载模块(
        _REPO / "backend" / "blender" / "addons" / "aicss_scene_builder" / "utils" / "scene_utils.py",
        "aicss_scene_utils_for_test",
    )
    视差 = _加载模块(
        _REPO / "backend" / "blender" / "addons" / "aicss_scene_builder" / "operators" / "layer_motion.py",
        "aicss_layer_motion_for_test",
    )
    assert 插件.Z_OFFSETS["ground"] == -4.0
    assert 插件.Z_OFFSETS["midground"] == -8.0
    assert 插件.Z_OFFSETS["foreground"] == -2.0
    assert 视差._Z_OFFSETS["ground"] == -4.0
    assert 视差._Z_OFFSETS["midground"] == -8.0


def test_视差输出越大越近时翻成近小远大():
    from app.utils.image_utils import depth_to_meters, disparity_to_depth_norm

    视差图 = np.array([[1.0, 0.0], [0.8, 0.2]], dtype=np.float32)
    深度 = disparity_to_depth_norm(视差图)
    assert float(深度[0, 0]) == 0.0
    assert float(深度[0, 1]) == 1.0
    米 = depth_to_meters(深度, scale=50.0)
    assert float(米[0, 1]) > float(米[0, 0])


def test_层深度和缩放近大远小且顺序一致():
    from app.services.layer_exporter import perspective_offsets

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
    表 = perspective_offsets(深度, 遮罩)
    按名 = {项["layer"]: 项 for 项 in 表}
    assert 按名["sky"]["depthMeters"] > 按名["foreground"]["depthMeters"]
    assert 按名["sky"]["zOffset"] < 按名["background"]["zOffset"] < 按名["foreground"]["zOffset"]
    assert 按名["foreground"]["scale"] == 1.0
    assert 按名["sky"]["scale"] > 按名["foreground"]["scale"]
    近距 = 12.0 + 按名["foreground"]["depthMeters"]
    远距 = 12.0 + 按名["sky"]["depthMeters"]
    assert 按名["sky"]["scale"] == round(远距 / 近距, 4)
    assert 按名["foreground"]["zOffset"] == -按名["foreground"]["depthMeters"]


def test_清单里的缩放会传给层平面():
    插件 = _加载模块(
        _REPO / "backend" / "blender" / "addons" / "aicss_scene_builder" / "utils" / "scene_utils.py",
        "aicss_scene_utils_scale_for_test",
    )
    清单 = {"zOffsets": [
        {"layer": "sky", "zOffset": -40.0, "scale": 0.2},
        {"layer": "foreground", "zOffset": -2.0, "scale": 1.0},
    ]}
    assert 插件.layer_plane_scale(清单, "sky") == 0.2
    assert 插件.layer_z_offset(清单, "foreground") == -2.0
    assert 插件.layer_plane_scale({}, "sky") == 1.0
