"""绿幕抽帧不依赖 SAM2 / GPU：抠像后背景 alpha 为 0。"""
from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np

from app.services import motion_extractor as me


def _write_greenscreen_frame(path: Path) -> None:
    import cv2

    image = np.zeros((64, 64, 3), dtype=np.uint8)
    image[:] = (0, 255, 0)
    image[16:48, 16:48] = (40, 40, 180)
    ok, buf = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError(f"failed to encode {path}")
    path.write_bytes(buf.tobytes())


def _write_frame_with_border(path: Path, border_bgr: tuple[int, int, int]) -> None:
    """边缘一圈是指定幕布色、中间放一个非绿主体的测试帧。"""
    import cv2

    image = np.zeros((64, 64, 3), dtype=np.uint8)
    image[:] = border_bgr
    image[16:48, 16:48] = (40, 40, 180)
    ok, buf = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError(f"failed to encode {path}")
    path.write_bytes(buf.tobytes())


def test_frame_background_is_greenscreen_accepts_dark_green_plate(tmp_path):
    """暗绿幕布 BGR (77,148,93) 距纯绿约 161，也必须判为绿幕。"""
    from app.services.motion_extractor import frame_background_is_greenscreen

    frame_path = tmp_path / "frame_0001.png"
    _write_frame_with_border(frame_path, (77, 148, 93))
    assert frame_background_is_greenscreen(str(frame_path)) is True


def test_frame_background_is_greenscreen_rejects_red_border(tmp_path):
    from app.services.motion_extractor import frame_background_is_greenscreen

    frame_path = tmp_path / "frame_0001.png"
    _write_frame_with_border(frame_path, (40, 40, 200))
    assert frame_background_is_greenscreen(str(frame_path)) is False


def _read_rgba(path: Path) -> np.ndarray:
    import cv2

    raw = np.frombuffer(path.read_bytes(), dtype=np.uint8)
    rgba = cv2.imdecode(raw, cv2.IMREAD_UNCHANGED)
    if rgba is None:
        raise AssertionError(f"could not decode {path}")
    return rgba


def test_pure_green_edge_alpha_is_zero():
    from app.services.motion_extractor import chroma_key_rgba

    rgba = np.zeros((48, 48, 4), dtype=np.uint8)
    rgba[:, :, 1] = 255
    rgba[:, :, 3] = 255
    rgba[16:32, 16:32] = (40, 40, 180, 255)

    out = chroma_key_rgba(rgba, threshold=80, softness=20)
    assert int(out[0, 0, 3]) == 0
    assert int(out[0, -1, 3]) == 0
    assert int(out[24, 24, 3]) == 255


def test_green_patch_not_touching_edges_stays_opaque():
    """衣服上的绿不连着画面边缘，不能被幕布一起挖掉。"""
    from app.services.motion_extractor import chroma_key_rgba

    rgba = np.zeros((64, 64, 4), dtype=np.uint8)
    rgba[:, :] = (0, 255, 0, 255)
    rgba[16:48, 16:48] = (40, 40, 180, 255)
    rgba[24:40, 24:40] = (0, 255, 0, 255)

    out = chroma_key_rgba(rgba, threshold=80, softness=20)
    assert int(out[0, 0, 3]) == 0
    assert int(out[18, 18, 3]) == 255
    assert int(out[32, 32, 3]) == 255


def test_light_green_plate_like_paper_cut_becomes_transparent():
    """纸雕测试那种浅绿幕布（BGR 约 134,179,116）连着边缘时背景变透明。"""
    from app.services.motion_extractor import chroma_key_rgba

    screen = (134, 179, 116)
    rgba = np.zeros((64, 64, 4), dtype=np.uint8)
    rgba[:, :] = (*screen, 255)
    rgba[16:48, 16:48] = (40, 40, 180, 255)
    rgba[24:40, 24:40] = (*screen, 255)

    out = chroma_key_rgba(rgba, threshold=80, softness=20)
    assert int(out[0, 0, 3]) == 0
    assert int(out[-1, -1, 3]) == 0
    assert int(out[18, 18, 3]) == 255
    assert int(out[32, 32, 3]) == 255


def test_chroma_key_does_not_restore_existing_alpha():
    """色度只能更透明，不能把 SAM2 已经挖掉的轮廓涂回不透明。"""
    from app.services.motion_extractor import chroma_key_rgba

    screen = (134, 179, 116)
    rgba = np.zeros((64, 64, 4), dtype=np.uint8)
    rgba[:, :] = (*screen, 0)
    rgba[16:48, 16:48] = (40, 40, 180, 255)
    rgba[24:40, 24:40] = (*screen, 255)
    rgba[4, 4] = (0, 0, 255, 0)

    out = chroma_key_rgba(rgba, threshold=80, softness=20)
    assert int(out[0, 0, 3]) == 0
    assert int(out[4, 4, 3]) == 0
    assert int(out[18, 18, 3]) == 255
    assert int(out[32, 32, 3]) == 255


def test_chroma_key_skips_border_that_is_not_green():
    from app.services.motion_extractor import chroma_key_rgba

    rgba = np.zeros((32, 32, 4), dtype=np.uint8)
    rgba[:, :, 2] = 180
    rgba[:, :, 3] = 200
    rgba[12:20, 12:20] = (0, 255, 0, 255)

    out = chroma_key_rgba(rgba, threshold=80, softness=20)
    assert int(out[0, 0, 3]) == 200
    assert int(out[16, 16, 3]) == 255


def test_greenscreen_frame_background_alpha_is_zero_without_sam2(tmp_path, monkeypatch):
    frame_dir = tmp_path / "白发角色" / "frames"
    frame_dir.mkdir(parents=True)
    frame_path = frame_dir / "frame_0001.png"
    _write_greenscreen_frame(frame_path)

    async def fake_generate_action_video(**kwargs):
        return str(tmp_path / "clip.mp4")

    def fake_extract_frames(video_path, output_dir, *args, **kwargs):
        return [str(frame_path)]

    monkeypatch.setattr(me, "generate_action_video", fake_generate_action_video)
    monkeypatch.setattr(me, "extract_frames_from_video", fake_extract_frames)

    import app.models as models_pkg

    monkeypatch.setattr(models_pkg.model_manager, "is_loaded", lambda: False)

    motion = asyncio.run(
        me.generate_motion_sequence(
            shot_id="shot-1",
            character_id="char-1",
            character_name="白发角色",
            action_prompt="walk",
            output_base_dir=str(tmp_path / "motion"),
            sam2_model=None,
            greenscreen=True,
        )
    )

    assert motion.status == "done"
    assert not motion.error
    assert motion.video_path
    assert motion.frame_count == 1

    pngs = sorted(Path(motion.segmented_dir).glob("*.png"))
    assert [p.name for p in pngs] == ["seg_0001.png"]

    rgba = _read_rgba(pngs[0])
    assert rgba.ndim == 3 and rgba.shape[2] == 4
    # 抠像 + 稳定化后：背景 alpha 为 0（稳定化用全新透明画布，颜色通道一并清零）。
    assert int(rgba[0, 0, 3]) == 0
    assert int(rgba[-1, -1, 3]) == 0
    assert int(rgba[0, -1, 3]) == 0
    # 人物被钉在默认锚点：脚底在 (0.5*W, 0.95*H)。
    ys, xs = np.nonzero(rgba[:, :, 3] > 0)
    assert ys.size > 0
    assert abs((int(xs.min()) + int(xs.max()) + 1) / 2 - 32) <= 1
    assert abs((int(ys.max()) + 1) - round(0.95 * 64)) <= 1
