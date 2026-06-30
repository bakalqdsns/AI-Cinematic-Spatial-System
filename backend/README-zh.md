# AICSS Backend

AICSS 后端是 AI Cinematic Spatial System 的 FastAPI 推理服务，负责提供深度估计、分割、空间分层、Billboard 生成、多面贴图生成以及遮罩局部重绘等运行时 API。

---

## 职责

后端主要负责：

- 在启动时加载全部模型
- 接收来自前端的图像与遮罩数据
- 生成深度图与分割结果
- 推导空间层与场景图关系
- 生成透明 RGBA Billboard 切图
- 将局部重绘请求转发到 DashScope

实际运行行为以以下文件为准：

- `app/config.py`
- `app/endpoints.py`
- `app/main.py`

---

## 技术栈

- Python 3.10+
- FastAPI
- Uvicorn
- PyTorch + TorchVision
- Transformers
- OpenCV
- Pillow
- NumPy
- DashScope SDK

---

## 目录说明

```text
backend/
├── app/
│   ├── main.py                  FastAPI 应用、CORS、启动生命周期
│   ├── config.py                所有 AICSS_* 配置
│   ├── endpoints.py             API 数据结构与处理器
│   ├── models/
│   │   ├── model_manager.py     模型生命周期单例
│   │   ├── depth_loader.py      DepthAnything 封装
│   │   ├── grounding_dino_loader.py
│   │   └── sam2_loader.py       SAM2 推理与轮廓修正
│   └── utils/
│       ├── image_utils.py       base64、PIL、深度辅助工具
│       ├── spatial_utils.py     图层与场景图辅助逻辑
│       ├── vlm_utils.py         DashScope VLM 集成
│       └── inpaint_utils.py     DashScope 局部重绘集成
├── requirements.txt
├── run.py                       推荐启动入口
├── README.md
└── SPEC.md                      较旧的规范文档，当前不一定与运行时代码完全一致
```

---

## 前置要求

- Python 3.10+
- 足够的磁盘空间用于模型缓存与权重
- 推荐 CUDA 12.x，以获得更可用的推理速度
- 需要 DashScope API 访问权限以支持 VLM 与局部重绘流程

---

## 安装步骤

### 1. 创建虚拟环境

```bash
cd backend
python -m venv .venv
```

激活方式：

```bash
# PowerShell
.\.venv\Scripts\Activate.ps1

# CMD
.\.venv\Scripts\activate.bat

# Bash / Git Bash / WSL
source .venv/bin/activate
```

### 2. 安装依赖

GPU 示例：

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
```

仅 CPU 示例：

```bash
pip install -r requirements.txt
```

### 3. 准备模型资源

#### SAM2 权重

`AICSS_SAM2_MODEL_SIZE` 必须与后端使用的权重文件相匹配。

当前默认值：

- `AICSS_SAM2_MODEL_SIZE=vit_l`
- 对应权重族：`sam2.1_l.pt`

常见映射如下：

| 配置值 | 权重文件 |
|---|---|
| `vit_l` | `sam2.1_l.pt` |
| `vit_b` | `sam2.1_b.pt` |
| `vit_s` | `sam2.1_s.pt` |
| `vit_t` | `sam2.1_t.pt` |

下载来源：
- [Segment Anything 2 releases](https://github.com/facebookresearch/segment-anything-2/releases)

#### HuggingFace 模型

应用会通过 `app/config.py` 将 HuggingFace 缓存重定向到 `backend/.cache/`。

你也可以在首次启动前手动预下载：

```bash
python -c "from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor; AutoProcessor.from_pretrained('IDEA-Research/grounding-dino-base'); AutoModelForZeroShotObjectDetection.from_pretrained('IDEA-Research/grounding-dino-base')"

python -c "from transformers import AutoModelForDepthEstimation, AutoImageProcessor; AutoImageProcessor.from_pretrained('depth-anything/Depth-Anything-V2-Large-hf'); AutoModelForDepthEstimation.from_pretrained('depth-anything/Depth-Anything-V2-Large-hf')"
```

---

## 启动服务

推荐方式：

```bash
python run.py
```

其他常见方式：

```bash
python run.py --cpu
python run.py --port 8080
```

也可以直接使用 Uvicorn，但仓库默认推荐 `run.py`：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

服务启动时，FastAPI lifespan 会尝试预加载全部模型。如果模型加载失败，服务可能仍能启动，但推理端点会在后续调用时报错。

启动后常用地址：

- `http://localhost:8000/health`
- `http://localhost:8000/docs`
- `http://localhost:8000/redoc`

---

## 配置说明

所有配置定义在 `app/config.py` 中，并统一使用 `AICSS_` 前缀。

### 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `AICSS_HOST` | `0.0.0.0` | 监听地址 |
| `AICSS_PORT` | `8000` | 服务端口 |
| `AICSS_RELOAD` | `true` | 是否启用自动重载 |
| `AICSS_DEVICE` | `cuda` | `cuda` 或 `cpu` |
| `AICSS_HF_TOKEN` | 空 | HuggingFace token |
| `AICSS_DEPTH_MODEL` | `depth-anything/Depth-Anything-V2-Large-hf` | 深度模型 ID |
| `AICSS_GROUNDING_DINO_MODEL` | `IDEA-Research/grounding-dino-base` | 检测模型 ID |
| `AICSS_SAM2_MODEL_SIZE` | `vit_l` | SAM2 尺寸选择 |
| `AICSS_SEGMENTATION_PROMPT` | 内置默认列表 | 分割回退提示词 |
| `AICSS_DASHSCOPE_API_KEY` | 空 | 服务端 DashScope Key 回退值 |
| `AICSS_DASHSCOPE_MODEL` | `wanx2.1-imageedit` | inpaint 模型名 |
| `AICSS_DASHSCOPE_FUNCTION` | `description_edit_with_mask` | DashScope 功能名 |
| `AICSS_INPAINT_TIMEOUT` | `120` | 局部重绘超时秒数 |

### `.env` 示例

```env
AICSS_DEVICE=cuda
AICSS_PORT=8000
AICSS_RELOAD=true
AICSS_SAM2_MODEL_SIZE=vit_l
AICSS_DASHSCOPE_API_KEY=your_dashscope_key
```

仓库现已提供 `backend/.env.example` 作为参考模板。

---

## API 端点

所有 API 统一挂载在 `/api/aicss` 下。

### `POST /api/aicss/analyze`

执行完整分析管线。

请求体：

```json
{
  "imageUrl": "data:image/png;base64,...",
  "shotId": "shot_001",
  "apiKey": "your_dashscope_key"
}
```

说明：
- 当前请求模型中 `apiKey` 为必填。
- 后端使用该 key 调用 DashScope VLM 完成场景与类别推断。
- 响应中在可用时还会返回 `vlmDetectedClasses` 与 `vlmDetectedScene`。

### `POST /api/aicss/depth`

仅生成深度图。

```json
{
  "imageUrl": "data:image/png;base64,..."
}
```

### `POST /api/aicss/segment`

仅执行分割。

```json
{
  "imageUrl": "data:image/png;base64,...",
  "apiKey": "your_dashscope_key"
}
```

### `POST /api/aicss/layers`

根据深度图与对象列表重建深度图层。

```json
{
  "depthMap": "data:image/png;base64,...",
  "objects": [],
  "imageWidth": 1024,
  "imageHeight": 768
}
```

### `POST /api/aicss/scene-graph`

重建空间关系图。

```json
{
  "shotId": "shot_001",
  "objects": []
}
```

### `POST /api/aicss/billboard`

为单个对象生成透明 RGBA 切图。

```json
{
  "imageUrl": "data:image/png;base64,...",
  "objectId": "obj_person_0",
  "boundingBox": { "x": 0.12, "y": 0.31, "w": 0.08, "h": 0.55 },
  "polygon": [[0.12, 0.31], [0.20, 0.31], [0.20, 0.86], [0.12, 0.86]]
}
```

说明：
- `polygon` 可选。
- 省略或为空时，后端会退回使用 `boundingBox`。

### `POST /api/aicss/multiface`

生成六面伪 3D 贴图。

```json
{
  "imageUrl": "data:image/png;base64,...",
  "objectId": "obj_person_0",
  "boundingBox": { "x": 0.12, "y": 0.31, "w": 0.08, "h": 0.55 },
  "polygon": [[0.12, 0.31], [0.20, 0.31], [0.20, 0.86], [0.12, 0.86]]
}
```

### `POST /api/aicss/inpaint`

通过 DashScope 执行遮罩局部重绘。

```json
{
  "imageUrl": "data:image/png;base64,...",
  "maskDataUrl": "data:image/png;base64,...",
  "prompt": "remove the person and reconstruct the background",
  "apiKey": "your_dashscope_key"
}
```

说明：
- 只有在后端已经配置 `AICSS_DASHSCOPE_API_KEY` 时，`apiKey` 才可以省略。
- 该端点内部为异步实现：服务端会轮询 DashScope，直到超过 `AICSS_INPAINT_TIMEOUT` 秒（默认 `120`）后报错。

### `POST /api/aicss/paper-style`

将照片转换为纸雕 / 插画风格：双边滤波 + 颜色量化 + Canny 边缘合成。该端点是 paper-diorama 纹理生成流程的第一阶段。

请求体：

```json
{
  "imageUrl": "data:image/png;base64,...",
  "colorLevels": 12,
  "styleStrength": 0.7,
  "edgeLow": 50,
  "edgeHigh": 150
}
```

响应：

```json
{
  "styledImageUrl": "data:image/png;base64,..."
}
```

参数说明：
- `colorLevels`（3–30）：值越小颜色越平，越像剪纸。
- `styleStrength`（0–1）：双边滤波强度，值越大平面区域越光滑。

### `POST /api/aicss/paper-diorama`

针对单个物体生成完整的纸雕贴图集合。`maskDataUrl` 描述物体范围，返回 5 张纹理供下游 3D 渲染使用。

请求体：

```json
{
  "imageUrl": "data:image/png;base64,...",
  "maskDataUrl": "data:image/png;base64,...",
  "thicknessMin": 1.0,
  "thicknessMax": 5.0,
  "outlineWidth": 3,
  "colorLevels": 12,
  "styleStrength": 0.7
}
```

响应（5 个字段均为 base64 PNG）：

```json
{
  "paper_style_url":   "data:image/png;base64,...",
  "outlined_url":      "data:image/png;base64,...",
  "thickness_url":     "data:image/png;base64,...",
  "thickness_gray_url":"data:image/png;base64,...",
  "normal_map_url":    "data:image/png;base64,..."
}
```

说明：
- `maskDataUrl` 为灰度 PNG，`255` = 物体，`0` = 背景。
- `thicknessMin` / `thicknessMax` 单位毫米，仅影响归一化；相对高度场保持不变。
- paper-style 输出 RGBA，纸模外部区域透明。

### `POST /api/aicss/paper-layer`

与 `/paper-diorama` 字段一致，但作用于**整层深度图**（RGBA 图像，alpha 即图层归属）。无需外部 mask——`layerImageUrl` 的 alpha 通道就是权威 mask。可选 `layerMaskUrl` 会在提供时与 alpha 取交集。

请求体：

```json
{
  "layerImageUrl": "data:image/png;base64,...",
  "layerMaskUrl": "data:image/png;base64,...",
  "thicknessMin": 1.0,
  "thicknessMax": 5.0,
  "outlineWidth": 3,
  "colorLevels": 12,
  "styleStrength": 0.7
}
```

响应：与 `/paper-diorama` 相同的 5 字段。

### `GET /health`

返回示例：

```json
{
  "status": "ok",
  "device": "cuda",
  "models_loaded": true
}
```

---

## Project Workspace（长期存储 + 断点续做）

后端会把每个项目的中间 ML 产物和贴图持久化到磁盘，以**项目 ID** 为单位组织在 `backend/.workspace/projects/` 下。它能带来：

- 每个 shot 拥有独立的项目文件夹（持久化），后端重启不丢失。
- step 级别细粒度——任意一个阶段可以单独重新跑，不必从头来。
- 断点续做——重新打开项目，看 `manifest.json` 知道哪些阶段已完成，从断点继续。
- 人类可读的 `manifest.json` 列出每个产物的 SHA-256 与时间戳。

### 目录布局

```
backend/.workspace/
└── projects/
    └── 20260630_220000_shot_001/
        ├── manifest.json           ← 索引与元数据（原子重写）
        ├── input/
        │   └── original.png        ← 原始图
        ├── depth/
        │   └── depth_map.png       ← 深度图
        ├── masks/
        │   ├── objects.json        ← 所有 DetectedObject 元数据
        │   └── mask_<objectId>.png ← 每物体二值 mask
        ├── layers/
        │   └── layer_assignments.json
        ├── scene/
        │   └── scene_graph.json
        ├── billboards/
        │   └── billboard_<objectId>.png
        ├── multiface/
        │   └── <objectId>_face_<front|back|left|right|top|bottom>.png
        ├── paper/
        │   ├── paper_style_<key>.png
        │   ├── paper_outlined_<key>.png
        │   ├── paper_thickness_<key>.png
        │   ├── paper_thickness_gray_<key>.png
        │   └── paper_normal_<key>.png
        └── inpaint/
            └── inpaint_<ts>.png
```

### Manifest Schema

```json
{
  "projectId": "20260630_220000_shot_001",
  "shotId": "shot_001",
  "createdAt": "2026-06-30T22:00:00Z",
  "updatedAt": "2026-06-30T22:05:30Z",
  "imageWidth": 1920,
  "imageHeight": 1080,
  "inputHash": "sha256:abc123...",
  "artifacts": {
    "depth":   { "files": [...], "savedAt": "..." },
    "segment": { "files": [...], "savedAt": "..." },
    "layers":  { "files": [...], "savedAt": "..." },
    "paper":   { "files": [...], "savedAt": "..." }
  },
  "timeline": [
    { "phase": "analyze", "startedAt": "...", "finishedAt": "...", "durationMs": 12345 }
  ]
}
```

### 项目管理端点

| 方法 | 路径 | 用途 |
|---|---|---|
| `POST` | `/api/aicss/projects`（multipart） | 创建项目并上传原始图（返回 `projectId`） |
| `POST` | `/api/aicss/projects/json` | 用 JSON body（base64 data URL）创建项目 |
| `GET` | `/api/aicss/projects` | 列出所有项目（仅 summary） |
| `GET` | `/api/aicss/projects/{pid}/manifest` | 读取完整 manifest |
| `GET` | `/api/aicss/projects/{pid}/artifacts/{step}/{filename}` | 拉取单个产物（PNG 或 JSON） |
| `POST` | `/api/aicss/projects/{pid}/checkpoint` | 记录一次 phase 起始 / 结束事件到 timeline |
| `DELETE` | `/api/aicss/projects/{pid}` | 删除项目（不可恢复） |

### 在既有端点中传入 `projectId`

所有 ML 端点都支持可选的 `projectId` 字段。传入时，响应会同时把产物写入对应项目的 `<step>/` 子目录并刷新 `manifest.json`。

| 端点 | 落盘内容 |
|---|---|
| `POST /api/aicss/analyze` | 一次性写完 `depth/`、`masks/`、`layers/`、`scene/` |
| `POST /api/aicss/depth` | `depth/depth_map.png` |
| `POST /api/aicss/segment` | `masks/objects.json` + `masks/mask_<id>.png` × N |
| `POST /api/aicss/layers` | `layers/layer_assignments.json` |
| `POST /api/aicss/scene-graph` | `scene/scene_graph.json` |
| `POST /api/aicss/billboard` | `billboards/billboard_<id>.png` |
| `POST /api/aicss/multiface` | `multiface/<id>_face_<face>.png` × 6 |
| `POST /api/aicss/inpaint` | `inpaint/inpaint_<ts>.png` |
| `POST /api/aicss/paper-style` | `paper/paper_style_<key>.png`（用 `layerKey` 命名） |
| `POST /api/aicss/paper-diorama` | 5 张纸模贴图写入 `paper/` |
| `POST /api/aicss/paper-layer` | 5 张纸模贴图写入 `paper/`（用 `layerKey` 命名） |

**不传** `projectId` 时，端点行为与之前完全一致——向后兼容。

### 断点续做示例

1. 用户开始项目：`POST /api/aicss/projects/json`，传 `shotId` 和 `imageBase64`。后端返回 `projectId = "20260630_220000_shot_001"`。
2. 前端把 `projectId` 透传给所有后续 `/analyze`、`/paper-layer` 等调用。
3. 后端逐步把产物写入项目目录。
4. 即便用户关闭浏览器，重新打开后前端可以 `GET /projects/{pid}/manifest` 看哪些阶段已完成，从下一个阶段继续。

### 配置

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `AICSS_WORKSPACE_DIR` | `backend/.workspace/` | 项目存储根目录，自动创建 `projects/` 子目录。 |

workspace 通过 `.gitignore` 排除（`backend/.workspace/`），不会进入版本控制。

### 原子性保证

- `manifest.json` 通过 `*.tmp` → `os.replace()` 写入（POSIX 完全原子，Windows 上接近原子）。
- 每个项目内部用 `asyncio.Lock` 串行化写操作。
- 启动时自动清理残留的 `*.tmp` 文件。

---

## DashScope 使用说明

后端目前在两个位置使用 DashScope：

1. `vlm_utils.py`
   - 场景识别
   - 提取分割所需的类别集合
2. `inpaint_utils.py`
   - 遮罩局部重绘

对开发者的影响：

- 如果服务端未配置 `AICSS_DASHSCOPE_API_KEY`，前端必须在支持的请求中传入 API key
- 当前实现下，`analyze` 和 `segment` 依赖 VLM 辅助检测流程
- 网络延迟和供应商限流会直接影响体感耗时

---

## 日志与运行特性

- 日志会写入 `backend/logs/aicss.log`
- 模型通过 FastAPI lifespan 在启动阶段预加载
- 当前 CORS 配置 `allow_origins=["*"]`，主要方便本地开发
- `app/main.py` 会把 backend 根目录注入 `sys.path`，以支持 `from app...` 形式导入

---

## 已知问题与当前限制

- `SPEC.md` 仍然只是参考文档，不应替代运行时代码。
- `app/utils/inpaint_utils.py` 之前包含硬编码本地调试输出路径，这类实现不具备可移植性。
- 当前仓库没有成体系的后端自动化测试说明。
- 当前还没有生产部署与 Docker 指南。
- 在纯 CPU 环境下模型启动可能非常慢。

---

## 排障建议

### 服务启动了，但推理失败
- 确认所需模型权重已存在
- 确认 SAM2 权重文件名与 `AICSS_SAM2_MODEL_SIZE` 对应
- 查看 `backend/logs/aicss.log`
- 检查 `http://localhost:8000/health`

### `analyze` 或 `segment` 请求异常
- 确认传入的是有效的 DashScope API key
- 确认当前环境可访问 DashScope
- 对照 `app/endpoints.py` 检查请求体字段

### 首次启动特别慢
- 首次运行或纯 CPU 模式下属正常现象
- 可先手动预下载 HuggingFace 模型以减少冷启动时间

---

## 相关文档

- 仓库总览：`../README.md`
- 前端开发指南：`../frontend/README.md`
- 后端运行时配置：`app/config.py`
- 后端 API 数据结构：`app/endpoints.py`
