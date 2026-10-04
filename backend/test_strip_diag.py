"""诊断 strip pipeline 的中间图片，排查纹理问题。"""
import io
import base64
import httpx
import struct
import json
import time
import os
from pathlib import Path

BACKEND = "http://127.0.0.1:8000"
PROJECT_ID = "strip_diag"
OUT_DIR = Path("test_outputs/strip_diag")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_image_as_data_url(path: Path):
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("ascii")
    from PIL import Image
    img = Image.open(path)
    return f"data:image/png;base64,{data}", img.width, img.height


def save_data_url(url: str, name: str):
    """把 data URL 保存到文件。"""
    if not url.startswith("data:"):
        print(f"  [WARN] {name}: not a data URL")
        return
    header, b64 = url.split(",", 1)
    content = base64.b64decode(b64)
    out = OUT_DIR / name
    out.write_bytes(content)
    # 打印图片尺寸和基本统计
    from PIL import Image
    import numpy as np
    img = Image.open(io.BytesIO(content))
    arr = np.array(img)
    print(f"  saved {name}: mode={img.mode} size={img.size} min={arr.min()} max={arr.max()} mean={arr.mean():.1f}")
    return out


def bbox_to_polygon(bbox: dict) -> list[list[float]]:
    x, y, w, h = bbox["x"], bbox["y"], bbox["w"], bbox["h"]
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def make_polygon_mask(width: int, height: int, polygon_uv: list[list[float]]) -> str:
    from PIL import Image, ImageDraw
    mask = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(mask)
    pts = [(int(px * width), int(py * height)) for px, py in polygon_uv]
    draw.polygon(pts, fill=(255, 255, 255, 255))
    buf = io.BytesIO()
    mask.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def main():
    TEST_IMAGE = Path("F:/AICinematicSpatialSystem/test/背景.png")
    if not TEST_IMAGE.exists():
        print(f"FAIL: {TEST_IMAGE} not found")
        return 1

    image_url, w, h = load_image_as_data_url(TEST_IMAGE)
    print(f"image: {w}x{h}")

    # 保存原图
    save_data_url(image_url, "00_original.png")

    regions = [
        {"name": "foreground_person", "bbox": {"x": 0.165, "y": 0.225, "w": 0.190, "h": 0.700}},
        {"name": "midground_tree",   "bbox": {"x": 0.770, "y": 0.230, "w": 0.180, "h": 0.580}},
        {"name": "background_sky",   "bbox": {"x": 0.380, "y": 0.030, "w": 0.260, "h": 0.200}},
    ]

    current = image_url
    for i, reg in enumerate(regions):
        print(f"\n--- Step {i}: {reg['name']} ---")
        polygon = bbox_to_polygon(reg["bbox"])
        mask_uri = make_polygon_mask(w, h, polygon)

        # 保存 mask
        save_data_url(mask_uri, f"step{i}_{reg['name']}_mask.png")

        # billboard
        with httpx.Client(timeout=60.0) as client:
            bb_resp = client.post(
                f"{BACKEND}/api/aicss/billboard",
                json={
                    "imageUrl": current,
                    "objectId": f"diag_{reg['name']}",
                    "boundingBox": reg["bbox"],
                    "polygon": polygon,
                    "projectId": PROJECT_ID,
                },
                timeout=60.0,
            )
            bb_resp.raise_for_status()
            bb_json = bb_resp.json()
            billboard_url = bb_json.get("billboardUrl") or bb_json.get("rgbaUrl")
            if not billboard_url:
                print(f"  [ERROR] billboardUrl missing: {bb_json.keys()}")
                continue
            save_data_url(billboard_url, f"step{i}_{reg['name']}_billboard.png")

            # inpaint
            inp_resp = client.post(
                f"{BACKEND}/api/aicss/inpaint",
                json={
                    "imageUrl": current,
                    "maskDataUrl": mask_uri,
                    "prompt": "natural background",
                    "projectId": PROJECT_ID,
                },
                timeout=300.0,
            )
            inp_resp.raise_for_status()
            inp_json = inp_resp.json()
            inpaint_url = inp_json.get("inpaintResultUrl") or inp_json.get("imageUrl")
            if not inpaint_url:
                print(f"  [ERROR] inpaintResultUrl missing: {inp_json.keys()}")
                continue
            save_data_url(inpaint_url, f"step{i}_{reg['name']}_inpaint.png")

        current = inpaint_url

    print(f"\nDone. Check {OUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
