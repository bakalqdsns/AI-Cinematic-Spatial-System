"""
render_queue operator (T07) — 多镜头批量渲染。

读取一组 shot manifest 路径，逐个：
  1. 清空当前场景
  2. 调 ``aicss.import_layers`` 装载层 + 角色平面
  3. 调 ``aicss.setup_camera_animation`` 烘焙相机关键帧
  4. 调 ``aicss.add_lighting`` 加 3 点光
  5. 用 Cycles（不可用时回退 Eevee）渲帧序列到 MP4

Cycles 配置（采样数 / 分辨率 / 设备）从 operator 属性读，默认采样 32、
1920x1080、GPU。失败 shot 记录错误继续，不阻塞队列。

输出路径：``<output_dir>/<shot_id>.mp4``（默认 ``projects/<pid>/renders``）。

非 Blender 环境下 operator 类仍可 import，但 register 为 no-op（见 __init__.py）。
"""
from __future__ import annotations

import json
import os

try:
    import bpy
    from bpy.types import Operator
    from bpy.props import StringProperty, IntProperty, EnumProperty, BoolProperty
    _HAS_BPY = True
except ImportError:
    _HAS_BPY = False

    class Operator:  # type: ignore[no-redef]
        pass

    def StringProperty(**kw): return None  # type: ignore[no-redef]
    def IntProperty(**kw): return None  # type: ignore[no-redef]
    def EnumProperty(**kw): return None  # type: ignore[no-redef]
    def BoolProperty(**kw): return None  # type: ignore[no-redef]


def _split_paths(raw: str) -> list:
    """把分号 / 换行分隔的路径字符串切成 list，去空白与不存在的项。"""
    if not raw:
        return []
    out = []
    for chunk in raw.replace("\n", ";").split(";"):
        p = chunk.strip()
        if p and os.path.exists(p):
            out.append(p)
    return out


def _clear_scene() -> None:
    """删除当前场景里所有对象，避免上一个 shot 的层 / 灯 / 相机残留。"""
    for obj in list(bpy.data.objects):
        try:
            bpy.data.objects.remove(obj, do_unlink=True)
        except Exception:
            pass
    # 清掉残留 data block，避免内存累积
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.images,
                 bpy.data.lights, bpy.data.cameras):
        for block in list(coll):
            try:
                if block.users == 0:
                    coll.remove(block)
            except Exception:
                pass


def _configure_cycles(scene, samples: int, device: str) -> str:
    """配置渲染引擎，返回实际使用的引擎名（'CYCLES' 或 'BLENDER_EEVEE'）。"""
    try:
        scene.render.engine = 'CYCLES'
    except Exception:
        scene.render.engine = 'BLENDER_EEVEE'
        return 'BLENDER_EEVEE'

    if hasattr(scene, "cycles"):
        try:
            scene.cycles.samples = max(1, int(samples))
        except Exception:
            pass
        try:
            scene.cycles.device = device if device in ("GPU", "CPU") else "GPU"
        except Exception:
            try:
                scene.cycles.device = "CPU"
            except Exception:
                pass
    return 'CYCLES'


def _configure_ffmpeg(scene, fps: int) -> None:
    """配置渲染输出为 PNG 序列（Blender 5.2 移除了 FFMPEG 直接输出）。
    MP4 合成由 _render_one_shot 渲染后调 ffmpeg 完成。"""
    scene.render.image_settings.file_format = 'PNG'
    try:
        scene.render.image_settings.color_mode = 'RGBA'
    except Exception:
        pass
    try:
        scene.render.fps = int(fps)
    except Exception:
        pass


def _render_one_shot(manifest_path: str, output_dir: str,
                     samples: int, res_x: int, res_y: int,
                     device: str, fps: int, lighting_preset: str) -> dict:
    """渲染单个 shot。返回 ``{shotId, status, outputPath?, error?}``。"""
    from ..utils.scene_utils import read_manifest

    result = {"shotId": "", "status": "failed", "outputPath": None, "error": None}
    try:
        manifest = read_manifest(manifest_path)
    except Exception as exc:
        result["error"] = f"manifest read failed: {exc}"
        return result

    shot_id = manifest.get("shotId") or os.path.basename(os.path.dirname(manifest_path))
    result["shotId"] = shot_id

    try:
        _clear_scene()

        # 1) 装载层 + 角色（character plane 用中间帧做静态落位）
        bpy.ops.aicss.import_layers(manifest_path=manifest_path)

        # 1.5) 把角色帧序列作为 Image Sequence 贴图挂上去（覆盖静态 material，
        #      让角色按帧播放动画，而不是定着不动）
        try:
            bpy.ops.aicss.import_character_frames(
                manifest_path=manifest_path,
                fps=int(fps),
            )
        except Exception as exc:
            # 帧序列导入失败不致命——退化为静态角色
            print(f"[AICSS] import_character_frames failed (will use static): {exc}")

        # 2) 相机动画：读 manifest.cameraPath（由 camera_path_generator 按分镜运镜写出）
        bpy.ops.aicss.setup_camera_animation(
            manifest_path=manifest_path,
            fps=float(fps),
        )

        # 2.5) 图层视差：有 cameraPath 时按深度差速移动各层（T09）
        try:
            bpy.ops.aicss.layer_motion(
                manifest_path=manifest_path,
                fps=float(fps),
            )
        except Exception as exc:
            print(f"[AICSS] layer_motion failed (layers stay static): {exc}")

        # 3) 灯光：优先用 manifest 的 lightingPreset，回退到 warm_interior
        preset = lighting_preset or manifest.get("lightingPreset") or "warm_interior"
        # add_lighting 的 preset 枚举只接受 4 项，自定义预设走 custom + path。
        # 这里直接用 BUILTIN_PRESETS 里能找到的，找不到就回退 warm_interior。
        try:
            from .add_lighting import BUILTIN_PRESETS
            if preset not in BUILTIN_PRESETS:
                preset = "warm_interior"
        except Exception:
            preset = "warm_interior"
        bpy.ops.aicss.add_lighting(preset=preset)

        # 4) 渲染配置
        scene = bpy.context.scene
        engine = _configure_cycles(scene, samples, device)
        scene.render.resolution_x = int(res_x)
        scene.render.resolution_y = int(res_y)
        scene.render.resolution_percentage = 100
        _configure_ffmpeg(scene, fps)

        # 4.5) 提高世界环境光，避免场景太暗（纸雕平面无反射，全靠环境光+灯光照亮）
        try:
            world = scene.world
            if world is None:
                world = bpy.data.worlds.new("AICSS_World")
                scene.world = world
            world.use_nodes = True
            bg = world.node_tree.nodes.get("Background")
            if bg is not None:
                bg.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
                bg.inputs["Strength"].default_value = 1.5
        except Exception:
            pass

        # 时间线范围：从 manifest.duration 推导，默认 5s
        # 5s@24fps = 120 帧，用 1-indexed（1~120）避免 frame 0 的 image sequence 加载 bug
        duration = float(manifest.get("duration") or 5.0)
        scene.frame_start = 1
        scene.frame_end = max(int(round(fps * duration)), 1)

        # 5) 输出路径：渲染 PNG 序列到子目录，再用 ffmpeg 合成 MP4
        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, f"{shot_id}.mp4")
        frames_dir = os.path.join(output_dir, f"{shot_id}_frames")
        os.makedirs(frames_dir, exist_ok=True)
        # 清理旧帧
        for old in os.listdir(frames_dir):
            if old.endswith(".png"):
                try:
                    os.remove(os.path.join(frames_dir, old))
                except Exception:
                    pass
        scene.render.filepath = os.path.join(frames_dir, "frame_####.png")

        # 5.5) 保存 .blend 工程文件，方便在 Blender GUI 打开调试几何 / 材质 / 灯光
        try:
            blend_path = os.path.join(output_dir, f"{shot_id}_scene.blend")
            bpy.ops.wm.save_as_mainfile(filepath=blend_path)
            result["blendPath"] = blend_path
        except Exception as exc:
            # 保存失败不阻塞渲染
            result["blendError"] = str(exc)

        # 6) 渲染动画（PNG 序列）
        # 先 frame_set 触发 image sequence 刷新，避免第一帧 image texture 未加载（白条）
        try:
            scene.frame_set(scene.frame_end)
            scene.frame_set(scene.frame_start)
        except Exception:
            pass
        bpy.ops.render.render(animation=True)

        # 7) ffmpeg 合成 MP4
        import subprocess, shutil
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            # fallback: FFMPEG_PATH env
            ffmpeg = os.environ.get("FFMPEG_PATH") or shutil.which("ffmpeg")
        if not ffmpeg:
            result["error"] = "ffmpeg not found — cannot mux PNG sequence to MP4"
            return result
        frame_glob = os.path.join(frames_dir, "frame_%04d.png")
        mux_cmd = [ffmpeg, "-y", "-framerate", str(int(fps)),
                   "-i", frame_glob, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                   "-vf", f"scale={int(res_x)}:{int(res_y)}",
                   out_path]
        mux = subprocess.run(mux_cmd, capture_output=True, text=True, timeout=300)
        if mux.returncode != 0:
            result["error"] = f"ffmpeg mux failed: {mux.stderr[-300:]}"
            return result

        if not os.path.exists(out_path):
            result["error"] = f"mux finished but MP4 not found at {out_path}"
            return result

        result["status"] = "succeeded"
        result["outputPath"] = out_path
        return result
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result


class AICSS_OT_render_queue(Operator):
    """Render multiple AICSS shots to MP4 in a single batch.

    Properties:
        manifest_paths: Semicolon- or newline-separated list of manifest.json
            paths. Each manifest is rendered as one shot.
        output_dir: Directory to write ``<shot_id>.mp4`` files into.
            Defaults to ``projects/<project_id>/renders``.
        project_id: Project ID — only used to derive the default output dir.
        samples: Cycles sample count (default 32).
        resolution_x / resolution_y: Render resolution (default 1920x1080).
        device: 'GPU' or 'CPU' (default GPU; falls back to CPU if unavailable).
        fps: Timeline frame rate (default 24).
        lighting_preset: Override manifest's lightingPreset. Empty = read
            from manifest, fallback 'warm_interior'.
        continue_on_error: When True (default), a failed shot doesn't abort
            the queue — its error is recorded and the next shot continues.
    """
    bl_idname = "aicss.render_queue"
    bl_label = "Render Queue"
    bl_options = {'REGISTER'}

    manifest_paths: StringProperty(
        name="Manifest Paths",
        description="Semicolon- or newline-separated list of manifest.json paths",
        subtype='FILE_PATH',
    )
    output_dir: StringProperty(
        name="Output Dir",
        description="Directory to write <shot_id>.mp4 files",
        subtype='DIR_PATH',
    )
    project_id: StringProperty(
        name="Project ID",
        default="",
    )
    samples: IntProperty(
        name="Samples",
        default=32,
        min=1,
        max=4096,
    )
    resolution_x: IntProperty(
        name="Resolution X",
        default=1920,
        min=16,
        max=8192,
    )
    resolution_y: IntProperty(
        name="Resolution Y",
        default=1080,
        min=16,
        max=8192,
    )
    device: EnumProperty(
        name="Device",
        items=[
            ("GPU", "GPU", "Use GPU (CUDA/Optix/HIP/Metal)"),
            ("CPU", "CPU", "Use CPU only"),
        ],
        default="GPU",
    )
    fps: IntProperty(
        name="FPS",
        default=24,
        min=1,
        max=120,
    )
    lighting_preset: StringProperty(
        name="Lighting Preset",
        default="",
        description="Override manifest's lightingPreset. Empty = read from manifest.",
    )
    continue_on_error: BoolProperty(
        name="Continue on Error",
        default=True,
        description="Failed shots are recorded but don't abort the queue",
    )

    def execute(self, context):
        if not _HAS_BPY:
            self.report({'ERROR'}, "bpy not available — run inside Blender")
            return {'CANCELLED'}

        paths = _split_paths(self.manifest_paths)
        if not paths:
            self.report({'ERROR'}, "No manifest paths given (or none exist)")
            return {'CANCELLED'}

        # 输出目录：默认 projects/<pid>/renders
        out_dir = self.output_dir
        if not out_dir:
            if not self.project_id:
                self.report({'ERROR'}, "output_dir or project_id required")
                return {'CANCELLED'}
            from app.services.project_store import WORKSPACE_DIR  # type: ignore
            out_dir = str(WORKSPACE_DIR / self.project_id / "renders")
        os.makedirs(out_dir, exist_ok=True)

        results = []
        succeeded = 0
        failed = 0
        for mp in paths:
            res = _render_one_shot(
                manifest_path=mp,
                output_dir=out_dir,
                samples=self.samples,
                res_x=self.resolution_x,
                res_y=self.resolution_y,
                device=self.device,
                fps=self.fps,
                lighting_preset=self.lighting_preset,
            )
            results.append(res)
            if res["status"] == "succeeded":
                succeeded += 1
            else:
                failed += 1
                self.report(
                    {'WARNING'},
                    f"Shot {res['shotId']} failed: {res['error']}",
                )
                if not self.continue_on_error:
                    break

        # 把结果 JSON 写到输出目录，方便后端端点读取
        try:
            summary_path = os.path.join(out_dir, "render_queue_results.json")
            with open(summary_path, "w", encoding="utf-8") as fp:
                json.dump({
                    "results": results,
                    "totalSucceeded": succeeded,
                    "totalFailed": failed,
                }, fp, ensure_ascii=False, indent=2)
        except Exception:
            pass

        self.report(
            {'INFO'},
            f"Render queue: {succeeded} ok / {failed} failed / {len(paths)} total",
        )
        return {'FINISHED'}
