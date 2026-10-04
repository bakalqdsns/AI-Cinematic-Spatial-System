"""End-to-end HTTP test for /api/aicss/v2/scripts/motion/generate.

Drives the route through FastAPI's TestClient, intercepts
``generate_motion_sequence`` (the function imported lazily inside the handler)
so that no real API keys, GPU or ffmpeg are needed, and asserts:

  * greenscreen / feather_edges from the request body actually flow through
    to ``generate_motion_sequence``;
  * the response shape matches ``MotionResponse``;
  * missing ffmpeg surfaces as a clear error message through the HTTP layer;
  * a default payload without the new fields still succeeds (backward-compat).
"""
from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _make_test_client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def test_motion_endpoint_default_payload(monkeypatch):
    """Monkeypatch the module-level symbol that endpoints_script.py
    imports lazily inside the handler (``from app.services.motion_extractor
    import generate_motion_sequence``).
    """
    me = importlib.import_module("app.services.motion_extractor")
    captured = {}

    async def fake_generate_motion_sequence(**kwargs):
        captured.update(kwargs)
        m = me.MotionSequence(
            shot_id=kwargs["shot_id"],
            character_id=kwargs["character_id"],
            character_name=kwargs["character_name"],
            action_description=kwargs["action_prompt"],
            status="done",
            video_path="/tmp/x.mp4",
            frame_count=0,
        )
        m.segmented_dir = None
        return m

    monkeypatch.setattr(me, "generate_motion_sequence", fake_generate_motion_sequence)

    client = _make_test_client()
    resp = client.post("/api/aicss/v2/scripts/motion/generate", json={
        "shot_id": "s1",
        "character_id": "c1",
        "character_name": "npc",
        "action_prompt": "walking",
        "duration_seconds": 3.0,
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "done"
    assert data["shot_id"] == "s1"
    assert data["character_id"] == "c1"
    assert data["frame_count"] == 0

    # Defaults must match module-2 contract: greenscreen off, feather on
    assert captured["greenscreen"] is False
    assert captured["feather_edges"] is True
    assert captured["video_provider"] == "dashscope"


def test_motion_endpoint_greenscreen_passthrough(monkeypatch):
    me = importlib.import_module("app.services.motion_extractor")
    captured = {}

    async def fake_generate_motion_sequence(**kwargs):
        captured.update(kwargs)
        m = me.MotionSequence(
            shot_id=kwargs["shot_id"],
            character_id=kwargs["character_id"],
            character_name=kwargs["character_name"],
            action_description=kwargs["action_prompt"],
            status="done",
        )
        m.segmented_dir = None
        return m

    monkeypatch.setattr(me, "generate_motion_sequence", fake_generate_motion_sequence)

    client = _make_test_client()
    resp = client.post("/api/aicss/v2/scripts/motion/generate", json={
        "shot_id": "s2",
        "character_id": "c2",
        "character_name": "knight",
        "action_prompt": "raising sword",
        "duration_seconds": 4.0,
        "greenscreen": True,
        "feather_edges": False,
    })
    assert resp.status_code == 200, resp.text
    assert captured["greenscreen"] is True, f"expected greenscreen=True, got {captured.get('greenscreen')}"
    assert captured["feather_edges"] is False, f"expected feather_edges=False, got {captured.get('feather_edges')}"


def test_motion_endpoint_returns_ffmpeg_error(monkeypatch):
    me = importlib.import_module("app.services.motion_extractor")

    async def fake_generate_motion_sequence(**kwargs):
        m = me.MotionSequence(
            shot_id=kwargs["shot_id"],
            character_id=kwargs["character_id"],
            character_name=kwargs["character_name"],
            action_description=kwargs["action_prompt"],
            status="error",
        )
        m.error = "ffmpeg not found in PATH. Install ffmpeg (https://ffmpeg.org/)"
        m.segmented_dir = None
        return m

    monkeypatch.setattr(me, "generate_motion_sequence", fake_generate_motion_sequence)

    client = _make_test_client()
    resp = client.post("/api/aicss/v2/scripts/motion/generate", json={
        "shot_id": "s3",
        "character_id": "c3",
        "character_name": "mage",
        "action_prompt": "casting spell",
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "error"


def test_motion_endpoint_greenscreen_string_coercion(monkeypatch):
    """Frontend may send ``greenscreen: "true"`` (JSON-stringified). Pydantic
    v2 lax mode coerces it to True, and we must propagate the bool through."""
    me = importlib.import_module("app.services.motion_extractor")
    captured = {}

    async def fake_generate_motion_sequence(**kwargs):
        captured.update(kwargs)
        m = me.MotionSequence(
            shot_id=kwargs["shot_id"], character_id=kwargs["character_id"],
            character_name=kwargs["character_name"],
            action_description=kwargs["action_prompt"], status="done",
        )
        m.segmented_dir = None
        return m

    monkeypatch.setattr(me, "generate_motion_sequence", fake_generate_motion_sequence)

    client = _make_test_client()
    resp = client.post("/api/aicss/v2/scripts/motion/generate", json={
        "shot_id": "s4", "character_id": "c4", "character_name": "rogue",
        "action_prompt": "sneaking", "greenscreen": "true",
    })
    assert resp.status_code == 200, resp.text
    # Pydantic v2 lax mode accepts "true" -> True
    assert captured["greenscreen"] is True


def test_motion_endpoint_appears_in_openapi():
    from app.main import app
    schema = app.openapi()
    # Find the route under /api/aicss/v2/scripts/motion/generate
    target = "/api/aicss/v2/scripts/motion/generate"
    found = False
    for path, methods in schema.get("paths", {}).items():
        if path.endswith("/scripts/motion/generate"):
            assert "post" in methods
            body_ref = methods["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
            assert body_ref.endswith("GenerateMotionRequest"), body_ref
            found = True
            break
    assert found, f"route {target} not in OpenAPI"
    print(f"  [e2e] OpenAPI exposes request schema: {body_ref.split('/')[-1]}")


if __name__ == "__main__":
    # Provide a minimal monkeypatch stand-in for direct invocation.
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
