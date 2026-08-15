# AICSS Scene Builder — Blender Addon (Phase 1.2)

Blender 4.0+ addon that imports layer PNGs exported by the AICSS backend
and assembles them into a paper-diorama 3D scene.

## What it does

The AICSS backend's `POST /api/aicss/layers/export` endpoint emits 4 RGBA
PNG data URIs (one per depth layer: foreground / midground / background /
sky) plus a Z-axis offset table. This addon consumes that output and:

1. **Imports the layers** as 4 mesh planes positioned along the camera
   Z-axis at the canonical offsets (-2, -6, -12, -20 world units).
2. **Applies a paper material** to each plane — diffuse texture with
   cartoonisation color ramp, normal map for paper grain, roughness 0.9.
3. **Sets up a camera** with shot-type-aware FOV (wide / medium / closeup).
4. **Adds a 3-point lighting rig** (key + fill + rim) from a built-in
   preset or a custom JSON file.

## Manifest format

The plugin expects a JSON manifest describing the scene. The backend
emits this alongside the layer PNGs. Minimal schema:

```json
{
  "shotId": "shot_001",
  "sceneId": "scene_forest",
  "width": 1920,
  "height": 1080,
  "layers": {
    "foreground":  "/abs/path/to/layer_foreground.png",
    "midground":   "/abs/path/to/layer_midground.png",
    "background":  "/abs/path/to/layer_background.png",
    "sky":         "/abs/path/to/layer_sky.png"
  },
  "zOffsets": [
    {"layer": "sky",        "zOffset": -20.0},
    {"layer": "background", "zOffset": -12.0},
    {"layer": "midground",  "zOffset": -6.0},
    {"layer": "foreground", "zOffset": -2.0}
  ],
  "camera": {
    "shotType": "wide",
    "fov": 35.0,
    "distance": 12.0,
    "target": [0.0, 0.0, 0.0]
  },
  "lighting": {
    "key":  {"type": "SUN",  "energy": 3.0, "color": [1.0, 0.96, 0.88]},
    "fill": {"type": "AREA", "energy": 1.5, "color": [0.8, 0.9, 1.0]},
    "rim":  {"type": "SPOT", "energy": 2.0, "color": [1.0, 0.93, 0.8]}
  }
}
```

## Install

1. **From a zip** — zip this folder (`aicss_scene_builder/`) and use
   Blender's *Edit → Preferences → Add-ons → Install…* to install the zip.
2. **From disk** — copy this folder to
   `<blender>/scripts/addons/aicss_scene_builder/` and enable it from the
   addons list.

## Use

1. In Blender, open the 3D viewport and press `N` to open the sidebar.
2. Click the **AICSS** tab.
3. Click **Import Scene** and pick your manifest JSON.
4. The 4 layer planes appear, each with the paper material applied.
5. Click **Set Camera** to create the shot camera.
6. Click **Add Lighting** to add the 3-point rig (pick a preset or
   "Custom JSON…").

## Module layout

```
aicss_scene_builder/
    __init__.py             # bl_info + register/unregister
    operators/
        import_layers.py    # POST /layers/export → mesh planes
        setup_camera.py     # shot_type → camera + target empty
        add_lighting.py     # preset → 3-point lighting rig
        apply_material.py   # AICSS paper material on selection
    materials/
        paper_material.py   # v1 node graph (diffuse + normal + cartoonisation)
    ui/
        aicss_panel.py      # N-panel sidebar
    utils/
        scene_utils.py      # Z_OFFSETS, LAYER_ORDER, manifest parser
    presets/
        lighting/
            warm_interior.json
            cool_exterior.json
            dramatic.json
```

## Tests

The non-Blender modules (`utils.scene_utils`, manifest parsing) are
unit-testable outside Blender. Run:

```bash
cd backend/blender/addons
python -c "import sys; sys.path.insert(0, '.'); from aicss_scene_builder.utils.scene_utils import normalize_manifest; print('OK')"
```

## Phase 2 roadmap

* `PaperMaterialParams.use_fibre = True` → procedural paper-fibre normal
* `subsurface = 0.15` → SSS for the side-lit paper translucency
* Per-layer `thicknessMm` from manifest → Box geometry instead of Plane

See `docs/IMPLEMENTATION_PLAN.md` §2.1 for the full Phase 2 material spec.
