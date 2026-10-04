"""
strip-stack 逐层剥离导出 e2e 测试。

Pipeline:
  1. 加载 test/背景.png
  2. 手工定义 3 个 strip region (前景/中景/背景)
  3. 对每个 region:
     a) 调用 /api/aicss/billboard 抠出 billboardUrl
     b) 用 PIL + ImageDraw 构造 polygon mask
     c) 调用 /api/aicss/inpaint (LaMa backend) 抹掉该 region
     d) 把 billboardUrl / inpaintResultUrl / polygon / depth 写入 stripStack step
  4. 调用 /api/aicss/v2/meshes/export-scene 传入 strip_stack
  5. 下载 GLB 做结构性格断言:
     - 文件存在 + size > 1KB
     - GLB magic 头正确
     - JSON chunk 中 meshes/nodes/textures/images/materials 数 >= len(strip_stack) + 1
     - BackgroundPlane mesh 存在
     - 每个 RegionMesh_<regionId> 都存在
  6. 落盘到 backend/test_outputs/strip_stack_e2e/

Blender 不可用时优雅降级（不 fail）。

Usage:
    cd F:/AICinematicSpatialSystem/backend && python test_strip_stack_export_e2e.py
"""
from __future__ import annotations

import base64
import io
import json
import os
import struct
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

import httpx
import numpy as np
from PIL import Image, ImageDraw


BACKEND = "http://127.0.0.1:8000"
TEST_IMAGE = Path(r"F:\AICinematicSpatialSystem\test\背景.png")
OUT_DIR = Path(__file__).resolve().parent / "test_outputs" / "strip_stack_e2e"
PROJECT_ID = "strip_stack_e2e_project"

# 3 个手工 strip region（前景 / 中景 / 背景），按 test/背景.png 实际内容定位：
#   - 人物：左前方校园女生（前景）
#   - 中景：右侧大树（midground 树）
#   - 天空：顶部云朵 + 太阳（背景天空）
STRIP_REGIONS = [
    {
        "name": "foreground_person",
        "bbox": {"x": 0.165, "y": 0.225, "w": 0.190, "h": 0.700},
        "depth_layer": "foreground",
        "depth_value": 90,
    },
    {
        "name": "midground_tree",
        "bbox": {"x": 0.770, "y": 0.230, "w": 0.180, "h": 0.580},
        "depth_layer": "midground",
        "depth_value": 128,
    },
    {
        "name": "background_sky",
        "bbox": {"x": 0.380, "y": 0.030, "w": 0.260, "h": 0.200},
        "depth_layer": "background",
        "depth_value": 180,
    },
]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


_FAILS: list[str] = []


def ok(cond: bool, label: str) -> bool:
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {label}", flush=True)
    if not cond:
        _FAILS.append(label)
    return bool(cond)


def bbox_to_polygon(bbox: dict) -> list[list[float]]:
    """归一化 bbox → 矩形 4 点多边形（逆时针）。"""
    x, y, w, h = bbox["x"], bbox["y"], bbox["w"], bbox["h"]
    return [
        [x,     y    ],
        [x + w, y    ],
        [x + w, y + h],
        [x,     y + h],
    ]


def make_polygon_mask(width: int, height: int, polygon_uv: list[list[float]]) -> str:
    """构造归一化 0-1 多边形对应的 RGBA mask PNG data URI：
    多边形内部 alpha=255（白），外部 alpha=0（黑）。
    PIL 坐标 (x, y) = (int(px*width), int(py*height))。
    """
    mask = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(mask)
    pts = [(int(px * width), int(py * height)) for px, py in polygon_uv]
    draw.polygon(pts, fill=(255, 255, 255, 255))
    buf = io.BytesIO()
    mask.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def load_image_as_data_url(path: Path) -> tuple[str, int, int]:
    img = Image.open(path).convert("RGB")
    w, h = img.size
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}", w, h


def strip_once(
    client: httpx.Client,
    image_url: str,
    polygon_uv: list[list[float]],
    bbox: dict,
    object_id: str,
    width: int,
    height: int,
) -> tuple[str, str]:
    """一次 strip 操作：先抠 billboard，再用 polygon mask LaMa inpaint。
    返回 (billboardUrl, inpaintResultUrl)。
    """
    bb_resp = client.post(
        f"{BACKEND}/api/aicss/billboard",
        json={
            "imageUrl": image_url,
            "objectId": object_id,
            "boundingBox": bbox,
            "polygon": polygon_uv,
            "projectId": PROJECT_ID,
        },
        timeout=60.0,
    )
    bb_resp.raise_for_status()
    bb_json = bb_resp.json()
    billboard_url = bb_json.get("billboardUrl") or bb_json.get("rgbaUrl")
    if not billboard_url:
        raise ValueError(f"billboardUrl missing in response: {bb_json.keys()}")

    mask_uri = make_polygon_mask(width, height, polygon_uv)

    inp_resp = client.post(
        f"{BACKEND}/api/aicss/inpaint",
        json={
            "imageUrl": image_url,
            "maskDataUrl": mask_uri,
            "prompt": "natural background",  # LaMa 是 blind inpainting，prompt 占位
            "projectId": PROJECT_ID,
        },
        timeout=300.0,
    )
    inp_resp.raise_for_status()
    inp_json = inp_resp.json()
    inpaint_url = inp_json.get("inpaintResultUrl") or inp_json.get("imageUrl")
    if not inpaint_url:
        raise ValueError(f"inpaintResultUrl missing in response: {inp_json.keys()}")

    return billboard_url, inpaint_url


def parse_glb_header(path: Path) -> dict:
    """解析 GLB (binary glTF 2.0) 文件头与 JSON chunk。

    Returns: {version, length, json, raw_size}
    Raises: ValueError if not a valid GLB.
    """
    data = path.read_bytes()
    if len(data) < 12:
        raise ValueError(f"GLB too small: {len(data)} bytes")
    magic = data[:4]
    if magic != b"glTF":
        raise ValueError(f"Not a GLB file (magic={magic!r})")
    version, length = struct.unpack_from("<II", data, 4)
    json_chunk_length, json_chunk_type = struct.unpack_from("<II", data, 12)
    if json_chunk_type != 0x4E4F534A:  # "JSON" as little-endian uint32
        raise ValueError(f"First chunk type invalid: {hex(json_chunk_type)}")
    json_data = data[20:20 + json_chunk_length]
    # JSON chunk 必须按 4 字节对齐，可能用空格 (0x20) 或 NUL (0x00) 填充
    json_data = json_data.rstrip(b"\x00").rstrip(b" ")
    json_obj = json.loads(json_data)
    return {
        "version": version,
        "length": length,
        "json": json_obj,
        "raw_size": len(data),
    }


def find_persisted_glb(scene_id: str) -> Optional[Path]:
    """从 AICSS_MESH_PERSIST_DIR 或默认 tempdir/aicss_mesh_persist 找 GLB。

    export_scene 在成功后会把 GLB 复制到该目录（避免 tempfile cleanup）。
    """
    persist_root = Path(os.environ.get(
        "AICSS_MESH_PERSIST_DIR",
        str(Path(tempfile.gettempdir()) / "aicss_mesh_persist"),
    ))
    candidate = persist_root / f"{scene_id}.glb"
    if candidate.exists():
        return candidate
    return None


def build_strip_stack(image_url: str, width: int, height: int, client: httpx.Client) -> list[dict]:
    """对每个 region 跑 strip pipeline，返回完整 stripStack 列表。"""
    stack: list[dict] = []
    current = image_url
    for i, region in enumerate(STRIP_REGIONS):
        polygon = bbox_to_polygon(region["bbox"])
        log(f"strip {i}: {region['name']} bbox={region['bbox']}")
        billboard, inpaint = strip_once(
            client,
            current,
            polygon,
            region["bbox"],
            object_id=f"strip_{region['name']}",
            width=width,
            height=height,
        )
        stack.append({
            "regionId": f"strip_{i}_{region['name']}",
            "baseImageDataUrl": current,
            "inpaintResultUrl": inpaint,
            "billboardUrl": billboard,
            "layerPolygon": polygon,
            "depthLayer": region["depth_layer"],
            "depthValue": region["depth_value"],
            "colorIndex": i,
        })
        current = inpaint
    return stack


def main() -> int:
    if not TEST_IMAGE.exists():
        log(f"FAIL test image missing: {TEST_IMAGE}")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    image_url, w, h = load_image_as_data_url(TEST_IMAGE)
    log(f"loaded image {w}x{h}")

    result: dict = {}
    mesh_id: Optional[str] = None
    glb_path = OUT_DIR / "strip_stack_scene.glb"
    scene_id = f"strip_stack_{int(time.time())}"
    blender_available = False

    with httpx.Client(timeout=httpx.Timeout(300.0, connect=30.0)) as client:
        # 1) 健康检查
        try:
            r = client.get(f"{BACKEND}/api/aicss/models/status", timeout=10.0)
            r.raise_for_status()
            log("backend healthy")
        except Exception as e:
            log(f"FAIL backend not reachable: {e}")
            return 1

        # 2) Blender 可用性
        try:
            r = client.get(f"{BACKEND}/api/aicss/v2/meshes/check", timeout=10.0)
            info = r.json()
            blender_available = bool(info.get("available"))
            log(f"blender available={blender_available} path={info.get('path')}")
        except Exception as e:
            log(f"WARN blender check failed: {e}")

        # 3) 跑 strip pipeline（3 次 LaMa inpaint）
        log("running 3-step strip pipeline (LaMa inpaint) ...")
        try:
            strip_stack = build_strip_stack(image_url, w, h, client)
        except Exception as e:
            log(f"FAIL strip pipeline: {type(e).__name__}: {e}")
            return 1

        log(f"built stripStack with {len(strip_stack)} steps")
        for i, step in enumerate(strip_stack):
            log(f"  - step {i}: regionId={step['regionId']} "
                f"depthLayer={step['depthLayer']} depthValue={step['depthValue']}")

        # 4) 调用 /v2/meshes/export-scene（minimal analysis_result,纯 strip_stack 路径）
        minimal_analysis = {
            "sceneType": "outdoor",
            "objects": [],
            "summary": {"stripStackSize": len(strip_stack)},
        }
        payload = {
            "project_id": PROJECT_ID,
            "analysis_result": minimal_analysis,
            "depth_split_result": {},
            "layer_assets": {},
            "object_assets": {},
            "billboard_offsets": {},
            "regions": [],
            "strip_stack": strip_stack,
            "format": "glb",
            "include_textures": True,
        }
        log("POST /api/aicss/v2/meshes/export-scene ...")
        try:
            r = client.post(
                f"{BACKEND}/api/aicss/v2/meshes/export-scene",
                json=payload,
                timeout=600.0,
            )
        except Exception as e:
            log(f"FAIL export HTTP: {type(e).__name__}: {e}")
            return 1

        if r.status_code != 200:
            log(f"FAIL export status={r.status_code}: {r.text[:500]}")
            return 1

        result = r.json()
        mesh_id = result.get("mesh_id")
        log(f"export result: success={result.get('success')} mesh_id={mesh_id} "
            f"object_count={result.get('object_count')} file_size={result.get('file_size')}")

        if not result.get("success"):
            log(f"WARN export unsuccessful: {result.get('error')}")

        # 5) 找 GLB：优先走 /download；若 mesh_id 仍是 scene_id 未覆盖，则直接从
        #    AICSS_MESH_PERSIST_DIR 读（export_scene 复制过去的）。
        if mesh_id:
            try:
                r2 = client.get(
                    f"{BACKEND}/api/aicss/v2/meshes/{mesh_id}/download",
                    params={"project_id": PROJECT_ID},
                    timeout=120.0,
                )
                if r2.status_code == 200 and r2.content:
                    glb_path.write_bytes(r2.content)
                    log(f"downloaded GLB to {glb_path} ({glb_path.stat().st_size} bytes)")
                else:
                    raise RuntimeError(f"download status={r2.status_code}")
            except Exception as e:
                log(f"download via API failed ({e}); falling back to persist dir")
                # 用 scene.scene_id (e.g. scene_<project_name>) 找
                scene_id = f"scene_{PROJECT_ID}"
                persisted = find_persisted_glb(scene_id) or find_persisted_glb(result.get("scene_id", ""))
                if persisted and persisted.exists():
                    glb_path.write_bytes(persisted.read_bytes())
                    log(f"copied GLB from {persisted} to {glb_path} ({glb_path.stat().st_size} bytes)")
                else:
                    log(f"WARN GLB not found in persist dir for scene_id={scene_id}")

        # 6) 落盘 stripStack manifest（不含 base64 字段，避免文件过大）
        slim_stack = []
        for step in strip_stack:
            slim_stack.append({
                "regionId": step["regionId"],
                "depthLayer": step["depthLayer"],
                "depthValue": step["depthValue"],
                "colorIndex": step["colorIndex"],
                "layerPolygon": step["layerPolygon"],
                "billboardUrlBytes": len(base64.b64decode(step["billboardUrl"].split(",", 1)[1])),
                "inpaintResultUrlBytes": len(base64.b64decode(step["inpaintResultUrl"].split(",", 1)[1])),
            })
        manifest_path = OUT_DIR / f"{scene_id}_strip_stack_manifest.json"
        manifest_path.write_text(json.dumps({
            "scene_id": scene_id,
            "project_id": PROJECT_ID,
            "strip_stack_steps": len(strip_stack),
            "test_image": str(TEST_IMAGE),
            "image_size": [w, h],
            "export_result": {
                "success": result.get("success"),
                "mesh_id": mesh_id,
                "object_count": result.get("object_count"),
                "vertex_count": result.get("vertex_count"),
                "face_count": result.get("face_count"),
                "file_size": result.get("file_size"),
                "format": result.get("format"),
                "error": result.get("error"),
                "blender_available": result.get("blender_available"),
            },
            "steps": slim_stack,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"wrote manifest: {manifest_path}")

    # 7) 结构性格断言
    print("\n=== Structural assertions ===")

    if not result.get("success"):
        if not blender_available:
            log("WARN Blender not available and export failed; structural assertions skipped.")
            return 0
        log(f"FAIL export unsuccessful and Blender available: {result.get('error')}")
        return 1

    if not glb_path.exists() or glb_path.stat().st_size < 1024:
        size = glb_path.stat().st_size if glb_path.exists() else 0
        log(f"FAIL GLB missing or too small: {glb_path} (size={size})")
        return 1
    ok(glb_path.stat().st_size > 1024,
       f"GLB size > 1KB ({glb_path.stat().st_size} bytes)")

    try:
        glb = parse_glb_header(glb_path)
    except Exception as e:
        log(f"FAIL GLB parse error: {e}")
        return 1
    ok(glb["version"] == 2, f"GLB version == 2 (got {glb['version']})")
    ok(glb["length"] == glb["raw_size"],
       f"GLB header length matches file size ({glb['length']} == {glb['raw_size']})")

    j = glb["json"]
    expected_min_meshes = len(STRIP_REGIONS) + 1  # +1 for background plane

    ok(len(j.get("meshes", [])) >= expected_min_meshes,
       f"meshes count >= {expected_min_meshes} (got {len(j.get('meshes', []))})")
    ok(len(j.get("nodes", [])) >= expected_min_meshes,
       f"nodes count >= {expected_min_meshes} (got {len(j.get('nodes', []))})")
    ok(len(j.get("textures", [])) >= expected_min_meshes,
       f"textures count >= {expected_min_meshes} (got {len(j.get('textures', []))})")
    ok(len(j.get("images", [])) >= expected_min_meshes,
       f"images count >= {expected_min_meshes} (got {len(j.get('images', []))})")
    ok(len(j.get("materials", [])) >= expected_min_meshes,
       f"materials count >= {expected_min_meshes} (got {len(j.get('materials', []))})")

    scene_names = [m.get("name", "") for m in j.get("meshes", [])]
    has_bg = any("BackgroundPlane" in n for n in scene_names)
    ok(has_bg, f"BackgroundPlane mesh present (mesh names={scene_names})")

    for region in STRIP_REGIONS:
        rid = f"strip_{STRIP_REGIONS.index(region)}_{region['name']}"
        found = any(rid in n for n in scene_names)
        ok(found, f"RegionMesh for {rid} present")

    if _FAILS:
        print(f"\n[FAIL] {len(_FAILS)} structural assertion(s) failed:")
        for f in _FAILS:
            print(f"  - {f}")
        return 1
    print("\n[PASS] all structural assertions completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())