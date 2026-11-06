"""归档工具 —— 深度分层落盘与 Blender 可导入的 shot archive ZIP。

包装 ``app.services.shot_archiver``。所有路径参数显式传；``workspace_dir``
为 None 时才用 ``app.services.project_store.WORKSPACE_DIR``（部署默认工
作区）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

__all__ = ["ensure_depth_layers", "build_shot_archive"]

PathLike = Union[str, Path]


def ensure_depth_layers(
    project_dir: PathLike,
    scene_id: Optional[str] = None,
) -> list[str]:
    """为项目生成 5 层 RGBA 深度分层并落盘（幂等，有缓存）。

    流程：找 scenes/**/wide.png → 深度估计 → 物件检测 → 场景分类 →
    匹配表归层 → LaMa 遮挡补全 → 写 ``<project_dir>/layers/*.png``、
    ``_perspective.json``、``_fill.json``。任何一步失败只记日志、返回
    已写出的文件名（可能为空），不抛异常中断归档。

    输入:
        project_dir: 项目目录（需含 scenes/**/wide.png）。
        scene_id: 可选，限定用哪个场景的 wide.png。
    输出:
        写出的 PNG 文件名列表（如 ["sky.png", "background.png", ...]）；
        缓存命中时返回已有文件列表。
    副作用:
        向 ``<project_dir>/layers/`` 写文件。
    模型:
        Depth Anything V2 + GroundingDINO + SAM2 + LaMa（GPU），经
        ``app.models.model_manager`` 懒加载；任一失败自动降级。
    """
    from app.services.shot_archiver import ensure_depth_layers as _ensure

    return _ensure(Path(project_dir), scene_id)


def build_shot_archive(
    project_id: str,
    shot_id: str,
    workspace_dir: Optional[PathLike] = None,
    output_path: Optional[PathLike] = None,
    scene_id: Optional[str] = None,
    lighting_preset: Optional[str] = None,
    camera_path: Optional[list[dict]] = None,
    characters_override: Optional[list[dict]] = None,
) -> dict:
    """把一个分镜的资产打成 Blender 可导入的 ZIP（含 manifest.json）。

    输入:
        project_id / shot_id: 项目与分镜 ID。
        workspace_dir: 工作区根目录（项目目录 = workspace_dir/project_id）。
            None 时用部署默认工作区。
        output_path: ZIP 输出路径；None 时写到
            ``<项目>/archives/<pid>_<shot>_archive.zip``。
        scene_id: 可选场景 ID（影响深度分层与场景类判定）。
        lighting_preset: 灯光预设名（如 "warm_interior"）。
        camera_path: 可选相机关键帧列表（``camera_path()`` 的输出）；
            None 时按分镜记录的运镜/景别/时长自动生成。
        characters_override: 可选角色列表，覆盖自动扫描 motions/ 的结果。
    输出:
        dict：zipPath / fileName / fileSize / manifest / fileCount /
        projectId / shotId。
    副作用:
        写 ZIP 文件；必要时会先跑 ``ensure_depth_layers``（动用 GPU 模型）。
        项目目录不存在时抛 FileNotFoundError。
    模型:
        间接：ensure_depth_layers 用到的深度/检测/SAM2/LaMa。
    """
    from app.services.shot_archiver import build_shot_archive as _build

    return _build(
        project_id,
        shot_id,
        workspace_dir=Path(workspace_dir) if workspace_dir is not None else None,
        output_path=Path(output_path) if output_path is not None else None,
        scene_id=scene_id,
        lighting_preset=lighting_preset,
        camera_path=camera_path,
        characters_override=characters_override,
    )
