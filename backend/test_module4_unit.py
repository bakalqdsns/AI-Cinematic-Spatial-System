"""Unit tests for module-4 pure helpers (no GPU / Blender / LaMa weights)."""
from __future__ import annotations

import base64
import io

from PIL import Image


def _png_data_url(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


# ─── mesh_exporter ────────────────────────────────────────────────────────────

def test_compute_fine_z_offset():
    from app.services.mesh_exporter import _compute_fine_z_offset

    assert _compute_fine_z_offset(None, -2.0) == -2.0
    assert abs(_compute_fine_z_offset(128, -2.0) - (-2.0)) < 1e-9
    # 越暗（近）Z 越小，越亮（远）Z 越大；幅度约 ±0.64
    assert _compute_fine_z_offset(0, -2.0) < -2.0
    assert _compute_fine_z_offset(255, -2.0) > -2.0
    assert abs(_compute_fine_z_offset(0, -2.0) - (-2.64)) < 0.01
    assert abs(_compute_fine_z_offset(255, -2.0) - (-1.36)) < 0.01


def test_billboard_thickness_table():
    from app.services.mesh_exporter import _billboard_thickness

    assert _billboard_thickness("foreground") == 0.30
    assert _billboard_thickness("midground") == 0.20
    assert _billboard_thickness("background") == 0.12
    assert _billboard_thickness("sky") == 0.08
    assert _billboard_thickness("unknown") == 0.20


def test_populate_regions_and_strip_dedupe():
    from app.services.mesh_exporter import (
        SceneExportData,
        _populate_regions_into_scene,
        _populate_strip_stack_into_scene,
    )

    scene = SceneExportData(scene_id="t")
    _populate_strip_stack_into_scene(
        scene,
        [
            {
                "regionId": "r1",
                "billboardUrl": "data:image/png;base64,xx",
                "depthLayer": "foreground",
                "depthValue": 128,
                "colorIndex": 0,
                "layerPolygon": [[0, 0], [1, 0], [1, 1]],
                "inpaintResultUrl": "data:image/png;base64,bg",
            }
        ],
    )
    assert len(scene.strip_billboards) == 1
    assert scene.background_plane is not None

    _populate_regions_into_scene(
        scene,
        [
            {"id": "r1", "depthLayer": "midground", "depthValue": 100, "polygon": [[0, 0], [1, 0], [0, 1]]},
            {"id": "r2", "depthLayer": "background", "depthValue": 200, "polygon": [[0.1, 0.1], [0.9, 0.1], [0.5, 0.9]]},
        ],
    )
    # r1 deduped, r2 appended
    assert len(scene.strip_billboards) == 2
    assert {b.region_id for b in scene.strip_billboards} == {"r1", "r2"}


# ─── inpaint_utils ────────────────────────────────────────────────────────────

def test_compute_resize_ratio():
    from app.utils.inpaint_utils import _compute_resize_ratio

    assert _compute_resize_ratio((800, 600)) == 1.0
    assert abs(_compute_resize_ratio((2048, 1024)) - 0.5) < 1e-9


def test_encode_image_and_mask_for_lama():
    from app.utils.inpaint_utils import _encode_image_for_lama, _encode_mask_for_lama

    rgba = Image.new("RGBA", (64, 48), (10, 20, 30, 128))
    rgb, orig = _encode_image_for_lama(rgba, target_max_dim=1024)
    assert orig == (64, 48)
    assert rgb.mode == "RGB"
    assert rgb.size == (64, 48)

    mask = Image.new("L", (64, 48), 0)
    for y in range(10, 30):
        for x in range(10, 30):
            mask.putpixel((x, y), 255)
    enc = _encode_mask_for_lama(mask, (64, 48))
    assert enc.size == (64, 48)


def test_mask_white_ratio_and_weak_prompt():
    from app.utils.inpaint_utils import compute_mask_white_ratio, detect_weak_prompt

    mask = Image.new("L", (100, 100), 0)
    for y in range(50):
        for x in range(100):
            mask.putpixel((x, y), 255)
    assert abs(compute_mask_white_ratio(mask) - 0.5) < 0.01

    assert detect_weak_prompt("") is not None


# ─── occlusion_holes ──────────────────────────────────────────────────────────

def _object(oid: str, depth: float, rect: tuple[int, int, int, int], size=(64, 64)):
    w, h = size
    x0, y0, x1, y1 = rect
    mask = Image.new("L", (w, h), 0)
    for y in range(y0, y1):
        for x in range(x0, x1):
            mask.putpixel((x, y), 255)
    return {
        "id": oid,
        "depth": depth,
        "maskDataUrl": _png_data_url(mask),
        "polygon": [[x0 / w, y0 / h], [x1 / w, y0 / h], [x1 / w, y1 / h], [x0 / w, y1 / h]],
    }


def test_occlusion_holes_peel_and_merge():
    from app.services.occlusion_holes import (
        compute_occlusion_holes,
        merge_hole_masks,
        holes_to_dicts,
    )

    objs = [
        _object("near", 2.0, (10, 10, 40, 40)),
        _object("far", 8.0, (20, 20, 50, 50)),
    ]
    holes = compute_occlusion_holes(objs, image_width=64, image_height=64, mode="peel")
    assert len(holes) == 2
    assert all(h.white_ratio > 0 for h in holes)
    merged = merge_hole_masks(holes, (64, 64))
    assert merged and merged.startswith("data:image/png")
    d = holes_to_dicts(holes)
    assert d[0]["objectId"] in ("near", "far")


def test_occlusion_holes_occluded_interior():
    from app.services.occlusion_holes import compute_occlusion_holes

    objs = [
        _object("near", 2.0, (10, 10, 40, 40)),
        _object("far", 8.0, (20, 20, 50, 50)),
    ]
    holes = compute_occlusion_holes(
        objs,
        image_width=64,
        image_height=64,
        target_object_ids=["far"],
        mode="occluded_interior",
    )
    assert len(holes) == 1
    assert holes[0].object_id == "far"
    assert holes[0].mode == "occluded_interior"
    assert "near" in holes[0].occluder_ids
    assert holes[0].white_ratio > 0


def test_occlusion_holes_endpoint():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    objs = [_object("a", 3.0, (5, 5, 30, 30))]
    resp = client.post(
        "/api/aicss/occlusion-holes",
        json={
            "objects": objs,
            "imageWidth": 64,
            "imageHeight": 64,
            "mode": "peel",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["count"] == 1
    assert data["mergedMaskDataUrl"]
    assert data["holes"][0]["objectId"] == "a"
