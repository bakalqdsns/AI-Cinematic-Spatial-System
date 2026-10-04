"""Inspect mesh export response to find correct download URL."""
import sys, json, base64, urllib.request, urllib.parse

with open(r"F:\AICinematicSpatialSystem\test\背景.png", "rb") as f:
    img_b64 = base64.b64encode(f.read()).decode("utf-8")
img_uri = f"data:image/png;base64,{img_b64}"

def post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
        headers={"Content-Type":"application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())

# 1. Export layers
layers_resp = post("http://127.0.0.1:8000/api/aicss/layers/export",
    {"imageUrl": img_uri, "numLayers": 4})
layers = layers_resp["layers"]

# 2. For each layer, generate paper
layer_assets = {}
for key in ["sky", "background", "midground", "foreground"]:
    paper = post("http://127.0.0.1:8000/api/aicss/paper-layer",
        {"layerImageUrl": layers[key]["dataUri"],
         "thicknessMin": 1.0, "thicknessMax": 5.0,
         "outlineWidth": 3, "colorLevels": 12, "styleStrength": 0.7})
    layer_assets[key] = {
        "rgbaUrl": layers[key]["dataUri"],
        "paperStyleUrl": paper.get("paperStyleUrl"),
        "normalMapUrl": paper.get("normalMapUrl"),
        "thicknessGrayUrl": paper.get("thicknessGrayUrl"),
        "outlinedUrl": paper.get("outlinedUrl"),
        "depthValue": {"sky":32,"background":96,"midground":160,"foreground":224}[key],
    }

# 3. Export mesh WITHOUT project_id
print("=== Without project_id ===")
resp_no = post("http://127.0.0.1:8000/api/aicss/v2/meshes/export-layers", {
    "layer_assets": layer_assets, "format": "glb", "include_textures": True,
})
print(json.dumps(resp_no, indent=2)[:800])

# 4. Export mesh WITH project_id
print("\n=== With project_id ===")
resp = post("http://127.0.0.1:8000/api/aicss/v2/meshes/export-layers", {
    "project_id": "mesh_e2e_project",
    "layer_assets": layer_assets, "format": "glb", "include_textures": True,
})
print(json.dumps(resp, indent=2)[:1500])

# Try download
mesh_id = resp.get("mesh_id")
if mesh_id:
    print(f"\n=== Download mesh_id={mesh_id} ===")
    qs = urllib.parse.urlencode({"project_id": "mesh_e2e_project"})
    for path in [f"/api/aicss/v2/meshes/{mesh_id}/download?{qs}",
                 f"/api/aicss/v2/meshes/download/{mesh_id}?{qs}",
                 f"/api/aicss/v2/meshes/{mesh_id}?{qs}"]:
        url = f"http://127.0.0.1:8000{path}"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read()
                print(f"  OK {path} -> {len(body)/1024:.1f} KB")
                with open(rf"f:\AICinematicSpatialSystem\backend\test_outputs\mesh_e2e\parkway_{mesh_id}.glb", "wb") as f:
                    f.write(body)
                break
        except urllib.error.HTTPError as e:
            print(f"  {e.code} {path}")
        except Exception as e:
            print(f"  ERR {path}: {e}")