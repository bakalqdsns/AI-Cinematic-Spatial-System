"""AICSS 工具层 —— 《纸间行》链路能力的独立、可单点调用的接口。

设计约定
--------
- 每个工具是 ``app.tools.<module>`` 里的一个函数，输入输出只用
  dict / dataclass / 基本类型 / numpy 数组 / PIL 图像。
- 不依赖 FastAPI 请求对象；不在函数体内读取全局 settings 单例——
  需要的参数（尺寸、阈值、模型句柄、工作目录）全部显式传。
- GPU 模型句柄（depth_model / sam2_model / inpaint_fn …）可显式注入，
  便于测试和复用；传 ``None`` 时才退回 ``app.models.model_manager`` 懒加载。
- 模块级 import 不加载任何模型权重；LLM / 出图 / 视频类工具是 async，
  纯计算工具是 sync。

外部 agent 用法::

    from app.tools import key_greenscreen, split_layers, estimate_depth

    rgba_paths = key_greenscreen(frames, "out/seg")
    depth = estimate_depth("scene.png")
    layers = split_layers(image, depth, object_assets=[], scene_class="street")

工具清单见 ``app.tools.list_tools()`` 和同目录 ``README.md``。
"""
from __future__ import annotations

# name -> (submodule, attribute)。懒加载：import app.tools 本身不拉重依赖。
_TOOL_TABLE: dict[str, tuple[str, str]] = {
    # 剧本解析
    "normalize_script_text": ("app.tools.script", "normalize_script_text"),
    "parse_script_text": ("app.tools.script", "parse_script_text"),
    "extract_characters": ("app.tools.script", "extract_characters"),
    "generate_shots": ("app.tools.script", "generate_shots"),
    # 视觉提示词
    "character_visual_prompt": ("app.tools.prompts", "character_visual_prompt"),
    "scene_visual_prompt": ("app.tools.prompts", "scene_visual_prompt"),
    # 出图（场景关键帧 / 人物三视图 / 变体）
    "scene_keyframes": ("app.tools.images", "scene_keyframes"),
    "character_three_view": ("app.tools.images", "character_three_view"),
    "character_variation": ("app.tools.images", "character_variation"),
    # 动作视频 / 抽帧
    "action_video": ("app.tools.video", "action_video"),
    "extract_frames": ("app.tools.video", "extract_frames"),
    # 抠像（绿幕 / SAM2）
    "key_greenscreen": ("app.tools.chroma_key", "key_greenscreen"),
    "chroma_key_rgba_array": ("app.tools.chroma_key", "chroma_key_rgba_array"),
    "is_greenscreen_frame": ("app.tools.chroma_key", "is_greenscreen_frame"),
    "segment_person": ("app.tools.chroma_key", "segment_person"),
    # 深度估计
    "estimate_depth": ("app.tools.depth", "estimate_depth"),
    # 物件检测
    "detect_objects": ("app.tools.detect", "detect_objects"),
    "DetectResult": ("app.tools.detect", "DetectResult"),
    # 场景类识别
    "classify_scene": ("app.tools.classify", "classify_scene"),
    "scene_class_scores": ("app.tools.classify", "scene_class_scores"),
    # 分层
    "split_layers": ("app.tools.layers", "split_layers"),
    "layer_masks": ("app.tools.layers", "layer_masks"),
    # 透视层距表
    "perspective_offsets": ("app.tools.perspective", "perspective_offsets"),
    "z_offset_table": ("app.tools.perspective", "z_offset_table"),
    # 遮挡补全
    "fill_occlusions": ("app.tools.inpaint", "fill_occlusions"),
    "inpaint_image": ("app.tools.inpaint", "inpaint_image"),
    # 归档
    "ensure_depth_layers": ("app.tools.archive", "ensure_depth_layers"),
    "build_shot_archive": ("app.tools.archive", "build_shot_archive"),
    # 相机路径 / Blender 渲染
    "camera_path": ("app.tools.render", "camera_path"),
    "render_shots": ("app.tools.render", "render_shots"),
}

__all__ = sorted(_TOOL_TABLE)


def __getattr__(name: str):
    """PEP 562 懒加载：首次访问某个工具名时才 import 对应子模块。"""
    target = _TOOL_TABLE.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module = importlib.import_module(target[0])
    value = getattr(module, target[1])
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))


def list_tools() -> dict[str, dict]:
    """返回全部工具的元信息：所属模块、是否 async、一句话说明。

    供外部 agent 做能力发现，例如::

        from app.tools import list_tools
        for name, meta in list_tools().items():
            print(name, meta["module"], meta["async"])
    """
    import importlib
    import inspect as _inspect

    table: dict[str, dict] = {}
    for name in __all__:
        module_name, attr = _TOOL_TABLE[name]
        module = importlib.import_module(module_name)
        fn = getattr(module, attr)
        doc = (_inspect.getdoc(fn) or "").splitlines()
        table[name] = {
            "module": module_name,
            "async": _inspect.iscoroutinefunction(fn),
            "summary": doc[0] if doc else "",
        }
    return table
