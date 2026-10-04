"""Integration tests for the ffmpeg dependency probe.

Verifies that ``extract_frames_from_video`` reports actionable errors when
ffmpeg is missing and that the upper layer (``generate_motion_sequence``)
captures those errors into ``MotionSequence.error``.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def test_extract_frames_raises_runtime_error_when_missing(monkeypatch):
    from app.services.motion_extractor import extract_frames_from_video

    monkeypatch.setattr("shutil.which", lambda _: None)
    raised = False
    try:
        extract_frames_from_video("/tmp/none.mp4", "/tmp/frames-out")
    except RuntimeError as e:
        raised = True
        assert "ffmpeg" in str(e).lower()
        assert "PATH" in str(e)
    assert raised, "expected RuntimeError when ffmpeg is missing"


def test_extract_frames_wraps_subprocess_errors(monkeypatch):
    from app.services.motion_extractor import extract_frames_from_video

    monkeypatch.setattr("shutil.which", lambda _: "/fake/ffmpeg")

    class R:
        returncode = 1
        stderr = "decoder not found"

    monkeypatch.setattr("subprocess.run", lambda *a, **kw: R())
    raised = False
    try:
        extract_frames_from_video("/tmp/none.mp4", "/tmp/frames-out")
    except RuntimeError as e:
        raised = True
        msg = str(e)
        assert "ffmpeg failed" in msg
        assert "decoder not found" in msg
    assert raised


def test_generate_motion_sequence_records_ffmpeg_error(monkeypatch):
    """When extract_frames raises, MotionSequence.error must surface the cause."""
    from app.services.motion_extractor import generate_motion_sequence

    async def fake_generate_action_video(**kwargs):
        return "/tmp/fake.mp4"

    monkeypatch.setattr(
        "app.services.motion_extractor.generate_action_video",
        fake_generate_action_video,
    )

    monkeypatch.setattr("shutil.which", lambda _: None)

    motion = asyncio.run(
        generate_motion_sequence(
            shot_id="s1",
            character_id="c1",
            character_name="npc",
            action_prompt="walking",
        )
    )
    assert motion.status == "error"
    assert "ffmpeg" in (motion.error or "").lower()


if __name__ == "__main__":
    test_extract_frames_raises_runtime_error_when_missing.__wrapped__ if False else None
    # Allow running directly (without pytest's monkeypatch) for quick sanity.
    import builtins
    print("Run via pytest to execute monkeypatch-based tests.")
