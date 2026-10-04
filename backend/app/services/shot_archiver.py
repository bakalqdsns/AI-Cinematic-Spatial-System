"""
Shot-level archive packer — 将项目资产打成 Blender 可导入的 ZIP。

产出结构（相对 ZIP 根目录）：
  manifest.json          # Blender addon 可读（相对路径）
  scene/                 # wide / closeup / mood 等场景关键帧
  character/             # 角色三视图 / 动作帧
  layers/                # 深度层 PNG（若存在）
  mesh/                  # GLB/FBX（若存在）
  camera/                # camera_keyframes.json（若存在）
  scripts/               # blender_import.py + lighting.json
  shots/<shot_id>/       # 该镜头目录原样拷贝（frames/artifacts）

manifest 字段（v2 扩展，向后兼容）：
  - characters:   list[{id, name, framesDir, frameCount, fps}]  (T11)
      framesDir 用绝对路径，方便 Blender 跨平台读
  - cameraPath:   list[{time, position, target, fov}]          (T06)
      关键帧序列，由 camera_path_generator 写入
  - lighting:     {key, fill, rim}                              (T14)
      从 presets/lighting/<preset>.json 格式读取
  - lightingPreset: str                                         (T13 兼容)
      预设名（如 "warm_interior"），前端可据此切换
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_log = logging.getLogger("aicss")

# Blender addon 约定的层顺序与默认 Z
_DEFAULT_Z_OFFSETS = [
    {"layer": "sky", "zOffset": -20.0},
    {"layer": "background", "zOffset": -12.0},
    {"layer": "midground", "zOffset": -6.0},
    {"layer": "foreground", "zOffset": -2.0},
    {"layer": "ground", "zOffset": -1.5},
]

_LAYER_NAMES = ("sky", "background", "midground", "foreground", "ground")

_BLENDER_IMPORT_SCRIPT = '''\
"""
AICSS shot archive — open in Blender Text Editor and Run Script,
or call from the AICSS addon after unzipping this archive.

Usage (Blender Python console):
  import bpy
  bpy.ops.aicss.import_layers(manifest_path="//manifest.json")
"""
import bpy
from pathlib import Path

# Resolve manifest next to this script's parent (archive root)
_here = Path(__file__).resolve().parent.parent
_manifest = _here / "manifest.json"
if not _manifest.is_file():
    raise FileNotFoundError(f"manifest.json not found at {_manifest}")

bpy.ops.aicss.import_layers(manifest_path=str(_manifest))
print(f"[AICSS] Imported scene from {_manifest}")
'''

_DEFAULT_LIGHTING = {
    "key": {"type": "SUN", "energy": 3.0, "color": [1.0, 0.96, 0.88]},
    "fill": {"type": "AREA", "energy": 1.5, "color": [0.8, 0.9, 1.0]},
    "rim": {"type": "SPOT", "energy": 2.0, "color": [1.0, 0.93, 0.8]},
}


def _copy_tree(src: Path, dst: Path) -> int:
    """Copy files under src into dst; return file count."""
    if not src.is_dir():
        return 0
    count = 0
    for p in src.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
        count += 1
    return count


def _collect_layers(staging: Path, project_dir: Path) -> dict[str, str]:
    """
    Find layer PNGs in common locations and copy into staging/layers/.
    Returns relative path map for manifest.layers.

    Fallback: when no canonical layer-name PNGs are found, map the scene
    keyframes (wide/closeup/mood) to background/midground/foreground so
    the paper-diorama render queue has at least one layer to import.
    """
    layers_out = staging / "layers"
    layers_out.mkdir(parents=True, exist_ok=True)
    found: dict[str, str] = {}

    search_roots = [
        project_dir / "layers",
        project_dir / "artifacts" / "layers",
        project_dir / "shots",
    ]
    # Also scan scene dirs for *layer*.png / depth layer names
    scenes = project_dir / "scenes"
    if scenes.is_dir():
        search_roots.append(scenes)

    candidates: list[Path] = []
    for root in search_roots:
        if not root.is_dir():
            continue
        for name in _LAYER_NAMES:
            candidates.extend(root.rglob(f"*{name}*.png"))
            candidates.extend(root.rglob(f"*{name}*.PNG"))

    def _stem_is_layer(stem: str, name: str) -> bool:
        # 精确匹配。子串会把 background.png 当成 ground（"ground" in "background"）。
        s = stem.lower()
        return s == name or s.endswith(f"_{name}") or s.endswith(f"-{name}")

    for name in _LAYER_NAMES:
        match = None
        for c in candidates:
            if _stem_is_layer(c.stem, name) and name not in found:
                match = c
                break
        if match is None:
            continue
        dest_name = f"{name}.png"
        shutil.copy2(match, layers_out / dest_name)
        found[name] = f"layers/{dest_name}"

    # ── Fallback: scene keyframe → depth-layer mapping ──────────────────────
    # scenes/<scene>/ generates wide.png / closeup.png / mood.png which don't
    # match the canonical layer names. Map them so the render queue has at
    # least one importable layer.
    # 注意：只有找到**不同**的图时才映射对应层，避免同一张图被映射到多个层
    # 导致不透明全屏 plane 互相遮挡。
    if not found and scenes.is_dir():
        _SCENE_LAYER_MAP = {
            "background": ("wide", "mood", "closeup"),
            "midground": ("mood", "closeup"),
            "foreground": ("closeup", "mood"),
        }
        used_files: set[str] = set()
        for layer_name, scene_keys in _SCENE_LAYER_MAP.items():
            match = None
            for sk in scene_keys:
                hits = sorted(scenes.rglob(f"{sk}.png"))
                if hits:
                    hit_name = hits[0].name
                    if hit_name not in used_files:
                        match = hits[0]
                        used_files.add(hit_name)
                        break
            if match is None:
                continue
            dest_name = f"{layer_name}.png"
            shutil.copy2(match, layers_out / dest_name)
            found[layer_name] = f"layers/{dest_name}"

    return found


def _collect_meshes(staging: Path, project_dir: Path) -> list[str]:
    mesh_out = staging / "mesh"
    mesh_out.mkdir(parents=True, exist_ok=True)
    packed: list[str] = []
    meshes_dir = project_dir / "meshes"
    if not meshes_dir.is_dir():
        return packed
    for p in meshes_dir.rglob("*"):
        if p.suffix.lower() not in (".glb", ".fbx", ".gltf"):
            continue
        rel = p.relative_to(meshes_dir)
        dest = mesh_out / rel.name
        # avoid overwrite collisions
        if dest.exists():
            dest = mesh_out / f"{p.parent.name}_{p.name}"
        shutil.copy2(p, dest)
        packed.append(f"mesh/{dest.name}")
    return packed


def _collect_characters(project_dir: Path) -> list[dict]:
    """扫描 motions/ 目录，构建 manifest.characters 字段（T11）。

    motion_extractor 输出布局：``motions/<character_name>/<action_slug>/frame_*.png``
    以及 ``motions/<character_name>/<action_slug>/segmented/seg_*.png``。

    每个角色生成一条记录：
      {id, name, framesDir, frameCount, fps}

    - framesDir 用绝对路径（os.path.abspath），方便 Blender 跨平台读。
    - frameCount = 该 action 目录下 frame_*.png 数量。
    - fps 默认 24（Blender 标准帧率）；若 action 目录下有 _meta.json 含 fps 字段则用之。
    - 一个角色若有多个 action，取帧数最多的那条作为该角色的代表序列。
    """
    motions_root = project_dir / "motions"
    if not motions_root.is_dir():
        return []

    characters: list[dict] = []
    for char_dir in sorted(p for p in motions_root.iterdir() if p.is_dir()):
        char_name = char_dir.name
        # 跳过 _misc 杂项目录
        if char_name.startswith("_"):
            continue

        best_action: Optional[dict] = None
        best_count = 0
        for action_dir in sorted(p for p in char_dir.iterdir() if p.is_dir()):
            frames = sorted(action_dir.glob("frame_*.png"))
            if not frames:
                # 也尝试 segmented/ 子目录
                seg_dir = action_dir / "segmented"
                if seg_dir.is_dir():
                    frames = sorted(seg_dir.glob("seg_*.png"))
            if not frames:
                continue
            count = len(frames)
            if count > best_count:
                best_count = count
                best_action = {
                    "action": action_dir.name,
                    "frames_dir": action_dir,
                    "frame_count": count,
                }

        if best_action is None:
            continue

        # fps：尝试读 _meta.json，否则默认 24
        fps = 24
        meta_path = best_action["frames_dir"] / "_meta.json"
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if isinstance(meta.get("fps"), (int, float)):
                    fps = int(meta["fps"])
            except Exception:
                pass

        characters.append({
            "id": char_name,
            "name": char_name.replace("_", " "),
            "framesDir": os.path.abspath(str(best_action["frames_dir"])),
            "frameCount": int(best_action["frame_count"]),
            "fps": int(fps),
        })

    return characters


def _load_lighting_preset(preset_name: str, addon_dir: Optional[Path] = None) -> Optional[dict]:
    """从插件 presets/lighting/<name>.json 读预设（T14）。

    找不到时返回 None，调用方回退到 _DEFAULT_LIGHTING。
    """
    if not preset_name:
        return None
    search_roots: list[Path] = []
    if addon_dir is not None:
        search_roots.append(addon_dir / "presets" / "lighting")
    # 后端相对路径：backend/blender/addons/aicss_scene_builder/presets/lighting
    backend_root = Path(__file__).resolve().parents[2]
    search_roots.append(backend_root / "blender" / "addons" / "aicss_scene_builder" / "presets" / "lighting")
    for root in search_roots:
        candidate = root / f"{preset_name}.json"
        if candidate.is_file():
            try:
                with open(candidate, "r", encoding="utf-8") as fp:
                    return json.load(fp)
            except Exception:
                _log.warning("[archive] failed to read lighting preset %s", candidate)
                return None
    return None


def _collect_camera(staging: Path, project_dir: Path, shot_id: str) -> Optional[str]:
    camera_out = staging / "camera"
    camera_out.mkdir(parents=True, exist_ok=True)
    candidates = [
        project_dir / "shots" / shot_id / "camera_keyframes.json",
        project_dir / "shots" / shot_id / "artifacts" / "camera_keyframes.json",
        project_dir / "camera" / "camera_keyframes.json",
        project_dir / "camera_keyframes.json",
    ]
    for c in candidates:
        if c.is_file():
            dest = camera_out / "camera_keyframes.json"
            shutil.copy2(c, dest)
            return "camera/camera_keyframes.json"
    # Write a minimal placeholder so the folder is useful
    placeholder = {
        "shotId": shot_id,
        "keyframes": [],
        "note": "No camera keyframes found in project; fill via /v2/scripts/camera-path",
    }
    (camera_out / "camera_keyframes.json").write_text(
        json.dumps(placeholder, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return "camera/camera_keyframes.json"


def _read_pipeline_state(project_dir: Path) -> dict:
    path = project_dir / "pipeline_state.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        _log.warning("[archive] pipeline_state unreadable: %s", exc)
        return {}


def _shot_record(project_dir: Path, shot_id: str) -> dict:
    state = _read_pipeline_state(project_dir)
    for shot in state.get("shots") or []:
        if str(shot.get("id")) == shot_id:
            return shot
    return {}


def _scene_type_for(project_dir: Path, scene_id: Optional[str]) -> str:
    """indoor / outdoor，给 GroundingDINO 选提示词。"""
    state = _read_pipeline_state(project_dir)
    for scene in state.get("script_data", {}).get("scenes") or []:
        if scene_id and str(scene.get("id")) != scene_id:
            continue
        text = f"{scene.get('location') or ''} {scene.get('atmosphere') or ''}".lower()
        if any(k in text for k in ("室", "馆", "厅", "房", "店", "indoor", "cafe", "room")):
            return "indoor"
        if scene_id:
            break
    return "outdoor"


def _find_scene_wide(project_dir: Path, scene_id: Optional[str]) -> Optional[Path]:
    scenes = project_dir / "scenes"
    if not scenes.is_dir():
        return None
    hits = sorted(scenes.rglob("wide.png"))
    if not hits:
        return None
    if scene_id:
        for hit in hits:
            if scene_id in hit.as_posix():
                return hit
    return hits[0]


_OCCLUSION_FILL_MARK = "occluded_lama_v1"


def _layers_already_exported(layers_dir: Path, source: Path) -> bool:
    if not layers_dir.is_dir():
        return False
    needed = [layers_dir / f"{name}.png" for name in _LAYER_NAMES]
    if not all(p.is_file() and p.stat().st_size > 0 for p in needed):
        return False
    mark = layers_dir / "_fill.json"
    try:
        payload = json.loads(mark.read_text(encoding="utf-8"))
    except Exception:
        return False
    if payload.get("method") != _OCCLUSION_FILL_MARK:
        return False
    try:
        src_mtime = source.stat().st_mtime
    except OSError:
        return True
    return all(p.stat().st_mtime >= src_mtime for p in needed)


def ensure_depth_layers(project_dir: Path, scene_id: Optional[str] = None) -> list[str]:
    """按文档路线生成 5 层 RGBA：DepthAnything → GroundingDINO+SAM2 → 地面拟合 → 分层导出。

    写入 ``<project>/layers/{sky,background,midground,foreground,ground}.png``。
    源图未变且 5 层都在时跳过。模型不可用时记日志并返回空列表，归档仍可继续。
    """
    source = _find_scene_wide(project_dir, scene_id)
    if source is None:
        _log.info("[archive] no wide.png — skip depth layer export")
        return []

    layers_dir = project_dir / "layers"
    if _layers_already_exported(layers_dir, source):
        _log.info("[archive] depth layers up to date: %s", layers_dir)
        return [p.name for p in sorted(layers_dir.glob("*.png"))]

    try:
        from PIL import Image
        from app.models.model_manager import model_manager
        from app.services.layer_exporter import export_layers
    except Exception as exc:
        _log.warning("[archive] layer pipeline imports failed: %s", exc)
        return []

    image = Image.open(source).convert("RGB")
    try:
        depth_meters = model_manager.depth_model.predict_meters(image, scale=50.0)
    except Exception as exc:
        _log.warning("[archive] DepthAnything failed, layers not regenerated: %s", exc)
        return []

    object_assets: list = []
    ground_entries: list = []
    scene_type = _scene_type_for(project_dir, scene_id)
    try:
        from app.services.object_detector import detect_objects
        object_assets, ground_entries = detect_objects(
            image, depth_meters, scene_type=scene_type,
        )
    except Exception as exc:
        _log.warning("[archive] object detection failed, depth buckets only: %s", exc)

    ground_asset = None
    try:
        from app.services.ground_reconstructor import reconstruct_ground
        ground_asset = reconstruct_ground(
            image, depth_meters, detections=ground_entries,
        )
    except Exception as exc:
        _log.warning("[archive] ground reconstruction failed: %s", exc)

    try:
        from app.services.layer_exporter import inpaint_occluded_layers
        layer_imgs = export_layers(
            image,
            depth_meters,
            object_assets=object_assets or None,
            ground_asset=ground_asset,
        )
        layer_imgs = inpaint_occluded_layers(
            image,
            layer_imgs,
            depth_meters,
            object_assets=object_assets or None,
            ground_asset=ground_asset,
        )
    except Exception as exc:
        _log.warning("[archive] export_layers failed: %s", exc)
        return []

    layers_dir.mkdir(parents=True, exist_ok=True)
    (layers_dir / "_fill.json").write_text(
        json.dumps({"method": _OCCLUSION_FILL_MARK}, ensure_ascii=False),
        encoding="utf-8",
    )
    written: list[str] = []
    for name, img in layer_imgs.items():
        dest = layers_dir / f"{name}.png"
        img.save(dest, format="PNG")
        written.append(dest.name)
        _log.info("[archive] wrote depth layer %s", dest)
    return written


def _camera_path_for_shot(project_dir: Path, shot_id: str) -> tuple[list[dict], float]:
    """用分镜的运镜 / 景别 / 时长生成 cameraPath。没有分镜记录时返回空路径。"""
    shot = _shot_record(project_dir, shot_id)
    if not shot:
        return [], 5.0
    duration = float(shot.get("duration_seconds") or 5.0)
    try:
        from app.services.camera_path_generator import build_camera_path
        path = build_camera_path(
            shot.get("camera_movement") or "Static",
            shot.get("shot_size") or "Medium Shot",
            duration,
        )
    except Exception as exc:
        _log.warning("[archive] camera path failed: %s", exc)
        return [], duration
    return path, duration


def build_shot_archive(
    project_id: str,
    shot_id: str,
    *,
    workspace_dir: Optional[Path] = None,
    output_path: Optional[Path] = None,
    scene_id: Optional[str] = None,
    lighting_preset: Optional[str] = None,
    camera_path: Optional[list[dict]] = None,
    characters_override: Optional[list[dict]] = None,
) -> dict[str, Any]:
    """
    Pack a shot archive ZIP for Blender import.

    Args:
        lighting_preset: 可选预设名（如 "warm_interior"），从插件 presets/lighting/ 读
            对应 JSON 作为 manifest.lighting。None 时用 _DEFAULT_LIGHTING。
        camera_path: 可选相机关键帧序列（T06），每项
            {time, position: [x,y,z], target: [x,y,z], fov}。None 时 manifest
            不含 cameraPath 字段（向后兼容）。
        characters_override: 可选角色列表，覆盖自动扫描 motions/ 的结果。

    Returns:
      {
        "zipPath": str,
        "fileName": str,
        "fileSize": int,
        "manifest": dict,
        "fileCount": int,
      }
    """
    from app.services.project_store import WORKSPACE_DIR, project_store

    root = Path(workspace_dir) if workspace_dir else WORKSPACE_DIR
    project_dir = root / project_id
    if not project_dir.is_dir():
        raise FileNotFoundError(f"Project not found: {project_id}")

    shot_dir = project_dir / "shots" / shot_id
    # Shot dir is preferred but not mandatory — we can still pack project assets
    if not shot_dir.is_dir():
        _log.warning("[archive] shot dir missing: %s — packing project assets only", shot_dir)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    zip_name = f"{project_id}_{shot_id}_archive.zip"
    if output_path is None:
        archives_dir = project_dir / "archives"
        archives_dir.mkdir(parents=True, exist_ok=True)
        output_path = archives_dir / zip_name
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="aicss_archive_") as tmp:
        staging = Path(tmp) / "root"
        staging.mkdir()

        file_count = 0

        # ── shot frames / artifacts ──────────────────────────────────────────
        if shot_dir.is_dir():
            file_count += _copy_tree(shot_dir, staging / "shots" / shot_id)

        # ── characters + motions ─────────────────────────────────────────────
        file_count += _copy_tree(project_dir / "characters", staging / "character")
        file_count += _copy_tree(project_dir / "motions", staging / "character" / "_motions")

        # ── scenes (keyframe views) ──────────────────────────────────────────
        file_count += _copy_tree(project_dir / "scenes", staging / "scene")

        # ── 文档路线：深度分层 + 分镜运镜 ──────────────────────────────────
        # 横条切图不在这里。缺层时跑 DepthAnything / DINO / SAM2 / 地面拟合。
        try:
            ensure_depth_layers(project_dir, scene_id)
        except Exception as exc:
            _log.warning("[archive] ensure_depth_layers failed: %s", exc)

        if camera_path is None:
            camera_path, shot_duration = _camera_path_for_shot(project_dir, shot_id)
        else:
            shot_duration = float(_shot_record(project_dir, shot_id).get("duration_seconds") or 5.0)

        # ── layers / meshes / camera ─────────────────────────────────────────
        layer_map = _collect_layers(staging, project_dir)
        file_count += len(layer_map)
        mesh_files = _collect_meshes(staging, project_dir)
        file_count += len(mesh_files)
        cam_rel = _collect_camera(staging, project_dir, shot_id)
        if cam_rel:
            file_count += 1

        # ── scripts ──────────────────────────────────────────────────────────
        scripts_dir = staging / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        (scripts_dir / "blender_import.py").write_text(_BLENDER_IMPORT_SCRIPT, encoding="utf-8")
        (scripts_dir / "lighting.json").write_text(
            json.dumps(_DEFAULT_LIGHTING, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        file_count += 2

        # ── Blender-facing manifest (relative paths) ─────────────────────────
        # Prefer existing project manifest metadata when available.
        width, height = 1920, 1080
        try:
            pm = project_store._read_manifest(project_id)
            width = getattr(pm, "image_width", None) or width
            height = getattr(pm, "image_height", None) or height
        except Exception:
            pass

        # ── characters (T11) ──────────────────────────────────────────────────
        if characters_override is not None:
            characters_field = characters_override
        else:
            characters_field = _collect_characters(project_dir)

        # ── lighting (T14): 优先从预设读，否则用默认 ─────────────────────────
        lighting_field = _DEFAULT_LIGHTING
        lighting_preset_name = lighting_preset or "warm_interior"
        if lighting_preset:
            preset_data = _load_lighting_preset(lighting_preset)
            if preset_data is not None:
                # 取 key/fill/rim 三段，保留 name/description 在 manifest 顶层
                lighting_field = {
                    role: preset_data[role]
                    for role in ("key", "fill", "rim")
                    if role in preset_data
                } or _DEFAULT_LIGHTING

        cam_fov = 35.0
        cam_distance = 12.0
        if camera_path:
            first = camera_path[0]
            cam_fov = float(first.get("fov") or cam_fov)
            pos = first.get("position") or [0.0, 0.0, cam_distance]
            cam_distance = float(pos[2]) if len(pos) > 2 else cam_distance

        manifest: dict[str, Any] = {
            "shotId": shot_id,
            "sceneId": scene_id or shot_id,
            "projectId": project_id,
            "width": width,
            "height": height,
            "duration": shot_duration,
            "layers": layer_map,
            "zOffsets": [z for z in _DEFAULT_Z_OFFSETS if z["layer"] in layer_map or not layer_map],
            "camera": {
                "shotType": "wide",
                "fov": cam_fov,
                "distance": cam_distance,
                "target": [0.0, 0.0, 0.0],
                "keyframesPath": cam_rel,
            },
            "cameraPath": list(camera_path) if camera_path else [],
            "characters": characters_field,
            "lighting": lighting_field,
            "lightingPreset": lighting_preset_name,
            "meshes": mesh_files,
            "archivedAt": datetime.now(timezone.utc).isoformat(),
            "archiveVersion": 2,
        }
        # If no layers found, still emit default zOffsets for addon defaults
        if not layer_map:
            manifest["zOffsets"] = list(_DEFAULT_Z_OFFSETS)

        (staging / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        file_count += 1

        # Also keep a copy of project-level manifest if present
        proj_manifest = project_dir / "manifest.json"
        if proj_manifest.is_file():
            shutil.copy2(proj_manifest, staging / "project_manifest.json")
            file_count += 1

        # ── zip ──────────────────────────────────────────────────────────────
        if output_path.exists():
            output_path.unlink()
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in staging.rglob("*"):
                if p.is_file():
                    zf.write(p, arcname=str(p.relative_to(staging)).replace("\\", "/"))

    size = output_path.stat().st_size
    _log.info(
        "[archive] wrote %s (%d bytes, ~%d files) for %s/%s",
        output_path, size, file_count, project_id, shot_id,
    )
    return {
        "zipPath": str(output_path.resolve()),
        "fileName": output_path.name,
        "fileSize": size,
        "manifest": manifest,
        "fileCount": file_count,
        "projectId": project_id,
        "shotId": shot_id,
    }


def update_archive_manifest_field(
    zip_path: Path | str,
    field: str,
    value: Any,
) -> dict:
    """更新已打包 shot archive ZIP 内 manifest.json 的单个字段（T06 用）。

    读取原 zip → 修改 manifest → 重写 zip（保留所有其它文件）。
    返回更新后的 manifest dict。
    """
    zip_path = Path(zip_path)
    if not zip_path.is_file():
        raise FileNotFoundError(f"Archive not found: {zip_path}")

    with zipfile.ZipFile(zip_path, "r") as zf_in:
        names = zf_in.namelist()
        if "manifest.json" not in names:
            raise ValueError(f"manifest.json not found in {zip_path}")
        manifest = json.loads(zf_in.read("manifest.json"))
        other_files = {
            n: zf_in.read(n) for n in names if n != "manifest.json"
        }

    manifest[field] = value

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf_out:
        for name, data in other_files.items():
            zf_out.writestr(name, data)
        zf_out.writestr(
            "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2),
        )

    _log.info("[archive] updated field %s in %s", field, zip_path)
    return manifest

