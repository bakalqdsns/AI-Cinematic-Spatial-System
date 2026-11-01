"""人物平面选帧：有抠像目录时用 segmented/ 里的 png，不用绿底整帧。"""
import importlib.util
import os
from pathlib import Path

from app.services.shot_archiver import _collect_characters, _select_action_frames


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def test_select_action_frames_prefers_segmented_pngs(tmp_path: Path):
    action = tmp_path / "walk"
    for i in range(3):
        _touch(action / f"frame_{i:04d}.png")
    # 实际抠像文件名不一定是 seg_ 前缀
    _touch(action / "segmented" / "hero_walk_0000.png")
    _touch(action / "segmented" / "hero_walk_0001.png")
    _touch(action / "segmented" / "notes.txt")

    frames_dir, count = _select_action_frames(action)
    assert frames_dir == action / "segmented"
    assert count == 2


def test_select_action_frames_falls_back_to_motion_frames(tmp_path: Path):
    action = tmp_path / "idle"
    _touch(action / "frame_0001.png")
    _touch(action / "frame_0002.png")
    (action / "segmented").mkdir()

    frames_dir, count = _select_action_frames(action)
    assert frames_dir == action
    assert count == 2

    bare = tmp_path / "run"
    _touch(bare / "frame_0001.png")
    frames_dir, count = _select_action_frames(bare)
    assert frames_dir == bare
    assert count == 1


def test_collect_characters_points_frames_dir_at_segmented(tmp_path: Path):
    action = tmp_path / "motions" / "hero" / "walk"
    for i in range(4):
        _touch(action / f"frame_{i:04d}.png")
    for i in range(2):
        _touch(action / "segmented" / f"seg_{i:04d}.png")
    (action / "_meta.json").write_text('{"fps": 12}', encoding="utf-8")

    chars = _collect_characters(tmp_path)
    assert len(chars) == 1
    row = chars[0]
    assert row["id"] == "hero"
    assert os.path.normcase(row["framesDir"]) == os.path.normcase(
        os.path.abspath(str(action / "segmented"))
    )
    assert row["frameCount"] == 2
    assert row["fps"] == 12


def test_collect_characters_uses_raw_frames_without_cutouts(tmp_path: Path):
    action = tmp_path / "motions" / "hero" / "idle"
    for i in range(3):
        _touch(action / f"frame_{i:04d}.png")

    chars = _collect_characters(tmp_path)
    assert len(chars) == 1
    assert os.path.normcase(chars[0]["framesDir"]) == os.path.normcase(
        os.path.abspath(str(action))
    )
    assert chars[0]["frameCount"] == 3
    assert chars[0]["fps"] == 24


def _load_list_frames():
    path = (
        Path(__file__).resolve().parents[1]
        / "blender"
        / "addons"
        / "aicss_scene_builder"
        / "operators"
        / "import_character_frames.py"
    )
    spec = importlib.util.spec_from_file_location("aicss_import_character_frames", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._list_frames


def test_list_frames_prefers_seg_prefix(tmp_path: Path):
    _list_frames = _load_list_frames()
    for name in ("frame_0002.png", "seg_0002.png", "frame_0001.png", "seg_0001.png", "other.png"):
        _touch(tmp_path / name)

    listed = [os.path.basename(p) for p in _list_frames(str(tmp_path))]
    assert listed == ["seg_0001.png", "seg_0002.png"]

    raw_only = tmp_path / "raw"
    _touch(raw_only / "frame_0002.png")
    _touch(raw_only / "frame_0001.png")
    listed = [os.path.basename(p) for p in _list_frames(str(raw_only))]
    assert listed == ["frame_0001.png", "frame_0002.png"]
