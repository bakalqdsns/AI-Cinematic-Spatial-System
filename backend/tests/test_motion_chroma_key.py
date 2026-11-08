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


def _write_shaded_plate_frame(path: Path, plate_dark: tuple[int, int, int],
                              plate_light: tuple[int, int, int]) -> None:
    """上半暗、下半亮的同一块绿幕，中间一个非绿主体；模拟生成视频里幕布变暗。"""
    import cv2

    image = np.zeros((64, 64, 3), dtype=np.uint8)
    image[:32] = plate_dark
    image[32:] = plate_light
    image[20:44, 20:44] = (40, 40, 180)
    ok, buf = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError(f"failed to encode {path}")
    path.write_bytes(buf.tobytes())


def _plate_chroma(bgr: tuple[int, int, int]) -> tuple[float, float]:
    import cv2

    ycc = cv2.cvtColor(np.uint8([[list(bgr)]]), cv2.COLOR_BGR2YCrCb)[0, 0]
    return float(ycc[1]), float(ycc[2])


def test_estimate_plate_chroma_picks_the_green_plate(tmp_path):
    """无论幕布明暗，投票出来的 Cr/Cb 都应该贴近幕布的色度。"""
    frame_path = tmp_path / "frame_0001.png"
    _write_shaded_plate_frame(frame_path, (75, 131, 49), (119, 178, 94))

    plate = me._estimate_plate_chroma([str(frame_path)])
    assert plate is not None
    expected = _plate_chroma((75, 131, 49))
    assert abs(plate[0] - expected[0]) < 6
    assert abs(plate[1] - expected[1]) < 6


def test_estimate_plate_chroma_returns_none_without_green(tmp_path):
    frame_path = tmp_path / "frame_0001.png"
    _write_frame_with_border(frame_path, (40, 40, 200))
    assert me._estimate_plate_chroma([str(frame_path)]) is None


def test_locked_key_removes_shaded_plate_and_keeps_subject():
    """同一帧里暗幕布和亮幕布亮度差很远，锁色后两半都必须变透明。"""
    rgba = np.zeros((64, 64, 4), dtype=np.uint8)
    rgba[:32, :, :3] = (75, 131, 49)
    rgba[32:, :, :3] = (119, 178, 94)
    rgba[:, :, 3] = 255
    rgba[20:44, 20:44] = (40, 40, 180, 255)

    out = me.chroma_key_rgba_locked(rgba, _plate_chroma((75, 131, 49)), min_island=0)
    assert int(out[4, 4, 3]) == 0
    assert int(out[60, 60, 3]) == 0
    assert int(out[32, 32, 3]) == 255


def test_locked_key_suppresses_green_spill_on_kept_pixels():
    """幕布反光把主体边缘染绿时，保留像素的 G 要压回中性。"""
    rgba = np.zeros((64, 64, 4), dtype=np.uint8)
    rgba[:, :, :3] = (75, 131, 49)
    rgba[:, :, 3] = 255
    rgba[20:44, 20:44] = (60, 140, 180, 255)

    out = me.chroma_key_rgba_locked(
        rgba, _plate_chroma((75, 131, 49)), min_island=0, despill=True
    )
    b, g, r = (int(out[32, 32, 0]), int(out[32, 32, 1]), int(out[32, 32, 2]))
    assert int(out[32, 32, 3]) == 255
    assert g <= (r + b) // 2 + 12


def test_locked_key_does_not_restore_existing_alpha():
    """锁色版同样只能更透明，不能把 SAM2 已经挖掉的轮廓涂回不透明。"""
    rgba = np.zeros((64, 64, 4), dtype=np.uint8)
    rgba[:, :, :3] = (75, 131, 49)
    rgba[:, :, 3] = 0
    rgba[20:44, 20:44] = (40, 40, 180, 255)

    out = me.chroma_key_rgba_locked(rgba, _plate_chroma((75, 131, 49)), min_island=0)
    assert int(out[4, 4, 3]) == 0
    assert int(out[32, 32, 3]) == 255


def test_chroma_key_frames_sequence_lock_plate_clears_shaded_screen(tmp_path):
    """整段锁色：两帧幕布一暗一亮，抠完都应该是透明底。"""
    frames = []
    for idx, (dark, light) in enumerate(
        [((75, 131, 49), (95, 154, 73)), ((90, 146, 70), (119, 178, 94))], start=1
    ):
        frame_path = tmp_path / "frames" / f"frame_{idx:04d}.png"
        frame_path.parent.mkdir(parents=True, exist_ok=True)
        _write_shaded_plate_frame(frame_path, dark, light)
        frames.append(str(frame_path))

    written = me.chroma_key_frames_sequence(
        frames, str(tmp_path / "seg"), lock_plate=True, despill=True
    )
    assert len(written) == 2
    for path in written:
        rgba = _read_rgba(Path(path))
        assert int(rgba[2, 2, 3]) == 0
        assert int(rgba[-2, -2, 3]) == 0
        assert int(rgba[32, 32, 3]) == 255


def test_chroma_key_frames_sequence_falls_back_when_plate_cannot_be_locked(tmp_path):
    """没有绿幕时锁色拿不到颜色，要退回逐帧采样而不是抛异常。"""
    frame_path = tmp_path / "frames" / "frame_0001.png"
    frame_path.parent.mkdir(parents=True, exist_ok=True)
    _write_frame_with_border(frame_path, (40, 40, 200))

    written = me.chroma_key_frames_sequence(
        [str(frame_path)], str(tmp_path / "seg"), lock_plate=True, despill=True
    )
    assert len(written) == 1
    rgba = _read_rgba(Path(written[0]))
    # 蓝底不是绿幕，逐帧采样会放弃抠像，主体保留。
    assert int(rgba[32, 32, 3]) == 255
