"""帧稳定化测试：抠像序列里人物被钉在同一锚点、同一大小。

不碰真实模型 / GPU / 视频后端：seg 帧全是合成方块，流水线级测试用
monkeypatch 假视频 / 假抽帧（参考 test_motion_chroma_key.py）。
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np

from app.services import motion_extractor as me


def _write_png(path: Path, image: np.ndarray) -> None:
    import cv2

    ok, buf = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError(f"failed to encode {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buf.tobytes())


def _write_seg_frame(path: Path, box: tuple[int, int, int, int] | None,
                     canvas: int = 128) -> None:
    """写一张 RGBA seg 帧：背景全透明，box=(y0,y1,x0,x1) 处是不透明人物方块。"""
    rgba = np.zeros((canvas, canvas, 4), dtype=np.uint8)
    if box is not None:
        y0, y1, x0, x1 = box
        rgba[y0:y1, x0:x1] = (40, 40, 180, 255)
    _write_png(path, rgba)


def _write_greenscreen_frame(path: Path, box: tuple[int, int, int, int],
                             canvas: int = 128) -> None:
    """绿幕底 + 人物方块的假原始帧（供 chroma key 流水线用）。"""
    image = np.zeros((canvas, canvas, 3), dtype=np.uint8)
    image[:] = (0, 255, 0)
    y0, y1, x0, x1 = box
    image[y0:y1, x0:x1] = (40, 40, 180)
    _write_png(path, image)


def _read_rgba(path: Path) -> np.ndarray:
    import cv2

    raw = np.frombuffer(path.read_bytes(), dtype=np.uint8)
    rgba = cv2.imdecode(raw, cv2.IMREAD_UNCHANGED)
    if rgba is None:
        raise AssertionError(f"could not decode {path}")
    return rgba


def _alpha_bbox(rgba: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.nonzero(rgba[:, :, 3] > 0)
    assert ys.size > 0, "expected a non-empty person mask"
    return int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1


# 三个框：位置、大小都不同；中位高度 60。
_BOXES = [
    (60, 100, 20, 60),    # h=40
    (40, 100, 40, 100),   # h=60
    (30, 110, 30, 110),   # h=80
]


def test_stabilize_frames_pins_anchor_and_height(tmp_path):
    """稳定化后：每帧包围盒底边中点在同一锚点（±1px），高度相等（±1px）。"""
    frame_paths = []
    for i, box in enumerate(_BOXES, start=1):
        p = tmp_path / "seg" / f"seg_{i:04d}.png"
        _write_seg_frame(p, box)
        frame_paths.append(str(p))

    written = me.stabilize_segmented_frames(frame_paths, str(tmp_path / "out"))
    assert len(written) == 3
    assert [Path(p).name for p in written] == [
        "seg_0001.png", "seg_0002.png", "seg_0003.png",
    ]

    canvas = 128
    anchor_fx = 0.5 * canvas            # 64
    anchor_fy = round(0.95 * canvas)    # 122
    foot_xs, foot_ys, heights = [], [], []
    for p in written:
        y0, y1, x0, x1 = _alpha_bbox(_read_rgba(Path(p)))
        foot_xs.append((x0 + x1) / 2)
        foot_ys.append(y1)
        heights.append(y1 - y0)

    for fx in foot_xs:
        assert abs(fx - anchor_fx) <= 1
    for fy in foot_ys:
        assert abs(fy - anchor_fy) <= 1
    assert max(heights) - min(heights) <= 1


def test_stabilize_frames_default_output_dir_is_stabilized_subdir(tmp_path):
    frame_paths = []
    for i, box in enumerate(_BOXES, start=1):
        p = tmp_path / "seg" / f"seg_{i:04d}.png"
        _write_seg_frame(p, box)
        frame_paths.append(str(p))

    written = me.stabilize_segmented_frames(frame_paths)
    assert len(written) == 3
    for p in written:
        assert Path(p).parent == tmp_path / "seg" / "stabilized"


def test_stabilize_frames_empty_alpha_passes_through(tmp_path):
    """没有 alpha 像素的帧原样写出。"""
    p1 = tmp_path / "seg" / "seg_0001.png"
    p2 = tmp_path / "seg" / "seg_0002.png"
    _write_seg_frame(p1, None)
    _write_seg_frame(p2, (40, 100, 40, 100))

    written = me.stabilize_segmented_frames([str(p1), str(p2)], str(tmp_path / "out"))
    assert len(written) == 2

    empty_out = _read_rgba(Path(written[0]))
    assert int((empty_out[:, :, 3] > 0).sum()) == 0

    # 正常帧仍被钉到锚点。
    y0, y1, x0, x1 = _alpha_bbox(_read_rgba(Path(written[1])))
    assert abs((x0 + x1) / 2 - 64) <= 1
    assert abs(y1 - round(0.95 * 128)) <= 1


def test_generate_motion_sequence_stabilizes_segmented_dir(tmp_path, monkeypatch):
    """流水线接入：generate_motion_sequence 之后 segmented_dir 里的 seg 帧已稳定。"""
    frame_dir = tmp_path / "frames"
    frame_paths = []
    for i, box in enumerate(_BOXES, start=1):
        p = frame_dir / f"frame_{i:04d}.png"
        _write_greenscreen_frame(p, box)
        frame_paths.append(str(p))

    async def fake_generate_action_video(**kwargs):
        return str(tmp_path / "clip.mp4")

    def fake_extract_frames(video_path, output_dir, *args, **kwargs):
        return list(frame_paths)

    monkeypatch.setattr(me, "generate_action_video", fake_generate_action_video)
    monkeypatch.setattr(me, "extract_frames_from_video", fake_extract_frames)

    import app.models as models_pkg

    monkeypatch.setattr(models_pkg.model_manager, "is_loaded", lambda: False)

    motion = asyncio.run(
        me.generate_motion_sequence(
            shot_id="shot-1",
            character_id="char-1",
            character_name="小女孩",
            action_prompt="walk",
            output_base_dir=str(tmp_path / "motion"),
            sam2_model=None,
            greenscreen=True,
        )
    )

    assert motion.status == "done"
    segs = sorted(Path(motion.segmented_dir).glob("seg_*.png"))
    assert [p.name for p in segs] == ["seg_0001.png", "seg_0002.png", "seg_0003.png"]

    canvas = 128
    foot_xs, foot_ys, heights = [], [], []
    for p in segs:
        y0, y1, x0, x1 = _alpha_bbox(_read_rgba(p))
        foot_xs.append((x0 + x1) / 2)
        foot_ys.append(y1)
        heights.append(y1 - y0)

    for fx in foot_xs:
        assert abs(fx - 0.5 * canvas) <= 1
    for fy in foot_ys:
        assert abs(fy - round(0.95 * canvas)) <= 1
    assert max(heights) - min(heights) <= 1
