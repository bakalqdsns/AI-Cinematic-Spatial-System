"""
End-to-end smoke test for project workspace endpoints.
Uses FastAPI's TestClient (in-process, no need to start uvicorn).
"""
import sys
from pathlib import Path

_backend_root = str(Path(__file__).parent.parent)
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

import tempfile
import shutil
import base64
from io import BytesIO

# Use isolated workspace for this test
from PIL import Image
import pytest

from app.config import settings
import importlib
from app.services.project_store import ProjectStore, project_store as _default_store
_ps_mod = importlib.import_module("app.services.project_store")
from fastapi.testclient import TestClient
from app.main import app


# ─── Create test PNG ───────────────────────────────────────────────────────────

def make_test_png_bytes() -> bytes:
    img = Image.new("RGB", (100, 100), color=(200, 100, 50))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ─── Tests via TestClient ────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path, monkeypatch):
    """Build a TestClient with workspace redirected to tmp."""
    tmp_ws = tmp_path / "projects"
    test_store = ProjectStore(workspace_dir=tmp_ws)
    monkeypatch.setattr(_ps_mod, "project_store", test_store)
    import app.endpoints_projects as ep_mod
    monkeypatch.setattr(ep_mod, "project_store", test_store)
    with TestClient(app) as c:
        yield c


def test_create_and_list_project(client):
    png_b64 = base64.b64encode(make_test_png_bytes()).decode()
    resp = client.post("/api/aicss/projects/json", json={
        "shotId": "smoke_shot",
        "imageBase64": f"data:image/png;base64,{png_b64}",
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["shotId"] == "smoke_shot"
    assert "projectId" in data
    pid = data["projectId"]

    # List
    resp = client.get("/api/aicss/projects")
    assert resp.status_code == 200
    listing = resp.json()
    assert any(p["projectId"] == pid for p in listing["projects"])


def test_manifest_endpoint(client):
    png_b64 = base64.b64encode(make_test_png_bytes()).decode()
    resp = client.post("/api/aicss/projects/json", json={
        "shotId": "manifest_shot",
        "imageBase64": f"data:image/png;base64,{png_b64}",
    })
    pid = resp.json()["projectId"]

    resp = client.get(f"/api/aicss/projects/{pid}/manifest")
    assert resp.status_code == 200
    m = resp.json()
    assert m["projectId"] == pid
    assert m["shotId"] == "manifest_shot"
    assert m["imageWidth"] == 100
    assert m["imageHeight"] == 100
    # inputHash is a 64-char hex (raw SHA-256)
    assert len(m["inputHash"]) == 64
    assert all(c in "0123456789abcdef" for c in m["inputHash"])


def test_checkpoint(client):
    png_b64 = base64.b64encode(make_test_png_bytes()).decode()
    resp = client.post("/api/aicss/projects/json", json={
        "shotId": "ckpt_shot",
        "imageBase64": f"data:image/png;base64,{png_b64}",
    })
    pid = resp.json()["projectId"]

    resp = client.post(f"/api/aicss/projects/{pid}/checkpoint", json={
        "phase": "analyze",
        "startedAt": "2026-06-30T22:00:00Z",
        "finishedAt": "2026-06-30T22:00:10Z",
        "durationMs": 10000,
    })
    assert resp.status_code == 200

    resp = client.get(f"/api/aicss/projects/{pid}/manifest")
    timeline = resp.json()["timeline"]
    assert any(t["phase"] == "analyze" for t in timeline)


def test_artifact_endpoint(client):
    png_b64 = base64.b64encode(make_test_png_bytes()).decode()
    resp = client.post("/api/aicss/projects/json", json={
        "shotId": "art_shot",
        "imageBase64": f"data:image/png;base64,{png_b64}",
    })
    pid = resp.json()["projectId"]

    # input/original.png should be readable
    resp = client.get(f"/api/aicss/projects/{pid}/artifacts/input/original.png")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    # Read it back with PIL
    img = Image.open(BytesIO(resp.content))
    assert img.size == (100, 100)


def test_delete_project(client):
    png_b64 = base64.b64encode(make_test_png_bytes()).decode()
    resp = client.post("/api/aicss/projects/json", json={
        "shotId": "del_shot",
        "imageBase64": f"data:image/png;base64,{png_b64}",
    })
    pid = resp.json()["projectId"]

    resp = client.delete(f"/api/aicss/projects/{pid}")
    assert resp.status_code == 200

    resp = client.get(f"/api/aicss/projects/{pid}/manifest")
    assert resp.status_code == 404


def test_path_traversal_blocked(client):
    """Attempt to read /artifacts/../../etc/passwd should be rejected."""
    png_b64 = base64.b64encode(make_test_png_bytes()).decode()
    resp = client.post("/api/aicss/projects/json", json={
        "shotId": "safe_shot",
        "imageBase64": f"data:image/png;base64,{png_b64}",
    })
    pid = resp.json()["projectId"]

    # Try path traversal in step
    resp = client.get(f"/api/aicss/projects/{pid}/artifacts/..%2F..%2Fetc/passwd")
    # Either 400 (regex blocks) or 404 (no such artifact) — both are safe
    assert resp.status_code in (400, 404)
