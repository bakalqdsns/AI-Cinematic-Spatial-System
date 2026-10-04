"""E2E 验证:模块 4 修复的三个不变量。

本次修复涉及三个改动点,本脚本**不启动后端、不调用 Blender、不下载模型**,直接在
Python 进程中验证最终行为是否正确:

  (1) ``mesh_exporter.make_paper_material`` 的 Blender 脚本源码含 HASHED 透明
      混合 + Alpha 输出连线,与下游 GLB 渲染一致。
  (2) ``object_assets.make_object_rgba(feather_px=N)`` 输出的 RGBA alpha 通
      道在边缘处含软渐变(不再是严格 0/255 二值),且 ``feather_px=0`` 仍可禁
      用羽化。
  (3) ``object_detector.detect_objects`` 内部对 SAM2 mask 调用
      ``refine_mask_edges`` —— 这里通过静态扫描 + 调用链 mock 来证明。

Usage:
    cd F:/AICinematicSpatialSystem/backend
    python test_alpha_blend_e2e.py
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
from PIL import Image


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


# ---------------------------------------------------------------------------
# 检查 (1): Blender 脚本启用透明混合
# ---------------------------------------------------------------------------

def check_blender_alpha_script() -> list[str]:
    """读取 ``mesh_exporter`` 中嵌入的 Blender Python 脚本字符串,断言包含
    透明材质所需的全部声明。"""
    src = (HERE / "app/services/mesh_exporter.py").read_text(encoding="utf-8")

    # ``make_paper_material`` 拼出来的一段串就是嵌入到 Blender headless
    # run 的脚本(经 ``exec(...)`` 调用)。直接扫描 *Python 源码* 而不是真的
    # 跑 Blender —— 我们只关心逻辑约束是否就位。
    func_match = re.search(
        r"def make_paper_material\(.*?(?=\ndef |\Z)",
        src,
        flags=re.DOTALL,
    )
    assert func_match, "make_paper_material not found in mesh_exporter.py"
    snippet = func_match.group(0)

    failures: list[str] = []
    required = [
        ("HASHED blend_method", r"mat\.blend_method\s*=\s*['\"]HASHED['\"]"),
        ("HASHED shadow_method", r"mat\.shadow_method\s*=\s*['\"]HASHED['\"]"),
        ("alpha_threshold=0.5", r"mat\.alpha_threshold\s*=\s*0\.5"),
        ("use_backface_culling", r"mat\.use_backface_culling\s*=\s*True"),
        (
            "diffuse Alpha → Principled Alpha",
            r"tex\.outputs\[['\"]Alpha['\"]]\s*,\s*principled\.inputs\[['\"]Alpha['\"]]",
        ),
    ]
    for label, pattern in required:
        if not re.search(pattern, snippet):
            failures.append(f"[blender-script] missing: {label} ({pattern})")
    return failures


# ---------------------------------------------------------------------------
# 检查 (2): make_object_rgba 软边缘
# ---------------------------------------------------------------------------

def _circle_mask(size: int = 64, radius: int = 24) -> Image.Image:
    """生成一张干净的纯圆 RGB 图像 + 对应的圆形 bool mask。"""
    yy, xx = np.mgrid[0:size, 0:size]
    cy = cx = size // 2
    inside = (yy - cy) ** 2 + (xx - cx) ** 2 <= radius ** 2
    rgb = np.zeros((size, size, 3), dtype=np.uint8)
    # 圆内白色,圆外黑色;真实抠图用例中圆外像素在导出时被 0 alpha 隐藏。
    rgb[inside] = 230
    rgb[~inside] = 25
    return Image.fromarray(rgb, "RGB"), inside


def check_make_object_rgba() -> list[str]:
    """make_object_rgba 必须:
       - 把 uint8 alpha 输出为软渐变(不再只含 0 / 255)
       - 中央和远离边缘的内部像素 alpha 仍 ≈ 255
    """
    from app.services.object_assets import make_object_rgba

    failures: list[str] = []
    rgb_img, mask = _circle_mask(size=96, radius=32)

    # Default feather_px = 1: alpha should have non-binary values.
    out_default = make_object_rgba(rgb_img, mask)
    alpha_default = np.array(out_default)[:, :, 3]
    uniq = np.unique(alpha_default)
    if len(uniq) <= 2 and set(uniq.tolist()).issubset({0, 255}):
        failures.append(
            f"[object-assets] feather=1 默认仍只输出 0/255,uniq={uniq.tolist()}"
        )

    # 中央纯色像素 alpha 必须仍为 255
    center_alpha = int(alpha_default[48, 48])
    if center_alpha < 240:
        failures.append(
            f"[object-assets] 中央 alpha 应 ≈255,实测 {center_alpha}"
        )

    # 圆外角点像素 alpha 必须为 0
    corner_alpha = int(alpha_default[0, 0])
    if corner_alpha > 8:
        failures.append(
            f"[object-assets] 圆外 alpha 应≈0,实测 {corner_alpha}"
        )

    # 边缘一圈必须有过渡带宽度 ≥ 2 个像素(任一中间值出现即可)
    mid_band = alpha_default[15:18, 46:51]
    if not ((mid_band > 0) & (mid_band < 255)).any():
        failures.append(
            f"[object-assets] 边缘未出现软渐变像素,sample:\n{mid_band}"
        )

    # feather_px=0: 必须保持 0/255 二值,给硬边用例留 escape hatch
    out_hard = make_object_rgba(rgb_img, mask, feather_px=0)
    alpha_hard = np.array(out_hard)[:, :, 3]
    uniq_hard = set(np.unique(alpha_hard).tolist())
    if not uniq_hard.issubset({0, 255}):
        failures.append(
            f"[object-assets] feather_px=0 仍应二值,uniq={sorted(uniq_hard)}"
        )

    # feather_px=3: alpha 软渐变更宽(uniq 数量应该≥ feather=1 情况)
    out_soft = make_object_rgba(rgb_img, mask, feather_px=3)
    uniq_soft = len(np.unique(np.array(out_soft)[:, :, 3]))
    if uniq_soft < len(uniq):
        failures.append(
            f"[object-assets] feather_px=3 渐变层数应比 feather=1 少,"
            f"uniq(soft)={uniq_soft},uniq(default)={len(uniq)}"
        )

    return failures


# ---------------------------------------------------------------------------
# 检查 (3): detect_objects 调用 refine_mask_edges
# ---------------------------------------------------------------------------

def check_detector_calls_refine() -> list[str]:
    """``detect_objects`` 在得到 SAM2 mask 之后必须调用
    ``refine_mask_edges``(snap_distance 应与端点层一致 = 8)。"""
    from app.services import object_detector

    failures: list[str] = []
    src = Path(object_detector.__file__).read_text(encoding="utf-8")

    if "refine_mask_edges" not in src:
        failures.append("[object-detector] 模块源码不含 refine_mask_edges 调用")
        return failures

    # 抽取 detect_objects 函数体,断言 snap_distance=8
    func_match = re.search(
        r"def detect_objects\(.*?(?=\ndef |\Z)",
        src,
        flags=re.DOTALL,
    )
    assert func_match, "detect_objects not found"
    body = func_match.group(0)
    if "snap_distance=8" not in body:
        failures.append("[object-detector] snap_distance 未固定为 8")

    # 用 mock 跑一遍函数体: 模型管理器返回固定检测 + 固定 mask,
    # 验证 result.mask 被 refine_mask_edges 处理过(像素差 > 0)
    fake_box = np.array([10, 10, 80, 80], dtype=np.float32)
    fake_mask_a = np.zeros((96, 96), dtype=bool)
    fake_mask_a[20:75, 20:75] = True   # 矩形
    fake_mask_b = np.zeros((96, 96), dtype=bool)
    fake_mask_b[15:80, 25:70] = True   # 偏移后矩形,模拟边缘贴合效果

    fake_rgb = Image.fromarray(
        (np.random.RandomState(0).rand(96, 96, 3) * 255).astype(np.uint8), "RGB"
    )

    fake_dino = MagicMock()
    fake_dino.detect.return_value = [
        MagicMock(box=fake_box, score=0.95, label="mock_object"),
    ]
    fake_sam2 = MagicMock()
    fake_sam2.predict_masks_from_boxes.return_value = [
        (fake_mask_a, 0.95),
    ]

    fake_mm = MagicMock()
    fake_mm.grounding_dino = fake_dino
    fake_mm.sam2 = fake_sam2

    # refine_mask_edges 不应抛异常,且必须被调用
    called = {"n": 0, "snap": None, "with_masks": None}

    def _fake_refine(masks, image_rgb, snap_distance=8):
        called["n"] += 1
        called["snap"] = snap_distance
        called["with_masks"] = [m.copy() for m, _ in masks]
        # 模拟边缘贴合后的 mask(比原 mask 更贴合真实图像的边缘)
        return [(fake_mask_b, s) for _, s in masks]

    # detect_objects 内部使用以下两个 ``from … import``:
    #   from app.models.model_manager import model_manager
    #   from app.models.sam2_loader    import refine_mask_edges
    # Python 解释器会先查 sys.modules,只要那里是 MagicMock 即可命中。
    # 同时把 ``app.models.model_manager`` 提供成 ``fake_mm``,让
    # ``from … import model_manager`` 拿到我们的 MagicMock。
    sys.modules["app.models.model_manager"] = MagicMock(model_manager=fake_mm)
    sys.modules["app.models.sam2_loader"] = MagicMock(
        refine_mask_edges=MagicMock(side_effect=_fake_refine),
    )

    try:
        objs, ground = object_detector.detect_objects(
            fake_rgb, depth_meters=None,
        )
    except Exception as e:
        import traceback
        failures.append(
            f"[object-detector] 调用失败:{type(e).__name__}: {e}\n"
            f"{traceback.format_exc()}"
        )
        return failures
    finally:
        # 清理 sys.modules,避免污染本进程后续测试
        sys.modules.pop("app.models.model_manager", None)
        sys.modules.pop("app.models.sam2_loader", None)

    if called["n"] == 0:
        failures.append(
            "[object-detector] refine_mask_edges 未被调用 "
            "(snap_distance 8 应触发)"
        )
    elif called["snap"] != 8:
        failures.append(
            f"[object-detector] snap_distance 不正确:{called['snap']}"
        )

    if not objs:
        failures.append("[object-detector] 没产出 object_assets")
    else:
        # 既然 _fake_refine 把 mask a → mask b,落到 ObjectAsset.mask
        # 上应该是 b。如果还是 a,说明 refine 路径没生效。
        final_mask = getattr(objs[0], "mask", None)
        if final_mask is None:
            failures.append("[object-detector] ObjectAsset.mask 为 None")
        elif final_mask.shape != fake_mask_b.shape or not np.array_equal(
            final_mask, fake_mask_b
        ):
            failures.append(
                "[object-detector] ObjectAsset.mask 仍为 refine 前的版本 "
                "(未走 refine_mask_edges)"
            )

    return failures


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def main() -> int:
    print("=" * 72)
    print("[alpha-blend-e2e] 模块 4 修复不变量回归")
    print("=" * 72)

    sections = [
        ("(1) Blender 脚本启用透明混合", check_blender_alpha_script),
        ("(2) make_object_rgba 软边缘", check_make_object_rgba),
        ("(3) detect_objects 调用 refine_mask_edges", check_detector_calls_refine),
    ]

    total_fail = 0
    for label, fn in sections:
        print(f"\n→ {label}")
        try:
            failures = fn()
        except Exception as e:
            failures = [f"[{label}] 异常: {type(e).__name__}: {e}"]
        if failures:
            total_fail += len(failures)
            for f in failures:
                print(f"   FAIL  {f}")
        else:
            print("   PASS")

    print("\n" + "=" * 72)
    if total_fail == 0:
        print("ALL CHECKS PASSED")
        return 0
    print(f"{total_fail} FAILURE(S)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
