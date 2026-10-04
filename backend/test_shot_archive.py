"""Unit tests for shot archive packer (no GPU / Blender)."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from PIL import Image


def test_build_shot_archive(tmp_path: Path):
    from app.services.shot_archiver import build_shot_archive

    project_id = "20260101_demo"
    shot_id = "shot_001"
    proj = tmp_path / project_id
    (proj / "shots" / shot_id / "frames").mkdir(parents=True)
    (proj / "shots" / shot_id / "frames" / "0.json").write_text("{}", encoding="utf-8")
    (proj / "characters" / "hero").mkdir(parents=True)
    Image.new("RGB", (8, 8), (255, 0, 0)).save(proj / "characters" / "hero" / "front.png")
    (proj / "scenes" / "forest").mkdir(parents=True)
    Image.new("RGB", (8, 8), (0, 255, 0)).save(proj / "scenes" / "forest" / "wide.png")
    (proj / "layers").mkdir(parents=True)
    for name in ("foreground", "midground", "background", "sky"):
        Image.new("RGBA", (8, 8), (0, 0, 255, 128)).save(proj / "layers" / f"{name}.png")
    (proj / "meshes" / "scenes").mkdir(parents=True)
    (proj / "meshes" / "scenes" / "scene.glb").write_bytes(b"glTF")
    (proj / "manifest.json").write_text(
        json.dumps({"project_id": project_id, "image_width": 8, "image_height": 8}),
        encoding="utf-8",
    )

    result = build_shot_archive(
        project_id,
        shot_id,
        workspace_dir=tmp_path,
        output_path=tmp_path / "out.zip",
    )
    assert Path(result["zipPath"]).is_file()
    assert result["fileSize"] > 0
    assert result["fileCount"] >= 5

    with zipfile.ZipFile(result["zipPath"]) as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names
        assert "scripts/blender_import.py" in names
        assert "scripts/lighting.json" in names
        assert "layers/foreground.png" in names
        assert any(n.startswith("character/") for n in names)
        assert any(n.startswith("mesh/") for n in names)
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["shotId"] == shot_id
        assert "foreground" in manifest["layers"]
        assert manifest["layers"]["foreground"].startswith("layers/")


def test_archive_shot_cli(tmp_path: Path):
    project_id = "cli_proj"
    shot_id = "shot_x"
    proj = tmp_path / project_id
    (proj / "shots" / shot_id).mkdir(parents=True)
    (proj / "layers").mkdir(parents=True)
    Image.new("RGBA", (4, 4), (1, 2, 3, 255)).save(proj / "layers" / "sky.png")

    from scripts.archive_shot import main

    code = main([
        "--project-id", project_id,
        "--shot-id", shot_id,
        "--workspace", str(tmp_path),
        "--output", str(tmp_path / "cli2.zip"),
    ])
    assert code == 0
    assert (tmp_path / "cli2.zip").is_file()
    with zipfile.ZipFile(tmp_path / "cli2.zip") as zf:
        assert "manifest.json" in zf.namelist()
