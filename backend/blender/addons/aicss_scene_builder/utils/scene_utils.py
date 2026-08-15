"""
Scene utilities — manifest parsing + Z-offset constants.

These are pure Python helpers (no ``bpy`` import) so they can be unit
tested outside Blender. The Z-offset values mirror
``backend/app/services/layer_exporter.LAYER_Z_OFFSETS`` so the Blender
plugin places planes at the exact same Z the Three.js viewer uses.
"""

# Canonical Z offsets (negative = closer to camera in Blender's
# right-handed coordinate system). Mirrors the backend's LAYER_Z_OFFSETS
# so a scene assembled in Three.js lines up pixel-for-pixel when re-
# rendered in Blender.
Z_OFFSETS = {
    "sky": -20.0,
    "background": -12.0,
    "midground": -6.0,
    "foreground": -2.0,
}

# Render order — sky is drawn first (deepest), foreground last (closest).
LAYER_ORDER = ("sky", "background", "midground", "foreground")

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
    if not any(k in layers for k in ("foreground", "midground", "background", "sky")):
        raise ValueError(
            "Manifest `layers` must include at least one of: "
            "foreground, midground, background, sky"
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
            return float(entry.get("zOffset", Z_OFFSETS[layer]))
    return Z_OFFSETS[layer]