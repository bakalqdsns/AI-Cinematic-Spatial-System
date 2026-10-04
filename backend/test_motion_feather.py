"""Unit tests for the motion pipeline post-processing helpers.

These tests do not require SAM2 weights, a GPU, or ffmpeg — they exercise the
pure-Python / NumPy helpers (``chroma_key_rgba``) and validate the public
function signatures / call contracts.
"""
import inspect

import numpy as np


def test_chroma_key_rgba_removes_pure_green():
    from app.services.motion_extractor import chroma_key_rgba

    h, w = 32, 32
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[:, :, 1] = 255  # full green
    rgba[:, :, 3] = 255

    out = chroma_key_rgba(rgba, threshold=80, softness=20)
    assert out.shape == rgba.shape
    # Pure green must become fully transparent.
    assert (out[:, :, 3] == 0).all(), "green pixels must be alpha=0"


def test_chroma_key_rgba_keeps_red():
    from app.services.motion_extractor import chroma_key_rgba

    h, w = 16, 16
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[:, :, 2] = 255  # full red
    rgba[:, :, 3] = 255

    out = chroma_key_rgba(rgba, threshold=80, softness=20)
    # Red pixels are far from green, alpha must stay 255.
    assert (out[:, :, 3] == 255).all(), "red pixels must keep alpha=255"


def test_chroma_key_rgba_feather_band():
    from app.services.motion_extractor import chroma_key_rgba

    h, w = 8, 8
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    # Yellow-ish green at distance ~127 from pure green -> ramp zone.
    rgba[:, :, 0] = 50
    rgba[:, :, 1] = 200
    rgba[:, :, 2] = 50
    rgba[:, :, 3] = 255

    out = chroma_key_rgba(rgba, threshold=80, softness=40)
    # Alpha should be in (0, 255), not 0 or 255 only.
    alpha_vals = np.unique(out[:, :, 3])
    assert len(alpha_vals) > 1 or (0 < alpha_vals[0] < 255), (
        f"feather band must produce intermediate alpha, got {alpha_vals}"
    )


def test_segment_person_from_frame_accepts_greenscreen():
    """The function signature must expose the new parameters."""
    from app.services.motion_extractor import segment_person_from_frame

    sig = inspect.signature(segment_person_from_frame)
    params = sig.parameters
    for name in ("feather_edges", "greenscreen", "chroma_threshold", "chroma_softness", "snap_distance"):
        assert name in params, f"segment_person_from_frame must accept {name!r}"
    # feather_edges and greenscreen default to sensible values
    assert params["feather_edges"].default is True
    assert params["greenscreen"].default is False


def test_segment_frames_sequence_forwards_kwargs():
    from app.services.motion_extractor import segment_frames_sequence

    sig = inspect.signature(segment_frames_sequence)
    params = sig.parameters
    for name in ("feather_edges", "greenscreen", "chroma_threshold", "chroma_softness", "snap_distance"):
        assert name in params, f"segment_frames_sequence must accept {name!r}"


def test_generate_motion_sequence_accepts_motion_params():
    from app.services.motion_extractor import generate_motion_sequence

    sig = inspect.signature(generate_motion_sequence)
    params = sig.parameters
    for name in ("greenscreen", "feather_edges", "chroma_threshold", "chroma_softness", "snap_distance"):
        assert name in params, f"generate_motion_sequence must accept {name!r}"


def test_extract_frames_raises_when_ffmpeg_missing(monkeypatch):
    """When ffmpeg is not on PATH, extract_frames_from_video must raise RuntimeError."""
    from app.services.motion_extractor import extract_frames_from_video

    monkeypatch.setattr("shutil.which", lambda _: None)
    try:
        extract_frames_from_video("/tmp/does-not-exist.mp4", "/tmp/frames")
    except RuntimeError as e:
        assert "ffmpeg" in str(e).lower()
    else:
        raise AssertionError("extract_frames_from_video should raise RuntimeError when ffmpeg is missing")


def test_extract_frames_accepts_explicit_ffmpeg_path(monkeypatch, tmp_path):
    """When an explicit ffmpeg_path is provided, shutil.which is bypassed."""
    from app.services.motion_extractor import extract_frames_from_video

    monkeypatch.setattr("shutil.which", lambda _: None)

    seen_cmd = {}

    class FakeResult:
        returncode = 1
        stderr = "synthetic ffmpeg error"

    def fake_run(cmd, **kwargs):
        seen_cmd["exe"] = cmd[0]
        return FakeResult()

    monkeypatch.setattr("subprocess.run", fake_run)
    try:
        extract_frames_from_video(
            "/tmp/does-not-exist.mp4",
            str(tmp_path),
            ffmpeg_path="/opt/custom/ffmpeg",
        )
    except RuntimeError as e:
        assert seen_cmd["exe"] == "/opt/custom/ffmpeg"
        assert "synthetic ffmpeg error" in str(e)
    else:
        raise AssertionError("extract_frames_from_video should re-raise RuntimeError on non-zero returncode")


if __name__ == "__main__":
    test_chroma_key_rgba_removes_pure_green()
    test_chroma_key_rgba_keeps_red()
    test_chroma_key_rgba_feather_band()
    test_segment_person_from_frame_accepts_greenscreen()
    test_segment_frames_sequence_forwards_kwargs()
    test_generate_motion_sequence_accepts_motion_params()
    print("All motion_extractor unit tests PASSED.")
