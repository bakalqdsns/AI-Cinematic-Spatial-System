"""
Unit tests for app.services.project_store
"""
import json
import pytest
import shutil
import tempfile
from pathlib import Path

import asyncio

from app.services.project_store import (
    ProjectStore,
    ProjectManifest,
    ArtifactFile,
    PhaseEntry,
    TimelineEvent,
    _sha256,
)


# ─── Isolated store factory ────────────────────────────────────────────────────

def make_store() -> tuple[ProjectStore, Path]:
    """Create a ProjectStore backed by a fresh temp directory."""
    tmp = Path(tempfile.mkdtemp(prefix="aicss_test_ws_"))
    store = ProjectStore(workspace_dir=tmp / "projects")
    return store, tmp


# ─── Data ─────────────────────────────────────────────────────────────────────

SAMPLE_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01"
    b"\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _run(coro):
    """Run a coroutine in a shared event loop for the current test."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─── Tests ─────────────────────────────────────────────────────────────────────

class TestProjectStoreCreate:
    def test_create_makes_directory(self):
        store, tmp = make_store()
        try:
            info = _run(store.create("shot_001", SAMPLE_PNG, 1920, 1080))
            assert "projectId" in info
            assert info["shotId"] == "shot_001"
            assert info["inputHash"]
            proj_dir = store._project_dir(info["projectId"])
            assert proj_dir.exists()
            assert (proj_dir / "input" / "original.png").read_bytes() == SAMPLE_PNG
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_create_id_format(self):
        store, tmp = make_store()
        try:
            info = _run(store.create("myshot", SAMPLE_PNG, 800, 600))
            pid = info["projectId"]
            parts = pid.split("_", 3)
            assert len(parts) == 3   # date + time + shotId (2 underscores)
            assert parts[2] == "myshot"
            assert len(parts[0]) == 8   # YYYYMMDD
            assert len(parts[1]) == 6   # HHMMSS
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestProjectStoreManifest:
    def test_manifest_created(self):
        store, tmp = make_store()
        try:
            info = _run(store.create("shot_002", SAMPLE_PNG, 1280, 720))
            manifest = _run(store.read_manifest(info["projectId"]))
            assert manifest.project_id == info["projectId"]
            assert manifest.shot_id == "shot_002"
            assert manifest.image_width == 1280
            assert manifest.image_height == 720
            assert manifest.input_hash == info["inputHash"]
            assert manifest.artifacts == {}
            assert manifest.timeline == []
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestProjectStoreSaveStep:
    def test_save_step_writes_binary(self):
        store, tmp = make_store()
        try:
            info = _run(store.create("shot_003", SAMPLE_PNG, 1024, 768))
            pid = info["projectId"]
            _run(store.save_step(pid, "depth", {"depth_map.png": b"fake depth"}))
            loaded = _run(store.load_artifact(pid, "depth", "depth_map.png"))
            assert loaded == b"fake depth"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_save_step_writes_json(self):
        store, tmp = make_store()
        try:
            info = _run(store.create("shot_004", SAMPLE_PNG, 512, 512))
            pid = info["projectId"]
            _run(store.save_step(pid, "masks", {"objects.json": {"objects": [{"id": "obj1"}, {"id": "obj2"}]}}))
            loaded = _run(store.load_artifact(pid, "masks", "objects.json"))
            assert isinstance(loaded, dict)
            assert loaded["objects"][0]["id"] == "obj1"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_save_step_updates_manifest(self):
        store, tmp = make_store()
        try:
            info = _run(store.create("shot_005", SAMPLE_PNG, 640, 480))
            pid = info["projectId"]
            _run(store.save_step(pid, "depth", {"depth_map.png": b"x" * 100}))
            manifest = _run(store.read_manifest(pid))
            assert "depth" in manifest.artifacts
            depth_entry = manifest.artifacts["depth"]
            assert any(f.name == "depth_map.png" for f in depth_entry.files)
            assert depth_entry.files[0].size > 0
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_save_step_multiple_files(self):
        store, tmp = make_store()
        try:
            info = _run(store.create("shot_006", SAMPLE_PNG, 800, 600))
            pid = info["projectId"]
            _run(store.save_step(pid, "depth", {"depth_map.png": b"depth", "depth_colormap.png": b"colormap"}))
            assert _run(store.load_artifact(pid, "depth", "depth_map.png")) == b"depth"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_load_artifact_not_found(self):
        store, tmp = make_store()
        try:
            info = _run(store.create("shot_007", SAMPLE_PNG, 800, 600))
            pid = info["projectId"]
            with pytest.raises(FileNotFoundError):
                _run(store.load_artifact(pid, "depth", "does_not_exist.png"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestProjectStoreAtomicity:
    def test_manifest_valid_after_multiple_saves(self):
        store, tmp = make_store()
        try:
            info = _run(store.create("shot_atomic", SAMPLE_PNG, 100, 100))
            pid = info["projectId"]
            _run(store.save_step(pid, "depth", {"depth_map.png": b"d"}))
            _run(store.save_step(pid, "segment", {"objects.json": {"objects": []}}))
            manifest = _run(store.read_manifest(pid))
            assert "depth" in manifest.artifacts
            assert "segment" in manifest.artifacts
            d = manifest.to_dict()
            assert isinstance(d["projectId"], str)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestProjectStoreList:
    def test_list_projects_returns_summary(self):
        store, tmp = make_store()
        try:
            info1 = _run(store.create("shot_list1", SAMPLE_PNG, 1920, 1080))
            info2 = _run(store.create("shot_list2", SAMPLE_PNG, 1280, 720))
            summaries = _run(store.list_projects())
            ids = [s.project_id for s in summaries]
            assert info1["projectId"] in ids
            assert info2["projectId"] in ids
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_list_sorted_by_updated(self):
        store, tmp = make_store()
        try:
            _run(store.create("shot_old", SAMPLE_PNG, 100, 100))
            info_new = _run(store.create("shot_new", SAMPLE_PNG, 100, 100))
            summaries = _run(store.list_projects())
            ids = [s.project_id for s in summaries]
            assert ids[0] == info_new["projectId"]
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestProjectStoreDelete:
    def test_delete_project_removes_directory(self):
        store, tmp = make_store()
        try:
            info = _run(store.create("shot_del", SAMPLE_PNG, 200, 200))
            pid = info["projectId"]
            assert store._project_dir(pid).exists()
            _run(store.delete_project(pid))
            assert not store._project_dir(pid).exists()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_delete_nonexistent_raises(self):
        store, tmp = make_store()
        try:
            with pytest.raises(FileNotFoundError):
                _run(store.read_manifest("nonexistent_project_id"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestProjectStoreTimeline:
    def test_append_timeline(self):
        store, tmp = make_store()
        try:
            info = _run(store.create("shot_tl", SAMPLE_PNG, 300, 300))
            pid = info["projectId"]
            _run(store.append_timeline(
                pid,
                phase="analyze",
                started_at="2026-06-30T22:00:00Z",
                finished_at="2026-06-30T22:00:10Z",
                duration_ms=10000,
            ))
            manifest = _run(store.read_manifest(pid))
            assert len(manifest.timeline) == 1
            assert manifest.timeline[0].phase == "analyze"
            assert manifest.timeline[0].duration_ms == 10000
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestHelperFunctions:
    def test_sha256(self):
        h = _sha256(b"hello")
        assert len(h) == 64
        assert h == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"

    def test_manifest_to_dict_roundtrip(self):
        manifest = ProjectManifest(
            project_id="test_pid",
            shot_id="shot_test",
            created_at="2026-06-30T22:00:00Z",
            updated_at="2026-06-30T22:01:00Z",
            image_width=1920,
            image_height=1080,
            input_hash="sha256:abc123",
            artifacts={},
            timeline=[],
        )
        d = manifest.to_dict()
        restored = ProjectManifest.from_dict(d)
        assert restored.project_id == manifest.project_id
        assert restored.shot_id == manifest.shot_id
        assert restored.input_hash == manifest.input_hash

    def test_manifest_from_dict_backward_compat(self):
        d = {
            "projectId": "pid1",
            "shotId": "shot1",
            "createdAt": "2026-01-01T00:00:00Z",
            "updatedAt": "2026-01-01T00:01:00Z",
            "image_width": 640,
            "image_height": 480,
            "inputHash": "sha256:xyz",
            "artifacts": {},
            "timeline": [],
        }
        m = ProjectManifest.from_dict(d)
        assert m.image_width == 640
        assert m.image_height == 480
