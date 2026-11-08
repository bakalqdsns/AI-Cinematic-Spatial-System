# 系统说明：每个部分是干什么的、依赖什么

这份文档讲《纸间行》2.5D 纸雕动画系统的整体结构和依赖关系。
`README.md` 讲 `app.tools` 每个工具的函数签名；这份讲「这些东西分别有什么用、跑起来需要哪些东西」。

## 一句话总览

```
剧本文本
  → 解析 / 分镜（LLM）
  → 场景出图 + 人物三视图（Z-Image）
  → 动作视频（MiniMax，绿幕）
  → 抽帧（ffmpeg）→ 抠像（色度 + SAM2）→ 帧稳定
  → 深度（Depth Anything）+ 物件检测（GroundingDINO + SAM2）
  → 场景分类 → 分层 → 遮挡补全（LaMa）
  → 归档 ZIP（manifest + 层片 + 人物帧）
  → Blender 搭建渲染（Cycles）
  → 成片 mp4
```

## 依赖总表

### 硬件

| 依赖 | 用途 | 没有会怎样 |
|---|---|---|
| NVIDIA GPU（本机 RTX 4060 Ti 16GB） | 深度、检测、SAM2、LaMa、本地出图、本地视频 | 本地通路全不可用，只能走云端 API 或 ComfyUI 远程 |
| 系统内存 ~32GB | 模型 offload、Blender、视频帧缓存 | 大模型加载失败或极慢 |

### 外部进程（都要先启动）

| 进程 | 地址 / 路径 | 干什么 |
|---|---|---|
| FastAPI 后端 | `127.0.0.1:8000` | 所有 HTTP 接口。`backend/.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000` |
| ComfyUI | `127.0.0.1:8188` | Z-Image 出图、MiniMax 绿幕视频（`local_image_backend=comfyui` / `video_provider=comfyui` 时） |
| llama-server | `localhost:8080` | 本地 Qwen2.5-7B：剧本解析、提示词、场景分类 |
| Blender | `BLENDER_EXECUTABLE` 指定 | 层片搭建和 Cycles 渲染。后端子进程方式调用，无需常驻 |

### 模型（首次用才懒加载）

| 模型 | 缓存位置 | 用在哪 |
|---|---|---|
| Depth-Anything-V2-Large | `backend/.cache/huggingface/` | 场景深度图，分层和地面拟合的输入 |
| GroundingDINO-base | 同上 | 按词表检测场景物件（框） |
| SAM2（vit_l，`sam2.1_l.pt`） | `backend/.cache/` | 检测框 → 像素 mask；人物精修 |
| LaMa（big-lama.pt） | `backend/.cache/lama/` | 分层遮挡补全、通用修复 |
| Z-Image-Turbo | HuggingFace 缓存 | Diffusers 本地出图通路 |
| Z-Image（DiffSynth 格式） | `F:\zimage-lora\models\Z-Image` | `zimage_lora` 场景出图通路 |
| DiffSynth-Studio 代码 | `F:\zimage-lora\DiffSynth-Studio` | 上一条通路的 pipeline 实现 |
| MiniMax H3 工作流 | ComfyUI 端 | 绿幕动作视频（约 3 分钟 / 5 秒） |
| Qwen2.5-7B Q4_K_M GGUF | `backend/llmserver/` | llama-server 加载的本地 LLM |

### 目录

| 目录 | 内容 |
|---|---|
| `backend/.workspace/projects/<项目id>/` | 项目全部资产：scenes/（场景图）、characters/（三视图）、motions/（抠好的人物帧）、layers/（五层 PNG + `_perspective.json`）、archives/（Blender ZIP）、renders/（成片） |
| `backend/.cache/comfy/` | ComfyUI 出的图和视频 |
| `backend/.cache/motion/` | 抽帧和抠像的中间产物 |
| `backend/test_outputs/` | 端到端测试产物（不入库） |

## 链路每个阶段

### 1. 剧本解析与分镜（`app.tools.script`）

输入一段剧本文本，产出结构化剧本（人物、场景、段落）和分镜表（景别、运镜、动作提示词）。

- 依赖：llama-server（本地 LLM）；不可用时退回启发式解析，不会失败。
- 不需要 GPU。

### 2. 视觉提示词（`app.tools.prompts`）

把「白衣少女，16 岁」这种描述扩写成出图用的英文提示词。

- 依赖：llama-server；可降级。
- 场景提示词和人物提示词是两条独立入口。

### 3. 出图（`app.tools.images`）

三条本地通路，由 `settings.local_image_backend` 选择：

| 后端 | 走法 | 依赖 |
|---|---|---|
| `comfyui` | POST 工作流到 ComfyUI | ComfyUI 进程 + 其模型目录 |
| `diffusers` | 进程内 Z-Image-Turbo | GPU 显存 |
| `zimage_lora` | 进程内 DiffSynth ZImagePipeline | `F:\zimage-lora\models\Z-Image` + `F:\zimage-lora\DiffSynth-Studio`，GPU |

- 场景图（`scene_keyframes`）：wide/closeup/mood 三张，空场景不要人。`zimage_lora` 通路会自动追加纸雕 HD-2D 风格后缀和负面词（搬自 `F:\zimage-lora\gen_zhijing_scenes.py`）。
- 人物图（`character_three_view` / `character_variation`）：**必须带绿幕**（平整 #00FF00 cyclorama 后缀），供下一步动作视频当参考帧。

### 4. 动作视频与抽帧（`app.tools.video`）

- `action_video`：人物参考帧 + 动作提示词 → MiniMax 绿幕视频。ComfyUI 通路固定绿幕；抽帧保持宽高比（最长边 1024，不再压扁）。
- 依赖：ComfyUI（本地）或 DashScope（云端）；ffmpeg 或 imageio-ffmpeg 抽帧。

### 5. 抠像与帧稳定（`app.tools.chroma_key`）

把绿幕视频帧变成透明背景的人物 PNG：

1. 整段视频先按多帧绿色像素的 Cr/Cb 中位数锁定同一幕布色（幕布变暗也不漂移）；
2. 每帧只挖「和画面边缘连通」的幕布色，人物身上的绿衣服不连边就保留；
3. 可选 SAM2 精修边缘（取更透明的一侧，不会涂回去）；
4. `stabilize_frames`：脚底锚点对齐画布固定位置、身高归一化到全序列中位数——贴图里的人原地踏步，移动全交给 Blender 平面。

- 色度路径纯 CPU；SAM2 精修需要 GPU。
- 判定 `is_greenscreen_frame` 用边框采样，(77,148,93) 这种暗绿幕布也认。

### 6. 深度与物件检测（`app.tools.depth` / `app.tools.detect`）

- `estimate_depth`：Depth Anything V2，输出已翻成「0=近、1=远」再乘 50 米。
- `detect_objects`：GroundingDINO 按场景词表出框 → SAM2 出 mask → Canny 边缘吸附 → 每个物件带 label/mask/深度均值/层归属。
- 都依赖 GPU 和 HuggingFace 缓存。

### 7. 场景分类与分层（`app.tools.classify` / `app.tools.layers` / `app.tools.perspective`）

- `classify_scene`：先按中英文别名匹配表打分，再让 LLM 从闭集（school_playground / park / street / courtyard / indoor_room / nature / unknown）里选；LLM 乱答就用最高分。
- `split_layers`：物件按匹配表进层，表里没有的和剩余像素按各层深度中位数就近归层；每个像素只属于一层（近层拿走重叠处）。
- `perspective_offsets`：每层的深度、Z 位置（负深度）、缩放（近 1 倍，远层按相机距离放大）、厚度、偏航、错位，写进 `layers/_perspective.json`。
- 纯计算，不需要 GPU（LLM 仲裁可选）。

### 8. 遮挡补全（`app.tools.inpaint`）

近层挡住的区域用 LaMa 补进远层，只补轮廓窄带和全透明洞，近层自己不动。运镜/错位时露出来的是补出来的内容而不是空白。

- 依赖 LaMa（GPU）；测试可注入假 `inpaint_fn`。

### 9. 归档与渲染（`app.tools.archive` / `app.tools.render`）

- `build_shot_archive`：把层片、人物帧、相机路径、灯光打成 ZIP + `manifest.json`。人物自动落到前景与地面之间的深度、按真实身高缩放、带行走轨迹（walkFromX/walkToX）。
- `render_shots`：无头 Blender 子进程跑 Cycles。层片有厚度、暖纸板切边、轻微偏航和错位；人物平面只沿 X 轴 LINEAR 移动（严格平行画面）。
- 依赖：Blender 可执行文件；渲染用 GPU（Cycles）。

## 设置项速查（`POST /api/aicss/settings`）

| 字段 | 可选值 | 作用 |
|---|---|---|
| `image_mode` | `local` / `cloud` | 出图走本地还是云端 |
| `local_image_backend` | `comfyui` / `diffusers` / `zimage_lora` | 本地出图通路 |
| `video_mode` / `video_provider` | `local` + `comfyui` 等 | 动作视频通路 |
| `comfyui_base_url` | 默认 `http://127.0.0.1:8188` | ComfyUI 地址 |
| `zimage_lora_model_dir` | 默认 `F:\zimage-lora\models\Z-Image` | Z-Image 模型目录 |
| `zimage_lora_diffsynth_dir` | 默认 `F:\zimage-lora\DiffSynth-Studio` | DiffSynth 代码目录 |
| `model_mode` | `local` / `cloud` | LLM/VLM 走本地 llama-server 还是云端 |

环境变量 `BLENDER_EXECUTABLE` 指到 Blender 可执行文件（渲染必须）。

## 常见排错

- **人物是不透明卡片**：动作视频没出绿幕，或抠像没跑。看 `motions/.../frame_0001.png` 是否有 alpha。
- **人像被压扁**：旧版抽帧写死正方形，已修；确认抽帧代码带 `force_original_aspect_ratio=decrease`。
- **绿幕判不出来**：边框不是绿色系时 `is_greenscreen_frame` 为 False，色度不跑，只剩 SAM2。
- **人物在画面里漂移/忽大忽小**：确认走的是稳定化后的帧（抠像流水线已内置 stabilize）。
- **zimage_lora 报 RuntimeError**：检查 `zimage_lora_diffsynth_dir` 指向 DiffSynth-Studio 仓库根目录、模型目录里 transformer/text_encoder/vae 齐全。
- **渲染找不到 Blender**：设 `BLENDER_EXECUTABLE` 后重启后端。
