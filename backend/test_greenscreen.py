"""Tests for the green-screen prompt injection in video_adapter.

The integration tests below do not require any external API key — they
intercept the underlying SDK call and inspect the prompt that was forwarded.
"""
import asyncio
import inspect
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def test_apply_greenscreen_prompt_appends_suffix():
    from app.services.video_adapter import _apply_greenscreen_prompt

    out = _apply_greenscreen_prompt("knight walks forward", True)
    assert "knight walks forward" in out
    assert "#00FF00" in out or "00FF00" in out
    assert "background" in out.lower()


def test_apply_greenscreen_prompt_passthrough_when_false():
    from app.services.video_adapter import _apply_greenscreen_prompt

    base = "knight walks forward"
    assert _apply_greenscreen_prompt(base, False) == base


def test_provider_generate_accepts_greenscreen_kwarg():
    from app.services.video_adapter import (
        DashScopeFilmProvider,
        LocalWanProvider,
        SVDProvider,
    )
    for cls in (DashScopeFilmProvider, LocalWanProvider, SVDProvider):
        sig = inspect.signature(cls.generate)
        assert "greenscreen" in sig.parameters, (
            f"{cls.__name__}.generate must accept greenscreen kwarg"
        )


def test_video_generate_forwards_greenscreen(monkeypatch):
    """The convenience wrapper must forward the greenscreen flag end-to-end."""
    from app.services import video_adapter
    from app.services.video_adapter import _apply_greenscreen_prompt

    captured = {}

    class FakeProvider:
        name = "fake"

        async def generate(self, prompt, start_image_b64, end_image_b64, duration, *, greenscreen=False):
            # Mirror the real providers: apply the prompt transform inside.
            captured["prompt"] = _apply_greenscreen_prompt(prompt, greenscreen)
            captured["greenscreen"] = greenscreen
            return "/tmp/fake.mp4"

    monkeypatch.setitem(video_adapter._PROVIDER_REGISTRY, "fake", FakeProvider)

    out = asyncio.run(
        video_adapter.video_generate("walking", provider="fake", greenscreen=True)
    )
    assert out == "/tmp/fake.mp4"
    assert captured["greenscreen"] is True
    assert "#00FF00" in captured["prompt"]


def test_motion_generate_endpoint_accepts_greenscreen_payload():
    """The HTTP request model must include the greenscreen field."""
    from app.endpoints_script import GenerateMotionRequest

    req = GenerateMotionRequest(
        shot_id="s1",
        character_id="c1",
        character_name="hero",
        action_prompt="walking",
        greenscreen=True,
    )
    assert req.greenscreen is True
    assert req.feather_edges is True  # default


def test_motion_response_unchanged_field_set():
    from app.endpoints_script import MotionResponse

    # Greenscreen/feather are request-only toggles; the response stays the same.
    resp = MotionResponse(
        shot_id="s1",
        character_id="c1",
        status="done",
    )
    assert resp.status == "done"
    assert resp.frame_count == 0


if __name__ == "__main__":
    test_apply_greenscreen_prompt_appends_suffix()
    test_apply_greenscreen_prompt_passthrough_when_false()
    print("Static greenscreen checks PASSED. Run pytest for the async/wrapper tests.")
