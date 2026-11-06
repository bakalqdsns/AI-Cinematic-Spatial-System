# AICSS 工具层（`app.tools`）

《纸间行》链路能力的独立、可单点调用接口。15 个模块、30 个工具，全部从
`app.tools` 顶层导出。

## 设计约定

- 输入输出只用 dict / dataclass / 基本类型 / numpy 数组 / PIL 图像；
  **不依赖 FastAPI 请求对象**，不在函数体内读全局 settings 单例——尺寸、
  阈值、模型句柄、工作目录全部显式传。
- GPU 模型句柄（`depth_model` / `sam2_model` / `inpaint_fn` …）显式注入；
  传 `None` 时才退回 `app.models.model_manager` 懒加载。测试时传假句柄
  即可完全避开真实模型。
- 模块级 import 不加载任何模型权重；LLM / 出图 / 视频类工具是 `async`，
  纯计算工具是 `sync`。

## 外部 agent 怎么发现和使用工具

直接按名字 import 使用（懒加载，import `app.tools` 本身不拉重依赖）：

```python
from app.tools import key_greenscreen, split_layers, estimate_depth

rgba_paths = key_greenscreen(frame_paths, "out/seg")
depth = estimate_depth("scene.png")                 # 需要 GPU 深度模型
layers = split_layers(image, depth, object_assets=[], scene_class="street")
```

能力发现用 `list_tools()`，返回全部工具的元信息（所属模块、是否 async、
一句话说明）：

```python
from app.tools import list_tools

for name, meta in list_tools().items():
    print(name, meta["module"], meta["async"], meta["summary"])
```

`app.tools.__all__` 是全部工具名；`_TOOL_TABLE` 记录每个名字对应的
`(子模块, 属性)`，首次访问时才真正 import 子模块。

闭集场景类名（`classify_scene` / `split_layers` 等共用）：
`school_playground` / `park` / `street` / `courtyard` / `indoor_room` /
`nature` / `unknown`。层名固定五层，从远到近：
`sky` / `background` / `midground` / `ground` / `foreground`。

---

## script —— 剧本解析（async，LLM 可选降级）

包装 `app.services.script_parser` / `shot_generator`。LLM（本地
llama.cpp）不可用时底层自动退回启发式解析，离线也能拿到结构化结果。

### `normalize_script_text(raw_text: str, language: str = "chinese") -> str`

- 输入：原始剧本文本；`language` 为 `"chinese" / "english" / "japanese"`。
- 输出：规范化后的剧本文本（Pass 1）。
- 副作用：无。可能向本地 llama.cpp 发一次请求，失败退回简单排版。
- 模型：本地 Qwen2.5-7B（llama.cpp），可选。

### `parse_script_text(text: str, language: str = "chinese", normalize: bool = False) -> dict`

- 输入：剧本文本；`normalize=True` 时先做 Pass 1 规范化。
- 输出：`ScriptData.to_dict()` 形状的 dict（title / genre / logline /
  characters / scenes / story_paragraphs / language）。
- 副作用：无。任一子任务失败只影响对应字段，整体退回启发式，不抛异常。
- 模型：本地 Qwen2.5-7B（llama.cpp），可选。

### `extract_characters(text: str, language: str = "chinese") -> list[dict]`

- 输入：剧本文本（原始或规范化后的均可）。
- 输出：角色 dict 列表（id / name / gender / age / personality /
  visual_prompt / reference_image）；伪角色（"特写"、"裂缝" 等）已过滤。
- 副作用：无。LLM 不可用时退回括号描述 + 对白前缀启发式。
- 模型：本地 Qwen2.5-7B（llama.cpp），可选。

### `generate_shots(script_data: dict, shots_per_scene: int = 6, language: Optional[str] = None) -> list[dict]`

- 输入：`parse_script_text` 的输出 dict；`shots_per_scene` 为每场景最少
  分镜数；`language=None` 时用剧本自带语言。
- 输出：分镜 dict 列表，按 shot_number 全局连续排序（含 id / scene_id /
  action_summary / dialogue / camera_movement / shot_size / characters /
  visual_prompts / duration_seconds / keyframe_start/end_prompt）。
- 副作用：无。LLM 不可用时按段落类型启发式生成。
- 模型：本地 Qwen2.5-7B（llama.cpp），可选。

最小例子（LLM 不在时自动降级，仍可跑通）：

```python
import asyncio
from app.tools import parse_script_text, extract_characters

script = asyncio.run(parse_script_text("内景 教室 日\n小明走进教室。", normalize=False))
chars = asyncio.run(extract_characters("小明（男，10岁）背着书包进门。"))
```

## prompts —— 视觉提示词（async，LLM 可选降级）

底层按部署 settings 决定走本地 llama.cpp 还是云端 DashScope；LLM 不可用
时退回模板拼接。

### `character_visual_prompt(character: dict, genre: str = "cinematic", language: str = "chinese") -> str`

- 输入：角色 dict（至少含 name，可含 gender / age / personality）；题材
  `genre`；`language`。
- 输出：英文视觉提示词（str），供三视图/参考图出图。
- 副作用 / 模型：可能向 LLM 发一次请求；失败退回模板提示词。

### `scene_visual_prompt(scene: dict, genre: str = "cinematic", language: str = "chinese") -> str`

- 输入：场景 dict（至少含 location，可含 time / atmosphere）。
- 输出：英文场景提示词（str），只描述地点，不含人物和动作。
- 副作用 / 模型：同上。

最小例子：

```python
import asyncio
from app.tools import character_visual_prompt

prompt = asyncio.run(character_visual_prompt(
    {"name": "小女孩", "gender": "女", "age": "8岁", "personality": "倔强"},
))
```

## images —— 出图（async，需要 GPU 或云端）

返回图像都是 base64 PNG 字符串（不带 `data:` 前缀），失败的视角为 None；
不写磁盘。

### `scene_keyframes(scene, visual_prompt=None, anchor_image_b64=None, seed=None, size=None, max_retries=2) -> dict`

- 输入：场景 dict；可选英文提示词（None 时现场生成）；可选 base64 锚点图
  （给了就跳过 wide 的 txt2img）；`seed` 仅本地后端生效；`size` 如
  `"1280*720"`。
- 输出：`{"wide": b64|None, "closeup": b64|None, "mood": b64|None}`；
  wide 失败时 closeup / mood 一并跳过。
- 副作用：调用图像生成后端（本地 GPU 或云端 API）。
- 模型：本地 Z-Image/SDXL（GPU）或云端 DashScope，取决于部署 settings。

### `character_three_view(character, visual_prompt=None, reference_image_b64=None, seed=None, size=None, max_retries=2) -> dict`

- 输入：角色 dict；可选提示词 / 参考图（给了就当 front 锚点，只生成
  side / back）。
- 输出：`{"front": b64|None, "side": b64|None, "back": b64|None}`（绿幕底，
  供后续抠像）。
- 副作用：调用出图后端；重试全部失败时底层抛 RuntimeError。
- 模型：同 `scene_keyframes`。

### `character_variation(character, variation_prompt, reference_image_b64=None, size=None) -> Optional[str]`

- 输入：角色 dict；变体的完整英文提示词；可选风格参考图。
- 输出：base64 PNG；失败返回 None。
- 副作用 / 模型：同上。

最小例子（需要 GPU 模型或云端额度，略）：

```python
frames = await scene_keyframes({"location": "学校操场", "time": "黄昏"},
                               size="1280*720")
```

## video —— 动作视频与抽帧

### `action_video(prompt, start_image_b64=None, end_image_b64=None, duration=5.0, provider="dashscope", greenscreen=False) -> Optional[str]`（async）

- 输入：动作描述；可选首尾关键帧（base64 PNG）；时长（秒）；
  `provider` 为 `"dashscope"`（云端 wan2.5，付费）/ `"happyhorse"`（云端
  试用额度）/ `"local_wan"`（本地 28GB+ VRAM）/ `"svd"`（本地 8GB）；
  `greenscreen=True` 时提示词追加绿幕背景指令，产物可直接交给
  `key_greenscreen`。
- 输出：本地视频文件路径；失败返回 None。
- 副作用：调用视频生成后端，在缓存目录写视频文件。
- 模型：云端 DashScope VideoSynthesis 或本地 wan2.1 / SVD。

### `extract_frames(video_path, output_dir, fps=30.0, max_frames=300, ffmpeg_path=None) -> list[str]`（sync）

- 输入：源视频路径；帧输出目录（自动创建，已有 `frame_*.png` 先清理）；
  采样率；帧数上限；`ffmpeg_path=None` 时依次找 `FFMPEG_PATH` 环境变量、
  imageio-ffmpeg 自带二进制、系统 PATH。
- 输出：排序后的帧路径列表（`frame_0001.png` …）。
- 副作用：向 output_dir 写 PNG；ffmpeg 缺失或失败抛 RuntimeError。
- 模型：无（只调 ffmpeg 子进程）。

最小例子：

```python
from app.tools import extract_frames
frames = extract_frames("clip.mp4", "out/frames", fps=12.0)  # 需要 ffmpeg
```

## chroma_key —— 抠像（纯 CPU 路径 + SAM2）

幕布颜色从帧边缘自适应采样；只有与画面边缘连通的绿色区域才会变透明，
衣服上的绿块不会被误抠。

### `key_greenscreen(frame_paths: list[str], output_dir: str, threshold: int = 80, softness: int = 20) -> list[str]`

- 输入：帧路径列表（如 `extract_frames` 的输出）；RGBA 输出目录；
  `threshold` 为与幕布色的距离阈值，`softness` 为羽化带宽。
- 输出：写出的 RGBA PNG 路径列表（`seg_0001.png` …，不可读的帧跳过）。
- 副作用：向 output_dir 写 `seg_*.png`。
- 模型：无（纯 numpy/OpenCV，CPU）。

### `chroma_key_rgba_array(rgba_bgr: np.ndarray, threshold=80, softness=20, key_color=(0, 255, 0)) -> np.ndarray`

- 输入：HxWx4 uint8，BGR + alpha 通道顺序（OpenCV 约定）。
- 输出：新的 HxWx4 uint8；颜色通道原样拷贝，alpha 与输入取 min（已有
  alpha 只会变更透明）。边缘不像绿幕时原样返回。
- 副作用 / 模型：无（内存内纯函数）。

### `is_greenscreen_frame(frame_path: str, threshold: int = 80, min_ratio: float = 0.7) -> bool`

- 输入：帧路径；`min_ratio` 为边缘像素中绿幕占比的判定线。
- 输出：bool；读不出图像返回 False。
- 副作用 / 模型：无。

### `segment_person(frame_path, output_path, sam2_model=None, min_area=1000, feather_edges=True, greenscreen=False, threshold=80, softness=20) -> bool`

- 输入：帧路径；输出 RGBA PNG 路径；`sam2_model` 为预加载的 SAM2 句柄
  （None 时从 `model_manager` 懒加载）；`greenscreen=True` 时在 SAM2
  alpha 上再叠一次 chroma key。
- 输出：bool，是否成功写出。
- 副作用：成功时写 RGBA PNG。
- 模型：SAM2（GPU）；模型缺失时返回 False。

最小例子（纯 CPU，可直接跑）：

```python
import numpy as np
from app.tools import chroma_key_rgba_array

frame = np.zeros((48, 48, 4), dtype=np.uint8)
frame[:, :] = (0, 255, 0, 255)              # 绿幕
frame[16:32, 16:32] = (40, 40, 180, 255)    # 中间一个人
out = chroma_key_rgba_array(frame)
assert out[0, 0, 3] == 0 and out[24, 24, 3] == 255
```

## depth —— 深度估计（GPU）

### `estimate_depth(image, scale: float = 50.0, depth_model=None) -> np.ndarray`

- 输入：PIL 图像 / numpy 数组（HxWx3）/ 图像文件路径；`scale` 为深度
  映射的最远米数；`depth_model` 为预加载句柄（需有
  `predict_meters(pil_image, scale=...)`），None 时懒加载。
- 输出：HxW float32 米制深度，数值越大越远。
- 副作用：无（首次懒加载占显存）。
- 模型：Depth Anything V2 Large（GPU）。

最小例子（需要 GPU 模型）：

```python
depth = estimate_depth("scene.png", scale=50.0)  # HxW float32，单位米
```

## detect —— 物件检测（GPU）

### `detect_objects(image, depth_meters=None, scene_type="outdoor", prompt=None, confidence_threshold=0.3, max_objects=32, min_mask_area_px=256) -> DetectResult`

- 输入：图像（PIL / numpy / 路径）；可选米制深度（给每件物体算
  depth_mean/min/max）；`scene_type` 决定默认检测词表；`prompt` 自定义
  检测词列表（地面类名词总会自动追加）。
- 输出：`DetectResult` dataclass。`result.objects` 可直接传给
  `classify_scene` / `split_layers` / `fill_occlusions`；JSON 化用
  `result.to_dict()`。
- 副作用：无（首次懒加载占显存）。
- 模型：GroundingDINO（GPU）+ SAM2（GPU）。

### `DetectResult`

dataclass，字段 `objects`（ObjectAsset 列表）与 `ground_entries`
（地面类候选，供地面重建用）；`to_dict()` 转 JSON 友好 dict（不含
mask / PIL 图像）。

## classify —— 场景类识别（规则 + 可选 LLM）

### `classify_scene(objects: list, llm_call: Optional[Callable] = None) -> str`

- 输入：物件列表（`detect_objects(...).objects`，或任何带 label /
  meta.area_px / depth_mean 属性的对象）；`llm_call` 签名
  `llm_call(objects, scores) -> str`，测试时传假回答即可避开 LLM。
  空列表直接返回 `"unknown"`，不调 LLM。
- 输出：闭集类名之一（见文首）。
- 副作用：无。`llm_call=None` 时可能向本地 llama.cpp 发一次请求
  （30s 超时，失败或答非所问自动退回规则打分最高分）。
- 模型：本地 Qwen2.5-7B（llama.cpp），可选。

### `scene_class_scores(objects: list) -> dict`

- 输入：同上。
- 输出：`{场景类名: 分数}`，覆盖闭集全部 7 个类；命中期望标签加分，
  出现禁忌标签扣分。
- 副作用 / 模型：无（纯函数）。

最小例子（纯函数，可直接跑）：

```python
from types import SimpleNamespace
from app.tools import classify_scene, scene_class_scores

objs = [SimpleNamespace(label="bench", meta={"area_px": 100.0}, depth_mean=5.0),
        SimpleNamespace(label="flower", meta={"area_px": 80.0}, depth_mean=6.0)]
print(scene_class_scores(objs))                       # park 得分最高
print(classify_scene(objs, llm_call=lambda o, s: "乱答"))  # 退回 "park"
```

## layers —— 分层（纯计算）

### `split_layers(image, depth_meters=None, object_assets=None, scene_class=None, feather_px=1, layers=None) -> dict[str, PIL.Image]`

- 输入：场景图；HxW 米制深度（形状必须与图像一致）；物件列表；闭集
  场景类名（None 且传了物件时会现场调 LLM 分类——离线/测试请显式传）；
  边界羽化半径；只导出的层名子集。
- 输出：`{层名: PIL RGBA 图}`，属于该层的像素保留 RGB，其余全透明；
  没有像素的层是全透明图。各层可见像素互斥（重叠时更近的层拿走）。
- 副作用：无。
- 模型：无（`scene_class=None` 且有物件时例外，会现场调 LLM）。

### `layer_masks(height, width, depth_meters=None, object_assets=None, scene_class="unknown") -> dict[str, np.ndarray]`

- 输入：图像尺寸；可选米制深度；物件列表；场景类名（必须显式给，
  未知就传 `"unknown"`）。
- 输出：`{层名: (height, width) bool 数组}`；任一像素最多属于一层。
- 副作用 / 模型：无（纯函数）。

最小例子（纯函数，可直接跑）：

```python
import numpy as np
from types import SimpleNamespace
from app.tools import layer_masks

h, w = 16, 16
depth = np.full((h, w), 8.0, dtype=np.float32)
mask = np.zeros((h, w), dtype=bool); mask[8:, :] = True
grass = SimpleNamespace(label="grass", mask=mask, depth_mean=5.0, meta={})
masks = layer_masks(h, w, depth, [grass], scene_class="park")
assert masks["ground"][12, 0] and not masks["foreground"][12, 0]
```

## perspective —— 透视层距表（纯函数）

相机在 +Z 朝 -Z 看，平面 Z 取负的深度（越负越远）。实测中位数破坏
远→近单调性时把远层再推远，不交换层名；最近层 scale=1，越远越大。

### `perspective_offsets(depth_meters=None, masks=None) -> list[dict]`

- 输入：HxW 米制深度（None 时全部用默认层距）；`masks` 为
  `{层名: HxW bool}`（`layer_masks` 的输出），缺的层用默认层距。
- 输出：dict 列表，固定按 sky → background → midground → ground →
  foreground 顺序；每行含 layer / depthMeters / zOffset / zMin / zMax /
  scale / thicknessM / yawDeg / pitchDeg / shiftXM / shiftYM（后五个是
  纸雕呈现字段，只给 Blender 摆层片用）。
- 副作用 / 模型：无。

### `z_offset_table() -> list[dict]`

- 输入：无。
- 输出：五层默认 Z 偏移表（sky=-20, background=-12, midground=-8,
  ground=-4, foreground=-2），字段同上，Blender 插件的兜底表。
- 副作用 / 模型：无。

最小例子（纯函数，可直接跑）：

```python
from app.tools import perspective_offsets, z_offset_table

rows = perspective_offsets()            # 全部用默认层距
assert rows[-1]["layer"] == "foreground" and rows[-1]["scale"] == 1.0
table = z_offset_table()                # Blender 插件兜底表
```

## inpaint —— 遮挡补全（LaMa，可注入假函数）

### `fill_occlusions(image, layer_imgs, depth_meters=None, object_assets=None, scene_class=None, inpaint_fn=None, reveal_band_px=None) -> dict[str, PIL.Image]`

- 输入：场景原图；`split_layers` 的输出 `{层名: RGBA 图}`；可选深度 /
  物件 / 场景类名；`inpaint_fn` 签名
  `inpaint_fn(rgb_image, mask_image, prompt) -> PIL Image`（mask 白色=
  待修复），None 时用本地 LaMa；`reveal_band_px` 为轮廓窄带宽度，None
  时约为图宽 2.5%。
- 输出：`{层名: RGBA 图}`，与输入同键。可见像素保持互斥，只补轮廓
  窄带和全透明洞（只补到最远层）；近层（foreground）不被补全。
- 副作用：无。
- 模型：LaMa（GPU），仅当 `inpaint_fn=None` 时。

### `inpaint_image(base_image, mask_image, prompt="occluded background") -> PIL.Image`

- 输入：原图（至少 128x128）；mask 图（L 模式 255=待修复，或 RGBA 用
  alpha）；`prompt` 仅为兼容旧调用保留（LaMa 是盲修复，忽略它）。
- 输出：修复后的 PIL RGB 图，尺寸与输入一致。
- 副作用：无（首次懒加载占显存）。mask 为空或图小于 128px 抛
  ValueError。
- 模型：LaMa big-lama（GPU）。

最小例子（注入假 inpaint_fn，避开 GPU 模型）：

```python
from app.tools import split_layers, fill_occlusions

layers = split_layers(image, depth, object_assets=[], scene_class="park")
filled = fill_occlusions(image, layers, depth,
                         scene_class="park",
                         inpaint_fn=lambda img, mask, prompt: img)
```

## archive —— 归档（落盘 + GPU 模型链）

### `ensure_depth_layers(project_dir, scene_id=None) -> list[str]`

- 输入：项目目录（需含 `scenes/**/wide.png`）；可选场景 ID。
- 输出：写出的 PNG 文件名列表（如 `["sky.png", "background.png", ...]`）；
  幂等，缓存命中时返回已有文件列表。
- 副作用：向 `<project_dir>/layers/` 写分层 PNG、`_perspective.json`、
  `_fill.json`。流程为 深度估计 → 物件检测 → 场景分类 → 归层 → LaMa
  补全；任何一步失败只记日志、返回已写出的文件名，不抛异常。
- 模型：Depth Anything V2 + GroundingDINO + SAM2 + LaMa（GPU），任一
  失败自动降级。

### `build_shot_archive(project_id, shot_id, workspace_dir=None, output_path=None, scene_id=None, lighting_preset=None, camera_path=None, characters_override=None) -> dict`

- 输入：项目 / 分镜 ID；`workspace_dir=None` 时用部署默认工作区；
  `output_path=None` 时写到 `<项目>/archives/<pid>_<shot>_archive.zip`；
  可选场景 ID、灯光预设、相机关键帧列表（`camera_path()` 的输出）、
  角色覆盖列表。
- 输出：dict（zipPath / fileName / fileSize / manifest / fileCount /
  projectId / shotId）。
- 副作用：写 ZIP；必要时先跑 `ensure_depth_layers`（动用 GPU 模型）；
  项目目录不存在抛 FileNotFoundError。
- 模型：间接使用深度 / 检测 / SAM2 / LaMa。

## render —— 相机路径与 Blender 渲染

### `camera_path(movement: str, shot_size: str, duration: float) -> list[dict]`（sync 纯函数）

- 输入：运镜枚举字符串（如 `"Static"` / `"Dolly In"` / `"Pan Right"`，
  完整枚举见 `app.services.shot_generator.CameraMovement`）；景别枚举
  （如 `"Wide Shot"` / `"Medium Shot"`）；时长（秒）。
- 输出：关键帧 dict 列表（起止两帧；Static 只有一帧），每项
  `{time, position: [x,y,z], target: [x,y,z], fov}`，可直接写入 shot
  archive 的 manifest.cameraPath。
- 副作用 / 模型：无。

### `render_shots(project_id, shot_ids, workspace_dir=None, samples=32, resolution=(1920, 1080), device="GPU", fps=24, lighting_preset=None, timeout_seconds=1800) -> dict`

- 输入：项目 ID；分镜 ID 列表（每个需已有
  `<项目>/archives/<pid>_<shot>_archive.zip`，即 `build_shot_archive`
  的产物，缺归档的分镜记 failed、其余继续）；工作区根目录；Cycles
  采样数；分辨率；`device` 为 `"GPU" / "CPU"`；帧率；可选灯光预设覆盖；
  子进程超时。
- 输出：dict（results / totalSucceeded / totalFailed /
  blenderAvailable / outputDir / error）。Blender 不存在时
  `blenderAvailable=False` 且 results 为空——不抛异常。
- 副作用：向 `<项目>/renders/` 写 `<shot_id>.mp4` 和
  `render_queue_results.json`；启动无头 Blender 子进程。
- 模型：无（需要本机装有 Blender 或配置 `BLENDER_EXECUTABLE`）。

最小例子（`camera_path` 纯函数可直接跑）：

```python
from app.tools import camera_path

keys = camera_path("Dolly In", "Medium Shot", 4.0)
assert keys[0]["time"] == 0.0 and len(keys) == 2
```
