# AI Cinematic Spatial System (AICSS) — 详细技术文档

> 本文档详细记录 AICSS 系统中**已完全实施**的各功能模块，包括数据模型、API 协议、前后端实现细节、目录结构及调用流程。
>
> 适用版本：v2
> 最后更新：2026-07-21

---

## 目录

1. [系统架构总览](#1-系统架构总览)
2. [模块一：自动化剧本拆解](#2-模块一自动化剧本拆解)
3. [模块二：分镜生成](#3-模块二分镜生成)
4. [模块三：角色资产生成](#4-模块三角色资产生成)
5. [模块四：动作序列生成](#5-模块四动作序列生成)
6. [模块五：项目存储与归档](#6-模块五项目存储与归档)
7. [数据持久化结构](#7-数据持久化结构)
8. [API 完整索引](#8-api-完整索引)
9. [前端组件说明](#9-前端组件说明)
10. [启动与配置](#10-启动与配置)

---

## 1. 系统架构总览

### 1.1 技术栈

| 层级 | 技术选型 |
|------|----------|
| 后端框架 | FastAPI（Python 3.11+） |
| 前端框架 | React 18 + TypeScript + Vite |
| 3D 渲染 | Three.js + @react-three/fiber + @react-three/drei |
| 深度学习 | PyTorch（本地模型推理） |
| AI 生成 | DashScope（阿里云）：qwen3-8b、wanx-v1、wanx-v1-imageedit、wan2.7-i2v |
| 本地模型 | DepthAnything-V2-Large、Grounding-DINO-base、SAM2 (vit_l)、Qwen3-VL-4B-Instruct |
| 状态管理 | Zustand（前端） |
| HTTP 客户端 | Axios（前端）+ FastAPI（后端） |
| 工作空间 | 本地文件系统（`backend/.workspace/projects/`） |

### 1.2 后端目录结构

```
backend/
├── app/
│   ├── main.py                          # FastAPI 入口，路由挂载，模型启动加载
│   ├── config.py                         # 全局配置（设备/模型路径/工作空间）
│   ├── endpoints.py                      # 核心分析 API（analyze/depth/segment/layers…）
│   ├── endpoints_projects.py             # 项目管理 API
│   ├── endpoints_sequence.py             # 序列分析 API
│   ├── endpoints_shots.py                # 镜头管理 API（v2）
│   ├── endpoints_script.py               # 剧本/分镜/动作 API（v2）
│   ├── endpoints_mesh.py                # 3D mesh 导出 API（v2.1）
│   ├── services/
│   │   ├── script_parser.py             # 剧本解析服务（两段式 LLM pipeline）
│   │   ├── shot_generator.py            # 分镜生成服务
│   │   ├── character_generator.py        # 角色资产生成
│   │   ├── motion_extractor.py          # 动作视频→帧→抠像 pipeline
│   │   ├── project_store.py             # 持久化存储服务
│   │   ├── project_store_mesh.py       # 3D mesh 持久化服务（v2.1）
│   │   └── mesh_exporter.py            # Blender Headless 导出服务（v2.1）
│   ├── models/
│   │   ├── model_manager.py             # 模型加载器（单例）
│   │   ├── depth_loader.py              # DepthAnything-V2-Large
│   │   ├── sam2_loader.py               # SAM2 自动分割 + 边缘贴合
│   │   ├── grounding_dino_loader.py     # Grounding-DINO 零样本检测
│   │   └── qwen3vl_loader.py            # Qwen3-VL-4B-Instruct
│   └── utils/
│       ├── spatial_utils.py             # 空间分层、遮挡关系推断
│       ├── inpaint_utils.py             # WanEdit 图像修复 / LaMa 本地修复
│       ├── lama_loader.py               # LaMa 本地图像修复模型
│       └── paper_diorama.py             # 纸片风格纹理生成
└── logs/                                # 运行日志（自动创建）
```

### 1.3 前端目录结构

```
frontend/src/
├── components/
│   ├── ScriptEditor.tsx                 # 剧本编辑器（4-tab UI）
│   ├── Viewer3D.tsx                    # Three.js 3D 查看器
│   ├── ExportPanel.tsx                 # 导出面板
│   ├── DepthSplitPanel.tsx             # 深度分层面板
│   └── ...
├── services/
│   ├── scriptService.ts                # 剧本 API 客户端
│   ├── aicssService.ts                 # AICSS 分析 API 客户端
│   └── sequenceService.ts              # 序列 API 客户端
├── store/
│   ├── useAppStore.ts                  # 全局状态（API key 等）
│   ├── useScriptStore.ts               # 剧本/分镜状态（Zustand）
│   └── useProjectStore.ts              # 项目状态
├── types/
│   └── script.ts                       # TypeScript 类型定义（与后端 dataclass 对应）
└── utils/
    └── depthSplit.ts                   # 前端深度分层工具
```

---

## 2. 模块一：自动化剧本拆解

### 2.1 概述

将用户输入的原始剧本文本，通过两段式 LLM pipeline 转换为结构化的 `ScriptData`，包含角色、场景、故事段落三大要素。支持中文、英文、日文三种语言。

### 2.2 数据模型

**文件：** `backend/app/services/script_parser.py`（L1-151）

```python
# 语言枚举
class ScriptLanguage(str, Enum):
    CHINESE = "chinese"
    ENGLISH = "english"
    JAPANESE = "japanese"

# 角色
@dataclass
class Character:
    id: str               # 如 "char-1"
    name: str             # 角色名称
    gender: str           # 性别
    age: str              # 年龄
    personality: str      # 性格描述
    visual_prompt: str    # AI 视觉生成提示词（可后续用于角色图生成）
    reference_image: Optional[str]  # base64 或 URL

# 场景
@dataclass
class Scene:
    id: str               # 如 "scene-1"
    location: str         # 地点（"咖啡馆"、"街道"等）
    time: str             # 时间：Day/Night/Dawn/Dusk/Morning/Evening
    atmosphere: str        # 氛围（"紧张"、"温馨"、"神秘"）

# 故事段落
@dataclass
class StoryParagraph:
    id: str               # 如 "para-1"
    text: str             # 原始段落文本
    scene_ref_id: str     # 所属场景 ID

# 完整剧本数据
@dataclass
class ScriptData:
    title: str
    genre: str             # 题材类型
    logline: str           # 一句话简介
    characters: list[Character]
    scenes: list[Scene]
    story_paragraphs: list[StoryParagraph]
    language: ScriptLanguage
```

### 2.3 两段式 Pipeline

#### Pass 1：规范化（Normalize）

**函数：** `normalize_script()`（L304-350）

```
原始剧本文本  →  LLM (qwen3-8b)  →  标准格式剧本
```

- **系统提示词**：指示模型将原始文本重写为标准电影剧本格式（INT./EXT. 场景标题、角色对白前缀、动作描述独立成行）
- **模型**：DashScope `qwen3-8b`，`temperature=0.3`，`max_tokens=4096`
- **Fallback**：若 API 调用失败，返回原文按行拆分后的最小化清理版本

#### Pass 2：结构化解析（Parse）

**函数：** `parse_script()`（L353-409）

```
规范化剧本  →  LLM (qwen3-8b, JSON 输出)  →  ScriptData dataclass
```

- **系统提示词**：要求模型输出严格 JSON，包含 title/genre/logline/characters/scenes/story_paragraphs
- **Markdown 过滤**：自动去除 ` ```json ` 等代码块标记
- **Fallback**：当 LLM 不可用时，使用正则表达式从规范化文本中启发式提取：
  - 场景：从 `INT./EXT.` 标题中提取
  - 角色：从对话行 `"角色名："` 模式中提取

### 2.4 便捷函数

```python
# 完整两段式 pipeline
await process_script(raw_text, language, dashscope_api_key)
# 返回: (normalized_text: str, script_data: ScriptData)

# 序列化（用于 JSON 传输）
serialize_script_data(script: ScriptData) -> dict
deserialize_script_data(data: dict) -> ScriptData
```

---

## 3. 模块二：分镜生成

### 3.1 概述

基于已解析的 `ScriptData`，通过 LLM 生成每场 6-8 个分镜，每个分镜包含镜头号、景别、运镜、动作描述、角色列表、预估时长，以及英文视觉提示词。

**文件：** `backend/app/services/shot_generator.py`

### 3.2 数据模型

**景别枚举（12 种）：**

```python
class ShotSize(str, Enum):
    EXTREME_CLOSE_UP = "Extreme Close-up"   # 大特写
    CLOSE_UP = "Close-up"                   # 特写
    MEDIUM_CLOSE_UP = "Medium Close-up"     # 中特写
    MEDIUM_SHOT = "Medium Shot"             # 中景
    MEDIUM_WIDE = "Medium Wide"             # 中全景
    WIDE_SHOT = "Wide Shot"                # 全景
    EXTREME_WIDE = "Extreme Wide"           # 大远景
    OVER_THE_SHOULDER = "Over-the-Shoulder"  # 过肩镜头
    POV = "POV"                            # 主观镜头
    TWO_SHOT = "Two-Shot"                  # 双人镜头
```

**运镜枚举（13 种）：**

```python
class CameraMovement(str, Enum):
    DOLLY_IN = "Dolly In"        # 推进
    DOLLY_OUT = "Dolly Out"      # 拉出
    PAN_RIGHT = "Pan Right"      # 右摇
    PAN_LEFT = "Pan Left"        # 左摇
    TILT_UP = "Tilt Up"          # 上摇
    TILT_DOWN = "Tilt Down"      # 下摇
    STATIC = "Static"            # 静止
    HANDHELD = "Handheld"        # 手持
    TRACKING = "Tracking"         # 跟踪
    CRANE_UP = "Crane Up"        # 升臂上移
    CRANE_DOWN = "Crane Down"    # 升臂下移
    ZOOM_IN = "Zoom In"          # 变焦推进
    ZOOM_OUT = "Zoom Out"        # 变焦拉出
```

**分镜数据类：**

```python
@dataclass
class Shot:
    id: str
    scene_id: str                # 所属场景 ID
    shot_number: int             # 镜头编号
    action_summary: str          # 动作描述
    dialogue: str                # 对白（可为空）
    camera_movement: CameraMovement
    shot_size: ShotSize
    characters: list[str]        # 角色 ID 列表
    visual_prompts: VisualPrompts
    duration_seconds: float      # 预估时长（默认 3.0s）
    keyframe_start_prompt: str   # 起始帧英文提示词
    keyframe_end_prompt: str     # 结束帧英文提示词

@dataclass
class VisualPrompts:
    scene_prompt: str            # 英文场景描述
    action_prompt: str          # 英文人物动作描述
    camera_prompt: str           # 相机运动描述
    transition_prompt: str       # 转场描述
```

### 3.3 核心函数

**分镜生成：**

```python
async def generate_shots(
    script_data: ScriptData,
    shots_per_scene: int = 6,   # 每场最少分镜数
    language: Optional[ScriptLanguage] = None,
) -> list[Shot]
```

- **模型**：DashScope `qwen3-8b`，`temperature=0.4`，`max_tokens=8192`
- **提示词构建**：`_build_shot_prompt()` 将场景列表、角色列表、故事段落拼接为用户提示词
- **Fallback**：当 LLM 不可用时，每 2 个故事段落生成一个分镜，循环使用 4 种景别

**场景转场生成：**

```python
def generate_scene_transitions(shots: list[Shot]) -> list[SceneTransition]
```

- 遍历相邻分镜，当 `scene_id` 发生变化时生成一个 `SceneTransition`
- 转场类型默认为 "dissolve"（叠化）
- `transition_prompt` 由前一镜场景提示词 + 转场描述 + 后一镜场景提示词拼接

**角色动作序列生成：**

```python
def generate_character_action_sequences(
    shots: list[Shot],
    characters: list[Character],
) -> list[CharacterActionSequence]
```

- 为每个角色汇总其出现的所有分镜中的动作提示词
- 生成 0-1 范围的强度曲线（oscillating energy curve）
- 每角色最多取前 5 个分镜的动作描述，用 "then" 连接

### 3.4 字符串解析容错

`_parse_camera()` 和 `_parse_shot_size()` 支持大小写不敏感和模糊匹配：
- 输入 `"wide shot"` → 匹配 `ShotSize.WIDE_SHOT`
- 输入 `"DOLLYIN"` → 匹配 `CameraMovement.DOLLY_IN`
- 无法匹配时默认 `Static` / `Medium Shot`

---

## 4. 模块三：角色资产生成

### 4.1 概述

基于角色信息生成角色视觉提示词、基础参考图，以及正面/侧面/背面三视图，确保角色在后续镜头中保持视觉一致性。

**文件：** `backend/app/services/character_generator.py`

### 4.2 数据模型

```python
@dataclass
class CharacterAsset:
    character_id: str
    visual_prompt: str              # AI 视觉提示词
    reference_image: str            # 基础参考图（base64）
    three_view_images: dict         # {"front": base64, "side": base64, "back": base64}
    variations: list               # 后续服装/表情变体

@dataclass
class CharacterVariation:
    id: str
    name: str
    visual_prompt: str
    image: Optional[str]            # base64
```

### 4.3 核心函数

| 函数 | 功能 | 调用模型 |
|------|------|----------|
| `generate_visual_prompt(char, genre, language)` | 从角色描述生成英文视觉提示词 | `qwen3-8b` |
| `generate_character_reference(char, prompt)` | 生成基础参考图 | `wanx-v1` |
| `generate_character_three_view(char, prompt)` | 生成正面/侧面/背面三视图 | `wanx-v1`（×3） |
| `generate_character_variation(char, variation_prompt, ref)` | 服装变体生成（以参考图为条件） | `wanx-v1-imageedit` |

### 4.4 三视图生成流程

```
角色描述 + visual_prompt
        │
        ├──→ generate_character_reference() ──→ reference_image (wanx-v1)
        │
        └──→ generate_character_three_view()
                    │
                    ├── front prompt ──→ wanx-v1 ──→ front image
                    ├── side prompt  ──→ wanx-v1 ──→ side image
                    └── back prompt  ──→ wanx-v1 ──→ back image
```

### 4.5 图像编码

所有生成的图像以 **base64 data URL** 形式返回：
- `data:image/png;base64,<base64_string>`
- 若源为 URL，先下载并转换为 base64（`_url_to_base64()`）

---

## 5. 模块四：动作序列生成

### 5.1 概述

将分镜中的角色动作提示词转化为绿幕动作视频 → ffmpeg 抽帧 → SAM2 人物抠像 → 透明通道 PNG 序列帧。

**文件：** `backend/app/services/motion_extractor.py`

### 5.2 数据模型

```python
@dataclass
class MotionSequence:
    shot_id: str
    character_id: str
    character_name: str
    action_description: str
    video_path: Optional[str]       # 生成的视频文件路径
    frame_count: int               # 提取的帧数
    segmented_dir: Optional[str]    # 抠像后 PNG 序列所在目录
    status: str                    # "pending" | "generating" | "done" | "error"

@dataclass
class SegmentedFrame:
    frame_index: int
    original_path: str             # 原始帧路径
    segmented_path: Optional[str]  # 抠像后路径（命名：{角色名}_{动作名}_{帧号:04d}.png）
    character_name: str
    action_name: str
```

### 5.3 完整 Pipeline

```
generate_motion_sequence()
        │
        ├── ① generate_action_video()
        │       wan2.7-i2v 异步任务（最长等待 5 分钟）
        │       start_image / end_image 作为首尾关键帧
        │       → 返回 video_path
        │
        ├── ② extract_frames_from_video()
        │       ffmpeg subprocess 调用
        │       参数：fps=30, scale=1024:1024, max_frames=300
        │       → 返回 frame_paths: list[str]
        │
        └── ③ segment_frames_sequence()
                SAM2 predict_automatic_masks()
                选取最大面积 mask（heuristic：近似人像）
                → 透明通道 PNG，命名：{角色名}_{动作名}_{帧号:04d}.png
```

### 5.4 各环节说明

**视频生成（wan2.7-i2v）：**

- 异步任务模式：创建任务 → 轮询（每 10 秒，最长 5 分钟）
- 支持 `start_image`（起始帧 base64）和 `end_image`（结束帧 base64）作为关键帧条件
- 若 ffmpeg 不可用，`extract_frames_from_video` 会返回空列表，不抛出异常

**SAM2 人物分割（`segment_person_from_frame`）：**

- 调用 `sam2.predict_automatic_masks(image_path)` 获取所有候选 mask
- **启发式选择**：按面积降序排列，选取最大 mask 作为人物（不依赖真实人物分类）
- 边缘贴合：`_refine_mask_with_canny()` 将 mask 轮廓贴合到 Canny 边缘（`snap_distance=8px`）
- 输出 RGBA PNG：白色区域为不透明，黑色区域为透明

**帧命名规范：**

```
{角色名_动作名_帧号:04d}.png
例如：LiMing_walking_0001.png
```

### 5.5 注意事项

- **ffmpeg 依赖**：必须在系统 PATH 中可用，否则视频抽帧失败
- **人物选择 heuristic**：使用最大面积 mask，非真实人物检测，可能在复杂场景中选错
- **首尾帧一致性**：当前未实现首尾帧一致性检查

---

## 6. 模块五：项目存储与归档

### 6.1 概述

统一的持久化存储服务，负责所有 ML 产物的落盘、索引管理和目录组织。

**文件：** `backend/app/services/project_store.py`（1064 行，单例模式）

### 6.2 核心设计

| 特性 | 说明 |
|------|------|
| 索引方式 | `manifest.json` 是唯一索引，每次写入原子重写（临时文件 + `os.replace`） |
| 并发安全 | per-project `asyncio.Lock`，避免并发写入冲突 |
| 启动清理 | 启动时删除所有残留 `.tmp` 文件 |
| 工作空间根 | `settings.workspace_dir / "projects"`（默认 `backend/.workspace/projects`） |

### 6.3 v1 目录结构（图像分析类项目）

```
<workspace>/<project_id>/
├── manifest.json                    ← 项目索引（唯一）
├── input/
│   └── original.png                 ← 原始输入图
├── depth/
│   ├── depth_map.png               ← 深度图
│   └── depth_colormap.png          ← 深度伪彩色图
├── masks/
│   ├── objects.json                ← 所有物体元数据
│   └── mask_<id>.png               ← 每个物体的二值 mask
├── layers/
│   ├── layer_assignments.json       ← 分层配置
│   └── layer_<key>.png             ← 每层 RGBA 图层
├── scene/
│   └── scene_graph.json             ← 场景图（物体空间关系）
├── billboards/
│   └── billboard_<id>.png           ← Billboard 贴图
├── multiface/
│   └── <id>_face_<i>.png           ← 六面展开图
├── paper/
│   ├── paper_style_<key>.png       ← 卡通化纹理
│   ├── paper_thickness_<key>.png    ← 厚度图
│   ├── paper_normal_<key>.png       ← 法线图
│   └── paper_outlined_<key>.png    ← 描边图
└── inpaint/
    └── inpaint_<ts>_<hash>.png     ← 修复后图像
```

### 6.4 v2 目录结构（剧本/分镜类项目）

```
<workspace>/<project_id>/
├── manifest.json                    ← 主索引（包含 scriptData / shotList）
├── sequences/
│   └── <sequence_id>.json           ← 序列分析结果
├── shots/
│   ├── shots_manifest.json           ← 镜头索引
│   └── <shot_id>/
│       ├── manifest.json            ← 镜头详情
│       ├── frames/
│       │   ├── 0.json               ← 单帧分析结果
│       │   ├── 0_original.png      ← 原始帧
│       │   └── 0_depth.png         ← 深度图
│       └── artifacts/               ← 镜头级产物
├── characters/
│   ├── <character_id>_front.png    ← 三视图
│   ├── <character_id>_side.png
│   ├── <character_id>_back.png
│   └── <character_id>_variation_<id>.png  ← 变体
├── motions/
│   └── <character_id>_<sequence_id>.json  ← 动作序列
└── meshes/                       ← 3D mesh 导出（v2.1）
    ├── mesh_manifest.json           ← mesh 导出索引
    ├── objects/
    │   └── <object_id>.glb/.fbx   ← 物体级 mesh
    ├── layers/
    │   └── <layer_key>.glb/.fbx  ← 深度层 mesh (foreground/midground/background/sky)
    └── scenes/
        └── <scene_id>.glb/.fbx    ← 完整场景 mesh
```

### 6.5 ProjectStore 公开 API

**项目管理：**

| 方法 | 说明 |
|------|------|
| `create(shot_id, image_bytes, w, h)` | 创建项目，写入原始图，初始化 manifest |
| `save_step(project_id, step, files)` | 写入产物到指定 step 子目录，更新 manifest |
| `load_artifact(project_id, step, filename)` | 读取单个产物（自动识别 JSON/binary） |
| `list_projects()` | 返回所有项目摘要（按 updated_at 降序） |
| `read_manifest(project_id)` | 读取完整 manifest |
| `delete_project(project_id)` | 删除整个项目目录 |
| `append_timeline(project_id, event)` | 追加执行时间线记录 |

**镜头管理（v2）：**

| 方法 | 说明 |
|------|------|
| `create_shot(project_id, shot_id, desc, scene_type)` | 创建镜头目录和 manifest |
| `save_frame(project_id, shot_id, idx, data, orig_bytes, depth_bytes)` | 保存单帧结果 |
| `load_frame(project_id, shot_id, idx)` | 读取单帧 JSON |
| `load_frame_image(project_id, shot_id, idx, kind)` | 读取帧图像（original/depth） |
| `finalize_shot(project_id, shot_id, status)` | 标记镜头完成/失败，重建 frames 列表 |
| `get_shot / list_shots / delete_shot` | 镜头 CRUD |

**剧本/分镜持久化：**

| 方法 | 说明 |
|------|------|
| `save_script_data(project_id, script_data)` | 保存解析后的剧本到 manifest |
| `save_shot_list(project_id, shot_list)` | 保存分镜表到 manifest |
| `save_character_asset(project_id, char_id, type, data)` | 保存角色资产 PNG |
| `add_character_variation(project_id, char_id, var_id, data)` | 追加角色变体 |
| `save_motion_sequence(project_id, char_id, seq_id, data)` | 保存动作序列 JSON |
| `list_character_assets / list_motion_sequences` | 列表查询 |

### 6.6 manifest.json 结构（v1）

```json
{
  "projectId": "20260718_143200_shot-1",
  "shotId": "shot-1",
  "createdAt": "2026-07-18T06:32:00.000Z",
  "updatedAt": "2026-07-18T06:35:12.000Z",
  "imageWidth": 1024,
  "imageHeight": 768,
  "inputHash": "sha256:abc123...",
  "artifacts": {
    "depth": {
      "phase": "depth",
      "files": [{ "name": "depth_map.png", "size": 524288, "sha256": "...", "savedAt": "..." }],
      "savedAt": "..."
    }
  },
  "timeline": [
    { "phase": "depth", "startedAt": "...", "finishedAt": "...", "durationMs": 2340 }
  ],
  "scriptData": { ... },     // v2 扩展
  "shotList": [ ... ]        // v2 扩展
}
```

### 6.7 原子写入机制

```python
def _write_manifest(self, project_id, manifest):
    tmp_path = manifest_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(manifest.to_dict(), ...), encoding="utf-8")
    os.replace(tmp_path, manifest_path)   # Windows 上也是原子 rename
```

---

## 7. 数据持久化结构

### 7.1 快照摘要（ProjectSummary）

用于列表展示，轻量级：

```python
@dataclass
class ProjectSummary:
    project_id: str
    shot_id: str
    created_at: str
    updated_at: str
    image_width: int
    image_height: int
    steps_completed: list[str]   # 已完成的 step 列表
```

### 7.2 时间线（TimelineEvent）

记录每个处理阶段的执行时间：

```python
@dataclass
class TimelineEvent:
    phase: str          # 如 "depth", "segment", "inpaint"
    started_at: str     # ISO 8601
    finished_at: str    # ISO 8601
    duration_ms: int    # 耗时（毫秒）
```

### 7.3 产物文件（ArtifactFile）

每个已保存文件的元数据：

```python
@dataclass
class ArtifactFile:
    name: str           # 文件名
    size: int           # 字节数
    sha256: str         # 内容哈希
    saved_at: str       # ISO 8601
```

---

## 8. API 完整索引

### 8.1 路由挂载（`main.py` L79-84）

```
/api/aicss/*            → endpoints_router（核心分析 API）
/api/aicss/projects/*  → projects_router（项目管理）
/api/aicss/v2/sequences → sequence_router（序列分析）
/api/aicss/v2/.../shots → shots_router（镜头管理）
/api/aicss/v2/scripts/* → script_router（剧本/分镜/动作）
/health                 → 健康检查
```

### 8.2 剧本拆解 API（v2）

**POST** `/api/aicss/v2/scripts/parse`

```json
// Request
{
  "raw_text": "原始剧本文本...",
  "language": "chinese",          // chinese | english | japanese
  "project_id": "optional",
  "dashscope_api_key": "optional"  // 可覆盖全局配置
}
// Response
{
  "normalized_script": "标准化后的剧本文本...",
  "script_data": {
    "title": "...",
    "genre": "...",
    "logline": "...",
    "characters": [...],
    "scenes": [...],
    "story_paragraphs": [...],
    "language": "chinese"
  },
  "project_id": "..."
}
```

**POST** `/api/aicss/v2/scripts/shots`

```json
// Request
{
  "script_data": { ... },         // parse 步骤返回的 script_data
  "shots_per_scene": 6,            // 默认 6
  "language": "chinese",
  "project_id": "optional"
}
// Response
{
  "shots": [ ... ],               // 分镜数组
  "scene_transitions": [ ... ],   // 场景转场
  "character_action_sequences": [ ... ],
  "total_duration_seconds": 124.5,
  "project_id": "..."
}
```

**POST** `/api/aicss/v2/scripts/scene-prompts`

```json
// Request: { "shots": [...] }
// Response: { "scene_prompts": [...], "transition_prompts": [...] }
```

**POST** `/api/aicss/v2/scripts/action-sequences`

```json
// Request: { "shots": [...], "characters": [...], "project_id": "optional" }
// Response: { "sequences": [...] }
```

**POST** `/api/aicss/v2/scripts/visual-prompt`

```json
// Request: { "character_name": "...", "gender": "...", "age": "...", "personality": "..." }
// Response: { "visual_prompt": "..." }
```

### 8.3 角色资产 API（v2）

**POST** `/api/aicss/v2/scripts/characters/generate-three-view`

```json
// Request
{
  "character_id": "char-1",
  "character_name": "李明",
  "character_gender": "男",
  "character_age": "30",
  "character_personality": "冷静内敛",
  "visual_prompt": "optional 视觉提示词",
  "reference_image": "optional base64",
  "project_id": "optional"
}
// Response
{
  "character_id": "char-1",
  "visual_prompt": "AI 生成的英文视觉提示词",
  "three_view_images": { "front": "base64", "side": "base64", "back": "base64" },
  "reference_image": "base64",
  "project_id": "..."
}
```

**POST** `/api/aicss/v2/scripts/characters/generate-variation`

```json
// Request: { "character_id": "...", "variation_prompt": "...", "reference_image": "base64", "project_id": "optional" }
// Response: { "character_id": "...", "variation_id": "var-abc12345", "variation_prompt": "...", "image": "base64" }
```

### 8.4 动作序列 API（v2）

**POST** `/api/aicss/v2/scripts/motion/generate`

```json
// Request
{
  "shot_id": "shot-1",
  "character_id": "char-1",
  "character_name": "李明",
  "action_prompt": "英文角色动作描述",
  "start_image": "optional base64 三视图正面",
  "end_image": "optional base64 三视图背面",
  "duration_seconds": 5.0,
  "project_id": "optional"
}
// Response
{
  "shot_id": "shot-1",
  "character_id": "char-1",
  "status": "done",
  "video_path": "backend/.cache/videos/xxx.mp4",
  "frame_count": 150,
  "segmented_frames": [
    { "frame_index": 0, "path": "...", "filename": "LiMing_walking_0001.png" },
    ...
  ],
  "project_id": "..."
}
```

**POST** `/api/aicss/v2/scripts/motion/extract-frames`

```json
// Request: { "video_path": "...", "output_dir": "optional", "fps": 30.0, "max_frames": 300 }
// Response: { "frame_paths": [...], "frame_count": 150 }
```

**POST** `/api/aicss/v2/scripts/motion/segment`

```json
// Request: { "frame_paths": [...], "character_name": "...", "action_name": "...", "output_dir": "optional" }
// Response: { "segmented_frames": [...] }
```

### 8.5 项目管理 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/aicss/projects` | 创建项目（multipart/form-data） |
| POST | `/api/aicss/projects/json` | 创建项目（base64 body） |
| GET | `/api/aicss/projects` | 列出所有项目 |
| GET | `/api/aicss/projects/{pid}/manifest` | 读取 manifest |
| GET | `/api/aicss/projects/{pid}/artifacts/{step}/{filename}` | 下载产物文件 |
| POST | `/api/aicss/projects/{pid}/checkpoint` | 记录断点 |
| DELETE | `/api/aicss/projects/{pid}` | 删除项目 |

### 8.6 镜头管理 API（v2）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/aicss/v2/projects/{pid}/shots` | 创建镜头 |
| GET | `/api/aicss/v2/projects/{pid}/shots` | 列出镜头 |
| GET | `/api/aicss/v2/projects/{pid}/shots/{sid}` | 获取镜头详情 |
| DELETE | `/api/aicss/v2/projects/{pid}/shots/{sid}` | 删除镜头 |
| GET | `/api/aicss/v2/projects/{pid}/shots/{sid}/frames/{idx}` | 获取单帧结果 |
| GET | `/api/aicss/v2/projects/{pid}/shots/{sid}/frames/{idx}/image` | 获取帧图像（PNG binary） |

### 8.7 核心分析 API（图像类）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/aicss/analyze` | 完整 pipeline（深度→VLM→DINO→SAM2→分层→场景图） |
| POST | `/api/aicss/depth` | 仅深度预测 |
| POST | `/api/aicss/segment` | SAM2 分割 |
| POST | `/api/aicss/layers` | 深度分层 |
| POST | `/api/aicss/scene-graph` | 空间关系推理 |
| POST | `/api/aicss/billboard` | Billboard 贴图生成 |
| POST | `/api/aicss/multiface` | 六面展开图生成 |
| POST | `/api/aicss/inpaint` | 图像修复（repair/restyle） |
| POST | `/api/aicss/paper-style` | 纸片风格 |
| POST | `/api/aicss/paper-diorama` | 单物体纸片纹理 |
| POST | `/api/aicss/v2/meshes/check` | Blender 可用性检查 |
| POST | `/api/aicss/v2/meshes/export-objects` | 物体级 3D mesh 导出 |
| POST | `/api/aicss/v2/meshes/export-layers` | 深度层 3D mesh 导出 |
| POST | `/api/aicss/v2/meshes/export-scene` | 完整场景 3D mesh 导出 |
| GET | `/api/aicss/v2/meshes/list` | 列出已导出的 mesh |
| GET | `/api/aicss/v2/meshes/{id}/info` | 获取 mesh 元数据 |
| GET | `/api/aicss/v2/meshes/{id}/download` | 下载 mesh 文件 |
| DELETE | `/api/aicss/v2/meshes/{id}` | 删除 mesh 导出 |

---

## 9. 前端组件说明

### 9.1 ScriptEditor（`ScriptEditor.tsx`）

剧本编辑器主组件，托管 4 个标签页：

**标签页 1 — 剧本数据（ScriptTab）**

- 左侧：原始剧本文本输入框（textarea，支持语言切换）
- 右侧：解析结果展示
  - 剧本标题 / 题材 / 一句话简介
  - 角色卡片列表（性别/年龄/性格）
  - 场景卡片列表（地点/时间/氛围）
  - 故事段落列表（按场景分组，带引用关系）
  - 可展开查看标准化剧本（用于调试 LLM 规范化结果）

**标签页 2 — 分镜预览（StoryboardTab）**

- 网格视图：每个分镜一张卡片，显示镜号、景别、运镜标签、动作摘要、角色标签、时长
- 选中状态：左侧高亮 + 右侧详情面板
- 详情面板：景别、运镜、英文场景提示词、动作提示词、相机提示词、对白、时长、起止帧提示词

**标签页 3 — 角色资产（CharactersTab）**

- 左侧：角色列表（显示已生成的三视图缩略图）
- 右侧：选中角色详情 + "生成三视图" 按钮 + 三视图网格（front/side/back）+ 视觉提示词编辑 + 服装变体网格

**标签页 4 — 动作序列（MotionTab）**

- 列出所有 (分镜 × 角色) 组合
- 每行显示：镜号、角色名、动作提示词摘要、"生成动作视频" 按钮
- 生成状态 badge（pending/generating/done/error）
- 成功后显示帧数和分割状态

### 9.2 状态管理（`useScriptStore.ts`）

Zustand store，完整管理剧本解析全链路状态：

```typescript
interface ScriptStore {
  // 输入
  rawScript: string;
  language: ScriptLanguage;

  // 解析结果
  parsedScript: ScriptData | null;
  normalizedScript: string;

  // 分镜
  shots: Shot[];
  sceneTransitions: SceneTransition[];
  characterActionSequences: CharacterActionSequence[];

  // 角色/动作
  characterAssets: Record<string, CharacterAsset>;
  motionSequences: Record<string, MotionSequence>;

  // 加载状态
  isParsing: boolean;
  isGeneratingShots: boolean;
  isGeneratingCharacter: Record<string, boolean>;
  isGeneratingMotion: Record<string, boolean>;

  // UI 状态
  activeTab: 'script' | 'storyboard' | 'characters' | 'motion';
  selectedShotId: string | null;
  selectedCharacterId: string | null;
  error: string | null;

  // Actions
  parseScript(projectId?): Promise<void>;
  generateShots(projectId?): Promise<void>;
  generateCharacterThreeView(charId, projectId?): Promise<void>;
  generateCharacterVariation(charId, prompt, projectId?): Promise<void>;
  generateMotion(shotId, charId, projectId?): Promise<void>;
  reset(): void;
  loadFromProject(data): void;
}
```

### 9.3 API 客户端（`scriptService.ts`）

Axios 封装，自动转换 snake_case ↔ camelCase：

```typescript
const api = axios.create({
  baseURL: `${BASE_URL}/api/aicss`,
  timeout: 300_000,   // 5 分钟，LLM 调用耗时较长
});
```

主要导出函数：

- `parseScript(request)` → `ParseScriptResponse`
- `generateShots(request)` → `GenerateShotsResponse`（camelCase 化）
- `getScenePrompts(shots)` → `{ scenePrompts, transitionPrompts }`
- `generateThreeView(request)` → `ThreeViewResponse`
- `generateVariation(charId, prompt, refImage?, projectId?)` → `{ variationId, image }`
- `generateMotion(request)` → `MotionResponse`
- `segmentFrames(framePaths, charName, actionName, projectId?)` → `MotionResponse`

### 9.4 类型定义（`types/script.ts`）

TypeScript 类型完整镜像后端 dataclass，使用 camelCase。提供序列化/反序列化辅助函数处理 API 边界的大小写差异：

```typescript
// 前端使用 camelCase
{ shotNumber: 1, cameraMovement: "Static", visualPrompts: { scenePrompt: "..." } }

// API 传输使用 snake_case
{ shot_number: 1, camera_movement: "Static", visual_prompts: { scene_prompt: "..." } }

serializeShots(shots)     // camelCase → snake_case
deserializeShots(data)     // snake_case → camelCase
```

---

## 10. 启动与配置

### 10.1 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DASHSCOPE_API_KEY` | DashScope API Key | 必需（用于 LLM + 图像生成） |
| `AICSS_WORKSPACE_DIR` | 工作空间根目录 | `backend/.workspace` |
| `AICSS_DEVICE` | 推理设备 | `cuda`（如可用）|
| `AICSS_SAM2_CHECKPOINT_DIR` | SAM2 模型缓存目录 | `backend/.cache/sam2` |
| `DEBUG_INPAINT_MASK` | 图像修复调试模式 | `0` |
| `AICSS_INPAINT_DEBUG_DIR` | 调试输出目录 | `backend/.cache/inpaint_debug` |

### 10.2 启动后端

```bash
cd backend
pip install -r requirements.txt   # 安装依赖
python -m uvicorn app.main:app --reload --port 8000
```

启动时自动：
1. 加载 DepthAnything-V2-Large（~400MB）
2. 加载 Grounding-DINO-base
3. 加载 SAM2（vit_l checkpoint）
4. 加载 Qwen3-VL-4B-Instruct
5. 清理残留 `.tmp` 文件

### 10.3 启动前端

```bash
cd frontend
npm install
npm run dev
# 访问 http://localhost:5173
```

### 10.4 健康检查

```bash
GET /health
# Response
{
  "status": "ok",
  "device": "cuda",
  "models_loaded": true
}
```

### 10.5 API 文档

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

---

## 附录：导出规格审查报告

### 审查范围

审查所有端点的导出持久化实现是否符合 ProjectStore 规格：目录结构、文件命名、manifest 记录、原子写入。

### 审查清单

| 端点 | 导出目录 | 文件命名规范 | manifest 记录 | 原子写入 |
|------|---------|------------|--------------|---------|
| `/api/aicss/analyze` → depth | `depth/` | `depth_map.png` | ✅ PhaseEntry | ✅ `_write_manifest` |
| `/api/aicss/analyze` → segment | `masks/` | `objects.json`, `mask_<id>.png` | ✅ PhaseEntry | ✅ |
| `/api/aicss/analyze` → layers | `layers/` | `layer_assignments.json`, `layer_<key>.png` | ✅ PhaseEntry | ✅ |
| `/api/aicss/analyze` → scene | `scene/` | `scene_graph.json` | ✅ PhaseEntry | ✅ |
| `/api/aicss/billboard` | `billboards/` | `billboard_<safe_id>.png` | ✅ PhaseEntry | ✅ |
| `/api/aicss/multiface` | `multiface/` | `<safe_id>_face_<face>.png` (7 faces) | ✅ PhaseEntry | ✅ |
| `/api/aicss/paper-style` | `paper/` | `paper_style_<key>.png` | ✅ PhaseEntry | ✅ |
| `/api/aicss/paper-diorama` | `paper/` | `paper_style_<hash>.png` 等 5 张 | ✅ PhaseEntry | ✅ |
| `/api/aicss/paper-layer` | `paper/` | `paper_style_<key>.png` 等 5 张 | ✅ PhaseEntry | ✅ |
| `/api/aicss/inpaint` | `inpaint/` | `inpaint_<ts>.png` | ✅ PhaseEntry | ✅ |
| v2 `/parse` | `manifest.json` | `scriptData` field | ✅ manifest | ✅ |
| v2 `/shots` | `manifest.json` | `shotList` field | ✅ manifest | ✅ |
| v2 `/characters/generate-three-view` | `characters/` | `<id>_front.png` 等 | ✅ 独立方法 | ✅ |
| v2 `/characters/generate-variation` | `characters/` | `<id>_variation_<var>.png` | ✅ 独立方法 | ✅ |
| v2 `/motions/generate` | `motions/` | `<char>_<seq>.json` | ✅ 独立方法 | ✅ |
| **v2 `/meshes/export-*`** | `meshes/objects/`, `meshes/layers/`, `meshes/scenes/` | `<target_id>.glb/.fbx` | ✅ mesh_manifest.json | ✅ |

### 审查结论

所有导出均符合规格：

- ✅ 每个端点对应一个 step 目录（除 v2 script/characters/motions 使用独立目录）
- ✅ 文件命名遵循语义化约定
- ✅ `manifest.json` / `mesh_manifest.json` 正确记录每个 PhaseEntry（含 SHA256）
- ✅ 使用原子写入（`.tmp` → `os.replace`）
- ✅ 提供下载端点 `/projects/{pid}/artifacts/{step}/{filename}`

### 已知不一致（文档 vs 实现）

以下差异已记录，实际代码行为为准：

| 位置 | 文档描述 | 实际实现 | 说明 |
|------|---------|---------|------|
| `paper-diorama` 文件名 | `paper_style_<key>.png` | `paper_style_<mask_md5_hash[:10]>.png` | objectId 不在 `PaperDioramaRequest` 中，使用 mask 内容哈希作为 ID |
| `paper-layer` 文件名 | `paper_style_<key>.png` | `paper_style_<sanitize(layerKey or 'default')>.png` | 使用请求中的 `layerKey` 参数 |
| `multiface` 文件数 | 6 faces | 7 faces (front/back/left/right/top/bottom + one extra) | 实际生成 7 面（含一个额外面） |
| `inpaint` 文件名 | `inpaint_<ts>.png` | `inpaint_<ts>_<file_hash[:8]>.png` | 增加哈希后缀避免并发覆盖 |
| 图像修复模型 | WanEdit wanx2.1 | LaMa (本地模型) | 已用 `lama_loader.py` 替换 DashScope API |

---

## 附录：已实施 vs 未实施对照

| 功能模块 | 状态 | 关键文件 |
|----------|------|----------|
| 剧本两段式解析（LLM + fallback） | ✅ 完全实施 | `script_parser.py` |
| 分镜表生成（景别/运镜/提示词） | ✅ 完全实施 | `shot_generator.py` |
| 场景转场提示词生成 | ✅ 完全实施 | `shot_generator.py` |
| 角色视觉提示词生成 | ✅ 完全实施 | `character_generator.py` |
| 角色三视图生成（wanx-v1） | ✅ 完全实施 | `character_generator.py` |
| 角色变体生成（wanx-v1-imageedit） | ✅ 完全实施 | `character_generator.py` |
| 动作视频生成（wan2.7-i2v） | ✅ 完全实施 | `motion_extractor.py` |
| ffmpeg 帧提取 | ⚠️ 需外部安装 ffmpeg | `motion_extractor.py` |
| SAM2 人物抠像 | ⚠️ heuristic 最大面积选人 | `motion_extractor.py` |
| 深度预测（DepthAnything-V2） | ✅ 完全实施 | `depth_loader.py` |
| Grounding-DINO 零样本检测 | ✅ 完全实施 | `grounding_dino_loader.py` |
| SAM2 自动分割 + 边缘贴合 | ✅ 完全实施 | `sam2_loader.py` |
| Qwen3-VL 场景分类 | ✅ 完全实施 | `qwen3vl_loader.py` |
| 空间分层（前景/中景/远景/天空） | ✅ 完全实施 | `spatial_utils.py` |
| 图像修复（WanEdit wanx2.1） | ✅ 完全实施 | `inpaint_utils.py` |
| 纸片风格纹理（厚度/法线/描边） | ✅ 完全实施 | `paper_diorama.py` |
| Billboard 贴图 | ✅ 完全实施 | `endpoints.py` |
| 六面展开图 | ✅ 完全实施 | `endpoints.py` |
| 三维立体纸雕导出 (FBX/GLB) | ✅ 完全实施 | `mesh_exporter.py`, `project_store_mesh.py`, `endpoints_mesh.py` |
| 项目存储（manifest + 产物落盘） | ✅ 完全实施 | `project_store.py` |
| 镜头管理（CRUD + 帧持久化） | ✅ 完全实施 | `endpoints_shots.py` |
| 前端 4-tab 剧本编辑器 | ✅ 完全实施 | `ScriptEditor.tsx` |
| 前端 3D 查看器（Three.js） | ✅ 完全实施 | `Viewer3D.tsx` |
| 前端深度分层（canvas bucketing） | ✅ 完全实施 | `depthSplit.ts` |
