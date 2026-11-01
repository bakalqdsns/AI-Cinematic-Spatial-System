"""
Scene utilities — manifest parsing + Z-offset constants.

These are pure Python helpers (no ``bpy`` import) so they can be unit
tested outside Blender. The Z-offset values mirror
``backend/app/services/layer_exporter.LAYER_Z_OFFSETS`` so the Blender
plugin places planes at the exact same Z the Three.js viewer uses.
"""

# 默认层距。相机在 +Z、朝 -Z 看，Z 越负越远。
# 有 Depth Anything 结果时，manifest.zOffsets 用每层深度的负值，并带 scale：
# 最近一层 scale=1，越远越大，用来抵消透视缩小。
Z_OFFSETS = {
    "sky": -20.0,
    "background": -12.0,
    "midground": -8.0,
    "ground": -4.0,
    "foreground": -2.0,
}

# 从远到近。地面在中景和前景之间，不盖住人物。
# 与 layer_exporter.LAYER_ORDER 一致。
LAYER_ORDER = ("sky", "background", "midground", "ground", "foreground")

# ── 纸雕呈现默认值 ──────────────────────────────────────────────────────────
# 与 backend/app/services/layer_exporter.py 的同名表一致。
# 只影响层片在 Blender 里的外观（厚度、切边、轻微旋转、错位），
# 不改深度归层语义。清单 zOffsets 行里带了同名字段时以清单为准。
LAYER_THICKNESS_M = {
    "sky": 0.12,
    "background": 0.10,
    "midground": 0.08,
    "ground": 0.08,
    "foreground": 0.06,
}

LAYER_YAW_DEG = {
    "sky": 2.5,
    "background": 2.0,
    "midground": 2.5,
    "ground": 2.0,
    "foreground": 2.5,
}

LAYER_PITCH_DEG = {
    "sky": 1.5,
    "background": 1.0,
    "midground": 1.5,
    "ground": 1.0,
    "foreground": 1.5,
}

LAYER_SHIFT_X_M = {
    "sky": 0.45,
    "background": -0.35,
    "midground": 0.15,
    "ground": -0.20,
    "foreground": 0.30,
}

LAYER_SHIFT_Y_M = {
    "sky": 0.25,
    "background": -0.10,
    "midground": 0.20,
    "ground": -0.15,
    "foreground": 0.0,
}

# Default scene size in Blender units (1 BU = 1 m in our paper-diorama world)
DEFAULT_SCENE_WIDTH = 20.0
DEFAULT_SCENE_HEIGHT = 15.0

# Default camera FOV (degrees) per shot type — mirrors the Three.js viewer
# so a wide shot looks the same in both renderers.
DEFAULT_CAMERA_FOV = {
    "wide": 35.0,
    "medium": 50.0,
    "closeup": 70.0,
    "extreme_closeup": 85.0,
}


def read_manifest(path):
    """Read and validate a manifest JSON file.

    Raises:
        FileNotFoundError: when ``path`` does not exist.
        ValueError: when the JSON is malformed or missing required keys.
    """
    import json
    import os

    if not os.path.exists(path):
        raise FileNotFoundError(f"Manifest not found: {path}")

    with open(path, "r", encoding="utf-8") as fp:
        data = json.load(fp)

    return normalize_manifest(data)


def normalize_manifest(data):
    """Validate a manifest dict and fill in sensible defaults.

    Returns a new dict (does not mutate the input). Raises ValueError if
    required keys are missing.
    """
    if not isinstance(data, dict):
        raise ValueError("Manifest must be a JSON object")

    # Layers are required. zOffsets default to the canonical table.
    layers = data.get("layers")
    if not layers or not isinstance(layers, dict):
        raise ValueError(
            "Manifest must contain a `layers` object with foreground/midground/"
            "background/sky PNG paths"
        )

    # We don't require every layer to be present (e.g. sky may be omitted
    # for night scenes), but we do require at least one.
    if not any(k in layers for k in ("foreground", "midground", "background", "sky", "ground")):
        raise ValueError(
            "Manifest `layers` must include at least one of: "
            "foreground, midground, background, sky, ground"
        )

    z_offsets = data.get("zOffsets")
    if z_offsets is None:
        # Default to canonical table
        z_offsets = [
            {"layer": layer, "zOffset": Z_OFFSETS[layer],
             "zMin": 0.0, "zMax": 9999.0}
            for layer in LAYER_ORDER
        ]
        data["zOffsets"] = z_offsets

    # Camera defaults
    camera = data.get("camera") or {}
    shot_type = camera.get("shotType", "wide")
    fov = camera.get("fov", DEFAULT_CAMERA_FOV.get(shot_type, DEFAULT_CAMERA_FOV["wide"]))
    distance = camera.get("distance", 12.0)
    target = camera.get("target", [0.0, 0.0, 0.0])

    data["camera"] = {
        "shotType": shot_type,
        "fov": float(fov),
        "distance": float(distance),
        "target": list(target),
    }

    # Width / height defaults
    if "width" not in data:
        data["width"] = int(DEFAULT_SCENE_WIDTH * 100)  # 2000 px default
    if "height" not in data:
        data["height"] = int(DEFAULT_SCENE_HEIGHT * 100)
    if "shotId" not in data:
        data["shotId"] = "unknown_shot"

    return data


def layer_z_offset(manifest, layer):
    """Look up the Z offset for a single layer in the manifest.

    Falls back to the canonical table when the manifest doesn't list
    the layer (e.g. sky is absent for night scenes).
    """
    for entry in manifest.get("zOffsets", []):
        if entry.get("layer") == layer:
            return float(entry.get("zOffset", Z_OFFSETS.get(layer, -8.0)))
    return float(Z_OFFSETS.get(layer, -8.0))


def layer_plane_scale(manifest, layer):
    """面片相对最近一层的放大倍数。清单里没有 scale 时用 1。"""
    for entry in manifest.get("zOffsets", []):
        if entry.get("layer") == layer:
            try:
                scale = float(entry.get("scale", 1.0))
            except (TypeError, ValueError):
                return 1.0
            if scale <= 0.0:
                return 1.0
            return scale
    return 1.0


def _layer_entry(manifest, layer):
    """清单 zOffsets 里该层的那一行，没有返回 None。"""
    for entry in manifest.get("zOffsets", []) or []:
        if entry.get("layer") == layer:
            return entry
    return None


def _entry_float(entry, key, default, *, minimum=None, maximum=None):
    """读清单里的浮点字段。缺失、非数、越界都回退到默认值。"""
    if entry is None:
        return default
    try:
        value = float(entry.get(key, default))
    except (TypeError, ValueError):
        return default
    if value != value:  # NaN
        return default
    if minimum is not None and value < minimum:
        return default
    if maximum is not None and value > maximum:
        return default
    return value


def layer_thickness(manifest, layer):
    """卡片厚度（米）。清单行里没有 thicknessM 时用默认表。"""
    default = LAYER_THICKNESS_M.get(layer, 0.08)
    return _entry_float(
        _layer_entry(manifest, layer), "thicknessM", default,
        minimum=0.005, maximum=0.5,
    )


def layer_yaw_deg(manifest, layer):
    """绕竖直轴的轻微偏航（度）。限制在 ±6°，避免相邻层穿插。"""
    default = LAYER_YAW_DEG.get(layer, 2.0)
    return _entry_float(
        _layer_entry(manifest, layer), "yawDeg", default,
        minimum=-6.0, maximum=6.0,
    )


def layer_pitch_deg(manifest, layer):
    """绕横轴的轻微俯仰（度）。限制在 ±6°。"""
    default = LAYER_PITCH_DEG.get(layer, 1.0)
    return _entry_float(
        _layer_entry(manifest, layer), "pitchDeg", default,
        minimum=-6.0, maximum=6.0,
    )


def layer_shift(manifest, layer):
    """水平/垂直错位（米），返回 (dx, dy)。限制在 ±3m，免得把层片推出取景框。"""
    entry = _layer_entry(manifest, layer)
    dx = _entry_float(
        entry, "shiftXM", LAYER_SHIFT_X_M.get(layer, 0.0),
        minimum=-3.0, maximum=3.0,
    )
    dy = _entry_float(
        entry, "shiftYM", LAYER_SHIFT_Y_M.get(layer, 0.0),
        minimum=-3.0, maximum=3.0,
    )
    return dx, dy