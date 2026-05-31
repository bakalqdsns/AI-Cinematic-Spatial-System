"""
Spatial utilities — layer bucketing, scene graph building.
"""
import numpy as np
from typing import Optional
from ..config import settings


def assign_to_depth_layer(depth_meters: float) -> tuple[str, float, float]:
    """
    Assign a depth value to the appropriate spatial layer.

    Returns (layer_name, z_min, z_max).
    """
    for z_min, z_max, name in settings.depth_buckets:
        if z_min <= depth_meters < z_max:
            return name, z_min, z_max
    # Fallback to sky
    return "sky", 50.0, float("inf")


def build_spatial_layers_from_objects(
    objects: list[dict],
    depth_map: Optional[np.ndarray] = None,
    image_width: int = 1024,
    image_height: int = 768,
) -> list[dict]:
    """
    Bucket objects into spatial layers based on their depth values.

    Returns a list of layer dicts matching the frontend SpatialLayer interface.
    """
    # Group objects by layer name
    layer_map: dict[str, list] = {}
    for obj in objects:
        layer_name = obj.get("layer", "foreground")
        if layer_name not in layer_map:
            layer_map[layer_name] = []
        layer_map[layer_name].append(obj)

    layers = []
    for z_min, z_max, layer_name in settings.depth_buckets:
        layer_obj = {
            "id": f"layer_{layer_name}_{int(z_min)}",
            "name": layer_name,
            "zMin": float(z_min),
            "zMax": float(z_max) if z_max != float("inf") else 9999.0,
            "objects": layer_map.get(layer_name, []),
        }
        layers.append(layer_obj)

    return layers


def build_scene_graph_from_objects(
    shot_id: str,
    objects: list[dict],
) -> dict:
    """
    Build a spatial relationship graph from segmented objects.

    Relations are derived from bounding box overlap and depth ordering:
      - leftOf / rightOf: horizontal overlap
      - inFrontOf / behind: depth ordering
      - above / below: vertical overlap
    """
    nodes = []
    for i, obj_a in enumerate(objects):
        bbox_a = obj_a.get("boundingBox", {})
        depth_a = obj_a.get("depth", 10.0)
        x_a = bbox_a.get("x", 0) + bbox_a.get("w", 0) / 2
        y_a = bbox_a.get("y", 0) + bbox_a.get("h", 0) / 2

        relations = []
        for j, obj_b in enumerate(objects):
            if i == j:
                continue
            bbox_b = obj_b.get("boundingBox", {})
            depth_b = obj_b.get("depth", 10.0)
            x_b = bbox_b.get("x", 0) + bbox_b.get("w", 0) / 2
            y_b = bbox_b.get("y", 0) + bbox_b.get("h", 0) / 2

            # Horizontal: is A to the left of B?
            if x_a + bbox_a.get("w", 0) * 0.3 < x_b:
                relations.append({"type": "leftOf", "targetId": obj_b.get("id", f"obj_{j}")})
            # Horizontal: is A to the right of B?
            elif x_a > x_b + bbox_b.get("w", 0) * 0.7:
                relations.append({"type": "rightOf", "targetId": obj_b.get("id", f"obj_{j}")})
            # Depth: is A in front of B?
            if abs(x_a - x_b) < 0.3:  # roughly aligned
                if depth_a < depth_b - 1.0:
                    relations.append({"type": "inFrontOf", "targetId": obj_b.get("id", f"obj_{j}")})
                elif depth_b < depth_a - 1.0:
                    relations.append({"type": "behind", "targetId": obj_b.get("id", f"obj_{j}")})
            # Vertical: is A above B?
            if y_a + bbox_a.get("h", 0) * 0.3 < y_b:
                relations.append({"type": "above", "targetId": obj_b.get("id", f"obj_{j}")})
            elif y_a > y_b + bbox_b.get("h", 0) * 0.7:
                relations.append({"type": "below", "targetId": obj_b.get("id", f"obj_{j}")})

        nodes.append({
            "id": obj_a.get("id", f"obj_{i}"),
            "classLabel": obj_a.get("classLabel", "unknown"),
            "depth": float(obj_a.get("depth", 10.0)),
            "layer": obj_a.get("layer", "foreground"),
            "relations": relations,
        })

    return {
        "shotId": shot_id,
        "nodes": nodes,
    }
