"""项目路径必须留在工作区里。"""
import asyncio
import shutil
import tempfile
from pathlib import Path

import pytest

from app.services.path_safety import PathEscapeError, contained_file, resolve_contained
from app.services.project_store import ProjectStore


SAMPLE_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01"
    b"\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_resolve_contained_rejects_parent_segment(tmp_path: Path):
    root = tmp_path / "projects"
    root.mkdir()
    (root / "ok").mkdir()
    assert resolve_contained(root, "ok") == (root / "ok").resolve()
    with pytest.raises(PathEscapeError):
        resolve_contained(root, "..")
    with pytest.raises(PathEscapeError):
        resolve_contained(root, "ok/../../outside")


def test_contained_file_rejects_outside_path(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("nope", encoding="utf-8")
    inside = root / "clip.mp4"
    inside.write_bytes(b"mp4")
    assert contained_file(root, str(inside)) == inside.resolve()
    assert contained_file(root, "clip.mp4") == inside.resolve()
    with pytest.raises(PathEscapeError):
        contained_file(root, str(outside))
    with pytest.raises(PathEscapeError):
        contained_file(root, "../secret.txt")


def test_delete_parent_id_does_not_remove_workspace_parent():
    tmp = Path(tempfile.mkdtemp(prefix="aicss_path_"))
    try:
        marker = tmp / "keep.txt"
        marker.write_text("keep", encoding="utf-8")
        store = ProjectStore(workspace_dir=tmp / "projects")
        with pytest.raises(PathEscapeError):
            _run(store.delete_project(".."))
        assert marker.is_file()
        assert marker.read_text(encoding="utf-8") == "keep"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_create_slugifies_shot_id_inside_workspace():
    tmp = Path(tempfile.mkdtemp(prefix="aicss_path_"))
    try:
        workspace = tmp / "projects"
        store = ProjectStore(workspace_dir=workspace)
        info = _run(store.create("../outside", SAMPLE_PNG, 8, 8))
        proj = store._project_dir(info["projectId"])
        assert proj.parent.resolve() == workspace.resolve()
        assert proj.is_dir()
        assert ".." not in proj.name
        assert not (tmp / "outside").exists()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
