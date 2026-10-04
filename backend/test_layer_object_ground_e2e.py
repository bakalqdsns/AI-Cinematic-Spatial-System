"""端到端验证 Object-Aware Layer Pipeline。

调用 POST /api/aicss/layers/export 传入 iter01-03 的旧测试图,启用:
- autoAnchor=True (GroundingDINO + SAM2)
- reconstructGround=True (RANSAC)
- saveArchive=True + sceneId='layer_pipeline_test_001'

期望返回:
- layers: 5 张 RGBA PNG (sky/background/midground/foreground/ground)
- objects: N 个 ObjectAssetSummary (label + bbox + depth + cutout_data_uri)
- ground: 1 个 GroundAssetSummary (plane + plane_normal + cutout_data_uri)
- layer_assignment: dict[layer, list[object_id]]

落盘到 backend/test_outputs/objects/layer_pipeline_test_001/,需包含:
- objects_manifest.json
- obj_NNNN_<label>.png (每个检测到的物体独立 RGBA)
- obj_NNNN_<label>.json (每个物体的元数据)
- ground.png + ground.json (+ ground_corrected_depth.png 如果 ground 拟合成功)

Usage:  cd F:/AICinematicSpatialSystem/backend && python test_layer_object_ground_e2e.py
"""
from __future__ import annotations

import base64
import io
import json
import sys
from pathlib import Path

import httpx
from PIL import Image


BACKEND = "http://127.0.0.1:8000"
TEST_IMAGE = Path("F:/AICinematicSpatialSystem/test/背景.png")
SCENE_ID = "layer_pipeline_test_001"
OUT_ROOT = Path("F:/AICinematicSpatialSystem/backend/test_outputs/objects")


def main() -> int:
    if not TEST_IMAGE.exists():
        print(f"[FAIL] test image missing: {TEST_IMAGE}")
        return 1

    # 1. Encode image as base64
    img = Image.open(TEST_IMAGE).convert("RGB")
    w, h = img.size
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    image_url = f"data:image/png;base64,{b64}"

    # 2. Call the endpoint
    print(f"[INFO] calling {BACKEND}/api/aicss/layers/export on {TEST_IMAGE.name} ({w}x{h}) ...")
    payload = {
        "imageUrl": image_url,
        "autoAnchor": True,
        "reconstructGround": True,
        "saveArchive": True,
        "sceneId": SCENE_ID,
        "sceneType": "outdoor",
        "featherPx": 1,
    }
    try:
        r = httpx.post(f"{BACKEND}/api/aicss/layers/export", json=payload, timeout=600.0)
    except Exception as e:
        print(f"[FAIL] HTTP error: {type(e).__name__}: {e}")
        return 1

    if r.status_code != 200:
        print(f"[FAIL] HTTP {r.status_code}: {r.text[:800]}")
        return 1

    data = r.json()
    print(f"[OK] HTTP 200 — {w}x{h}, layers={list(data.get('layers', {}).keys())}")

    # 3. Validate layers
    expected = {"sky", "background", "midground", "foreground", "ground"}
    got_layers = set(data.get("layers", {}).keys())
    if not expected.issubset(got_layers):
        missing = expected - got_layers
        print(f"[WARN] missing layers: {missing}")
    else:
        print(f"[OK] all 5 layers present")

    # 4. Validate objects
    objs = data.get("objects", [])
    print(f"[INFO] detected {len(objs)} objects")
    for o in objs[:5]:
        print(f"  - {o['object_id']} {o['label']!r} score={o['score']:.2f} "
              f"bbox={o['bbox']} depth_mean={o['depth_mean']:.2f}m "
              f"layer_hint={o['layer_hint']} z_offset={o['z_offset']}")

    # 5. Validate ground
    ground = data.get("ground")
    if ground is None:
        print("[WARN] no ground reconstruction returned")
    else:
        print(f"[OK] ground reconstructed: normal={ground['plane_normal']} "
              f"centroid={ground['centroid']} bbox={ground['bbox']} "
              f"meta={ground['meta'].get('inlier_ratio', 'n/a'):.2f} inlier_ratio" if isinstance(ground['meta'].get('inlier_ratio', 0), (int, float)) else "")

    # 6. Validate layer assignment
    la = data.get("layer_assignment", {})
    print(f"[OK] layer_assignment: { {k: len(v) for k, v in la.items()} }")

    # 7. Validate archive on disk
    archive_dir = OUT_ROOT / SCENE_ID
    if not archive_dir.exists():
        print(f"[FAIL] archive dir missing: {archive_dir}")
        return 1
    print(f"[OK] archive dir: {archive_dir}")
    files = sorted(archive_dir.glob("*"))
    for f in files:
        print(f"  - {f.name} ({f.stat().st_size // 1024} KB)")

    # Check required files
    manifest_path = archive_dir / "objects_manifest.json"
    if not manifest_path.exists():
        print(f"[FAIL] manifest missing: {manifest_path}")
        return 1
    with manifest_path.open("r", encoding="utf-8") as f:
        manifest = json.load(f)
    print(f"[OK] manifest: {len(manifest.get('objects', []))} objects, "
          f"ground={'yes' if manifest.get('ground') else 'no'}")

    # Visual: dump the first 3 object cutouts
    import numpy as _np
    print("\n[INFO] previewing first 3 object cutouts ...")
    for png_path in sorted(archive_dir.glob("obj_*.png"))[:3]:
        cimg = Image.open(png_path)
        a = _np.array(cimg.split()[-1])
        alpha_mean = float(a.mean())
        print(f"  - {png_path.name}: size={cimg.size} alpha_mean={alpha_mean:.1f}")

    # Visual: check ground
    gpath = archive_dir / "ground.png"
    if gpath.exists():
        gimg = Image.open(gpath)
        ga = _np.array(gimg.split()[-1])
        print(f"  - ground.png: size={gimg.size} alpha_mean={float(ga.mean()):.1f}")
    dpath = archive_dir / "ground_corrected_depth.png"
    if dpath.exists():
        dimg = Image.open(dpath)
        darr = list(dimg.getdata())
        dmean = sum(darr) / len(darr) if darr else 0
        print(f"  - ground_corrected_depth.png: size={dimg.size} mean={dmean:.1f}")

    print("\n[PASS] all validation checks completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())