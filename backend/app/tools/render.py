"""相机路径与 Blender 渲染工具。

- ``camera_path``：纯函数，把运镜 + 景别 + 时长变成相机关键帧表
  （``app.services.camera_path_generator.build_camera_path``）。
- ``render_shots``：无头 Blender 批量渲染。内部复用
  ``app.endpoints_compose._run_render_queue_blender`` 的子进程调用逻辑
  （懒加载引入，避免 import 本模块时拉起 FastAPI）；manifest 解析在本
  模块内完成，工作目录显式传。
"""
from __future__ import annotations

import logging
import tempfile
import zipfile
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger("aicss.tools.render")

__all__ = ["camera_path", "render_shots"]

PathLike = Union[str, Path]


def camera_path(movement: str, shot_size: str, duration: float) -> list[dict]:
    """生成相机关键帧表（起止两帧；Static 只有一帧）。

    输入:
        movement: 运镜枚举字符串，如 "Static" / "Dolly In" / "Pan Right"
            （完整枚举见 ``app.services.shot_generator.CameraMovement``）。
        shot_size: 景别枚举字符串，如 "Wide Shot" / "Medium Shot"。
        duration: 时长（秒）。
    输出:
        dict 列表，每项 {time, position: [x,y,z], target: [x,y,z], fov}；
        可直接写入 shot archive 的 manifest.cameraPath。
    副作用:
        无。
    模型:
        无。
    """
    from app.services.camera_path_generator import build_camera_path

    return build_camera_path(movement, shot_size, duration)


def _resolve_shot_manifest(project_dir: Path, shot_id: str, staging: Path) -> Optional[str]:
    """解压 shot archive 到 staging/<shot_id>/ 并返回 manifest.json 绝对路径。

    与 ``app.endpoints_compose._resolve_shot_manifest`` 同规则，但项目目录
    由调用方显式给（不读全局 WORKSPACE_DIR）。找不到归档时返回 None。
    """
    candidates = [
        project_dir / "archives" / f"{project_dir.name}_{shot_id}_archive.zip",
        project_dir / "shots" / shot_id / "manifest.json",
    ]
    for cand in candidates:
        if not cand.exists():
            continue
        if cand.suffix == ".zip":
            target = staging / shot_id
            target.mkdir(parents=True, exist_ok=True)
            try:
                with zipfile.ZipFile(cand, "r") as zf:
                    zf.extractall(target)
            except Exception as exc:
                logger.warning("[render_shots] failed to unzip %s: %s", cand, exc)
                return None
            manifest = target / "manifest.json"
            return str(manifest) if manifest.is_file() else None
        return str(cand)
    return None


def render_shots(
    project_id: str,
    shot_ids: list[str],
    workspace_dir: Optional[PathLike] = None,
    samples: int = 32,
    resolution: tuple[int, int] = (1920, 1080),
    device: str = "GPU",
    fps: int = 24,
    lighting_preset: Optional[str] = None,
    timeout_seconds: int = 1800,
) -> dict:
    """用无头 Blender 批量渲染一组分镜（每个分镜需已打好 archive ZIP）。

    输入:
        project_id: 项目 ID。
        shot_ids: 要渲染的分镜 ID 列表；每个都需要存在
            ``<项目>/archives/<pid>_<shot>_archive.zip``（``build_shot_archive``
            的产物）。缺归档的分镜记 failed，其余继续。
        workspace_dir: 工作区根目录；None 时用部署默认工作区
            （app.services.project_store.WORKSPACE_DIR）。
        samples: Cycles 采样数。
        resolution: (宽, 高) 像素。
        device: "GPU" / "CPU"（GPU 不可用时 Blender 端自行回落）。
        fps: 时间轴帧率。
        lighting_preset: 覆盖 manifest 的 lightingPreset；None 读 manifest。
        timeout_seconds: Blender 子进程超时。
    输出:
        dict：results（每项 {shotId, status, outputPath, error}）/
        totalSucceeded / totalFailed / blenderAvailable / outputDir /
        error（可选）。Blender 不存在时 blenderAvailable=False 且
        results 为空——不抛异常，由调用方决定怎么处理。
    副作用:
        向 ``<项目>/renders/`` 写 <shot_id>.mp4 和
        render_queue_results.json；启动 Blender 子进程。
    模型:
        无（Blender 外部进程渲染；需要本机装有 Blender 或配置
        BLENDER_EXECUTABLE）。
    """
    if workspace_dir is None:
        from app.services.project_store import WORKSPACE_DIR

        workspace_dir = WORKSPACE_DIR
    project_dir = Path(workspace_dir) / project_id
    if not project_dir.is_dir():
        raise FileNotFoundError(f"Project not found: {project_id}")

    renders_dir = project_dir / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="aicss_render_staging_") as tmp:
        staging = Path(tmp)
        manifest_paths: list[str] = []
        missing: list[dict] = []
        for shot_id in shot_ids:
            mp = _resolve_shot_manifest(project_dir, shot_id, staging)
            if mp is None:
                missing.append({
                    "shotId": shot_id,
                    "status": "failed",
                    "outputPath": None,
                    "error": f"Shot archive not found for {shot_id} in {project_id}",
                })
            else:
                manifest_paths.append(mp)

        summary: dict = {
            "results": [],
            "totalSucceeded": 0,
            "totalFailed": 0,
            "blenderAvailable": True,
        }
        if manifest_paths:
            # 懒加载：避免 import 本模块时把 FastAPI 拉进依赖链。
            from app.endpoints_compose import _run_render_queue_blender

            summary = _run_render_queue_blender(
                project_id=project_id,
                manifest_paths=manifest_paths,
                output_dir=str(renders_dir),
                samples=samples,
                resolution=tuple(resolution),
                device=device,
                fps=fps,
                lighting_preset=lighting_preset,
                timeout_seconds=timeout_seconds,
            )

        op_results = []
        for r in summary.get("results", []):
            try:
                op_results.append({
                    "shotId": str(r.get("shotId", "")),
                    "status": r.get("status", "failed"),
                    "outputPath": r.get("outputPath"),
                    "error": r.get("error"),
                })
            except Exception:
                continue

        all_results = op_results + missing
        out = {
            "results": all_results,
            "totalSucceeded": sum(1 for r in all_results if r["status"] == "succeeded"),
            "totalFailed": sum(1 for r in all_results if r["status"] == "failed"),
            "blenderAvailable": bool(summary.get("blenderAvailable", True)),
            "outputDir": str(renders_dir),
        }
        if summary.get("error"):
            out["error"] = summary["error"]
        return out
