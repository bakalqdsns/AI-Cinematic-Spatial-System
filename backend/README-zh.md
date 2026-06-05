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
- 该端点已在代码中实现，现在也已在文档中补齐。

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
