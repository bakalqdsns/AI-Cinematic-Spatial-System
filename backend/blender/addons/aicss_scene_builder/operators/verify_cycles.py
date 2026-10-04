"""
verify_cycles operator — T10 验收用：跑一个 5 帧 Cycles 渲染确认场景无崩溃。

不依赖 manifest，直接对当前场景渲 5 帧 PNG 到用户指定输出目录。
默认采样数 32，分辨率缩放 50%，足够快速验证材质 / 灯光 / 几何不崩。

非 Blender 环境下 operator 类仍可 import，但 register 为 no-op（见 __init__.py）。
"""
from __future__ import annotations

import os

try:
    import bpy
    from bpy.types import Operator
    from bpy.props import StringProperty, IntProperty
    _HAS_BPY = True
except ImportError:
    _HAS_BPY = False

    class Operator:  # type: ignore[no-redef]
        pass

    def StringProperty(**kw): return None  # type: ignore[no-redef]
    def IntProperty(**kw): return None  # type: ignore[no-redef]


class AICSS_OT_verify_cycles(Operator):
    """Render 5 frames with Cycles to verify the scene doesn't crash.

    Properties:
        output_dir: Directory to write PNG frames into. Defaults to the
            system temp dir under ``aicss_verify``.
        frame_count: Number of frames to render (default 5).
        samples: Cycles sample count (default 32). Lower = faster.
        resolution_scale: Percentage scale of the render resolution
            (default 50). 50% of 1920x1080 = 960x540, fast enough for a
            smoke test.
    """
    bl_idname = "aicss.verify_cycles"
    bl_label = "Verify Cycles (5 frames)"
    bl_options = {'REGISTER'}

    output_dir: StringProperty(
        name="Output Dir",
        description="Directory to write verification PNG frames",
        subtype='DIR_PATH',
    )
    frame_count: IntProperty(
        name="Frame Count",
        default=5,
        min=1,
        max=60,
    )
    samples: IntProperty(
        name="Samples",
        default=32,
        min=1,
        max=4096,
    )
    resolution_scale: IntProperty(
        name="Resolution Scale %",
        default=50,
        min=10,
        max=100,
    )

    def execute(self, context):
        if not _HAS_BPY:
            self.report({'ERROR'}, "bpy not available — run inside Blender")
            return {'CANCELLED'}

        out_dir = self.output_dir or os.path.join(
            os.environ.get("TEMP", "/tmp"), "aicss_verify"
        )
        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception as exc:
            self.report({'ERROR'}, f"Cannot create output dir: {exc}")
            return {'CANCELLED'}

        scene = context.scene
        prev_engine = scene.render.engine
        prev_samples = getattr(scene.cycles, "samples", 32) if hasattr(scene, "cycles") else None
        prev_scale = scene.render.resolution_percentage
        prev_start = scene.frame_start
        prev_end = scene.frame_end
        prev_filepath = scene.render.filepath

        try:
            # 选 Cycles；不可用（headless 无 GPU）时回退 Eevee
            try:
                scene.render.engine = 'CYCLES'
            except Exception:
                scene.render.engine = 'BLENDER_EEVEE'

            if hasattr(scene, "cycles"):
                scene.cycles.samples = self.samples
                # 优先用 GPU；不可用则用 CPU
                try:
                    scene.cycles.device = 'GPU'
                except Exception:
                    scene.cycles.device = 'CPU'

            scene.render.resolution_percentage = self.resolution_scale
            scene.render.image_settings.file_format = 'PNG'
            scene.render.filepath = os.path.join(out_dir, "verify_")

            start_frame = scene.frame_start
            for i in range(self.frame_count):
                frame = start_frame + i
                scene.frame_set(frame)
                scene.render.filepath = os.path.join(out_dir, f"verify_{frame:04d}.png")
                bpy.ops.render.render(write_still=True)

            # 列出渲染产物
            rendered = [
                f for f in os.listdir(out_dir)
                if f.startswith("verify_") and f.endswith(".png")
            ]
        except Exception as exc:
            # 还原设置
            scene.render.engine = prev_engine
            if prev_samples is not None and hasattr(scene, "cycles"):
                scene.cycles.samples = prev_samples
            scene.render.resolution_percentage = prev_scale
            scene.frame_start = prev_start
            scene.frame_end = prev_end
            scene.render.filepath = prev_filepath
            self.report({'ERROR'}, f"Cycles render crashed: {exc}")
            return {'CANCELLED'}

        # 还原设置
        scene.render.engine = prev_engine
        if prev_samples is not None and hasattr(scene, "cycles"):
            scene.cycles.samples = prev_samples
        scene.render.resolution_percentage = prev_scale
        scene.frame_start = prev_start
        scene.frame_end = prev_end
        scene.render.filepath = prev_filepath

        if not rendered:
            self.report({'ERROR'}, "Cycles ran but no PNGs were produced")
            return {'CANCELLED'}

        self.report(
            {'INFO'},
            f"Rendered {len(rendered)} frames to {out_dir} (engine={scene.render.engine})",
        )
        return {'FINISHED'}
