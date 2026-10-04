"""
Camera-path generator — backend helper that converts a Shot's
camera_movement + duration + shot_size into Three.js-ready keyframes.

Phase 1.3 deliverable (Implementation Plan §1.3.4). The frontend's
`utils/cameraAnimation.ts` is the source of truth — we keep this
server-side mirror so:

  1. The Blender Phase 3 renderer can re-use the same keyframes.
  2. Future automated test harnesses can validate camera paths without
     spinning up a browser.
  3. The architecture stays consistent — both renderers consume the
     same abstract camera path, so a hand-edited manifest can target
     either renderer.

The actual interpolation lives on the frontend; this module only emits
the static keyframe table.

T06 扩展：``write_camera_path_to_archive`` 把关键帧序列写入 shot archive
ZIP 的 manifest.cameraPath 字段，供 Blender 插件
``aicss.setup_camera_animation`` operator 读取。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.services.shot_generator import CameraMovement, ShotSize


@dataclass
class CameraKeyframe:
    """One keyframe in a camera path (Phase 1.3)."""
    time: float               # 0..1
    position: tuple[float, float, float]
    target: tuple[float, float, float]
    fov: float                # degrees


# Distance from origin per shot size — matches the frontend's BASE_DISTANCE.
BASE_DISTANCE: dict[str, float] = {
    "Extreme Close-up": 1.5,
    "Close-up": 3.0,
    "Medium Close-up": 5.0,
    "Medium Shot": 8.0,
    "Medium Wide": 12.0,
    "Wide Shot": 16.0,
    "Extreme Wide": 22.0,
    "Over-the-Shoulder": 5.0,
    "POV": 5.0,
    "Two-Shot": 8.0,
}

# Base FOV per shot size — matches the frontend's BASE_FOV.
BASE_FOV: dict[str, float] = {
    "Extreme Close-up": 85.0,
    "Close-up": 65.0,
    "Medium Close-up": 55.0,
    "Medium Shot": 45.0,
    "Medium Wide": 38.0,
    "Wide Shot": 32.0,
    "Extreme Wide": 28.0,
    "Over-the-Shoulder": 55.0,
    "POV": 60.0,
    "Two-Shot": 45.0,
}


def build_camera_path(
    movement: CameraMovement | str,
    shot_size: ShotSize | str,
    duration: float,
) -> list[dict]:
    """Return 1 or 2 keyframes (start + end) for the given shot.

    Output is a list of plain dicts (not dataclasses) so FastAPI can
    serialise them via Pydantic with no extra model.
    """
    movement_str = movement.value if hasattr(movement, "value") else str(movement)
    shot_size_str = shot_size.value if hasattr(shot_size, "value") else str(shot_size)
    duration = max(0.1, float(duration))

    base_dist = BASE_DISTANCE.get(shot_size_str, 8.0)
    base_fov = BASE_FOV.get(shot_size_str, 45.0)

    start = {
        "time": 0.0,
        "position": [0.0, 0.0, base_dist],
        "target": [0.0, 0.0, 0.0],
        "fov": base_fov,
    }
    end = {
        "time": 1.0,
        "position": [0.0, 0.0, base_dist],
        "target": [0.0, 0.0, 0.0],
        "fov": base_fov,
    }

    if movement_str == "Static":
        return [start]

    if movement_str == "Pan Right":
        end["position"] = [-base_dist * 0.3, 0.0, base_dist]
        end["target"] = [base_dist * 0.3, 0.0, 0.0]
    elif movement_str == "Pan Left":
        end["position"] = [base_dist * 0.3, 0.0, base_dist]
        end["target"] = [-base_dist * 0.3, 0.0, 0.0]
    elif movement_str == "Tilt Up":
        end["position"] = [0.0, -base_dist * 0.2, base_dist]
        end["target"] = [0.0, base_dist * 0.3, 0.0]
    elif movement_str == "Tilt Down":
        end["position"] = [0.0, base_dist * 0.2, base_dist]
        end["target"] = [0.0, -base_dist * 0.3, 0.0]
    elif movement_str == "Dolly In":
        end["position"] = [0.0, 0.0, base_dist * 0.5]
        end["fov"] = min(base_fov + 5, 90)
    elif movement_str == "Dolly Out":
        end["position"] = [0.0, 0.0, base_dist * 1.5]
        end["fov"] = max(base_fov - 5, 25)
    elif movement_str == "Zoom In":
        end["fov"] = min(base_fov * 1.5, 90)
    elif movement_str == "Zoom Out":
        end["fov"] = max(base_fov * 0.65, 20)
    elif movement_str == "Tracking":
        end["position"] = [base_dist * 0.6, 0.0, base_dist * 0.9]
    elif movement_str == "Crane Up":
        end["position"] = [0.0, base_dist * 0.5, base_dist * 0.85]
    elif movement_str == "Crane Down":
        end["position"] = [0.0, -base_dist * 0.3, base_dist * 1.1]
    elif movement_str == "Handheld":
        end["position"] = [
            base_dist * 0.08,
            base_dist * 0.05,
            base_dist * 1.05,
        ]
        end["fov"] = base_fov + 2
    # else: unknown movement — fall back to static (just [start]).

    return [start, end]


def write_camera_path_to_archive(
    archive_path: Path | str,
    movement: CameraMovement | str,
    shot_size: ShotSize | str,
    duration: float,
) -> list[dict]:
    """生成相机路径并写入 shot archive ZIP 的 manifest.cameraPath 字段（T06）。

    Args:
        archive_path: shot archive ZIP 路径（由 ``shot_archiver.build_shot_archive`` 产出）。
        movement / shot_size / duration: 见 ``build_camera_path``。

    Returns:
        写入的 cameraPath 关键帧列表。

    Raises:
        FileNotFoundError: archive 不存在。
        ValueError: archive 内无 manifest.json。
    """
    from app.services.shot_archiver import update_archive_manifest_field

    camera_path = build_camera_path(movement, shot_size, duration)
    update_archive_manifest_field(
        archive_path, "cameraPath", camera_path,
    )
    return camera_path
