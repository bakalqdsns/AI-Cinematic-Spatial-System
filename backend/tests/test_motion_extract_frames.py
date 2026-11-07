"""抽帧 ffmpeg 命令保持宽高比，不把 16:9 视频硬拉成正方形。"""
from __future__ import annotations

from app.services import motion_extractor as me


def test_extract_frames_ffmpeg_keeps_aspect_ratio(tmp_path, monkeypatch):
    captured: dict[str, list[str]] = {}

    class _Result:
        returncode = 0
        stderr = ""

    def fake_run(cmd, *args, **kwargs):
        captured["cmd"] = list(cmd)
        return _Result()

    monkeypatch.setattr("subprocess.run", fake_run)

    fake_ffmpeg = tmp_path / "ffmpeg.exe"
    fake_ffmpeg.write_bytes(b"")

    frames = me.extract_frames_from_video(
        "clip.mp4",
        str(tmp_path / "frames"),
        ffmpeg_path=str(fake_ffmpeg),
    )
    assert frames == []

    cmd = captured["cmd"]
    vf = cmd[cmd.index("-vf") + 1]
    filters = vf.split(",")
    assert any("fps=" in f for f in filters)
    scale_filters = [f for f in filters if f.startswith("scale=")]
    assert len(scale_filters) == 1
    scale = scale_filters[0]
    assert "force_original_aspect_ratio=decrease" in scale
    assert "force_divisible_by=2" in scale
    # 写死的正方形缩放不允许再出现
    assert "scale=1024:1024" not in filters
