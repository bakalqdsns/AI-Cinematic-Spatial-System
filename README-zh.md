# AI Cinematic Spatial System (AICSS)

> 将单张 2D 图像转换为具有深度分层的伪 3D 场景，分割前景物体，生成透明 Billboard 贴图，并在 Three.js 工作区中进行交互式预览。

**[English Version](./README.md)**

---

## 项目用途

AICSS 是一个完整的前后端工具链，用于把单张图像转换为具备空间层次的场景结构：

- 前端负责导入图像，并统一到 1920×1080 工作画布
- 后端负责深度估计、目标检测、掩码分割与空间层构建
- 前端允许用户查看掩码、分配颜色层、生成 Billboard 切图并在 3D 中预览
- 可选的 DashScope VLM 与 Inpaint 流程可用于增强目标理解和局部修补

该仓库同时包含浏览器端 UI 和推理后端。

---

## 系统架构

```text
用户导入图像
      │
      ▼
┌──────────────────────────────────────────────────────────────┐
│ 前端 (React + Vite + Zustand + Three.js)                    │
│                                                              │
│ Toolbar → ImageCanvas → LayerSelector → SplitControls       │
│             2D 叠加层         图层分配                       │
│                                                              │
│ Viewer3D 渲染生成出的 RGBA Billboard 纹理                   │
└──────────────────────────────────────────────────────────────┘
      │
      │ POST /api/aicss/analyze
      ▼
┌──────────────────────────────────────────────────────────────┐
│ 后端 (FastAPI + PyTorch)                                     │
│                                                              │
│ analyze      完整分析管线                                    │
│ billboard    基于 polygon 的透明切图                         │
│ multiface    6 面伪 3D 纹理                                  │
│ inpaint      基于 DashScope 的遮罩重绘                       │
└──────────────────────────────────────────────────────────────┘
      │
      ▼
┌──────────────────────────────────────────────────────────────┐
│ 模型与后处理                                                  │
│                                                              │
│ DepthAnything V2      深度估计                               │
│ Grounding DINO        目标检测                               │
│ SAM2                  实例掩码                               │
│ Qwen-VL               场景/类别推断                          │
│ OpenCV 后处理         轮廓修正                               │
└──────────────────────────────────────────────────────────────┘
```

---

## 仓库结构

```text
.
├── frontend/                     React 19 + TypeScript + Vite 应用
│   ├── src/
│   │   ├── App.tsx              根布局与导入流程
│   │   ├── components/          2D/3D UI 组件
│   │   ├── services/            后端 API 客户端
│   │   ├── store/               Zustand 状态仓库
│   │   ├── types/               前端共享类型
│   │   └── utils/               IndexedDB 持久化与辅助函数
│   ├── .env.example             前端环境变量模板
│   ├── package.json
│   └── README.md
│
├── backend/                      FastAPI 推理服务
│   ├── app/
│   │   ├── main.py              应用入口、CORS、lifespan
│   │   ├── config.py            所有 AICSS_* 配置
│   │   ├── endpoints.py         REST 端点与数据结构
│   │   ├── models/              模型加载器与管理器
│   │   └── utils/               图像、空间、VLM、inpaint 工具
│   ├── requirements.txt
│   ├── run.py                   推荐使用的后端启动脚本
│   ├── README.md
│   └── SPEC.md                  历史规范文档，当前与实现并未完全同步
│
├── README.md                     英文说明
└── README-zh.md                  本文件
```

---

## 端到端流程

1. 在前端导入图像。
2. 前端先把图像统一缩放到 1920×1080 工作尺寸。
3. 点击 `Analyze`，调用 `POST /api/aicss/analyze`。
4. 后端执行：
   - 加载图像
   - 生成深度图
   - 使用 DashScope VLM 推断场景和目标类别
   - 使用 Grounding DINO + SAM2 做目标分割
   - 将掩码轮廓修正为 polygon
   - 生成深度层和场景图
5. 前端在 2D 视图展示掩码，并允许用户分配颜色层。
6. 点击 `Split Image`，对选中的物体调用 `POST /api/aicss/billboard`。
7. 生成的 RGBA 贴图会在 `Viewer3D` 中显示。
8. 如需局部重绘，可额外调用 `POST /api/aicss/inpaint`。

---

## 技术栈

### 前端
- React 19
- TypeScript 6
- Vite 8
- Tailwind CSS v4
- Zustand 5
- Three.js + `@react-three/fiber` + `@react-three/drei`
- Axios
- IndexedDB 本地会话持久化

### 后端
- Python 3.10+
- FastAPI + Uvicorn
- PyTorch + TorchVision
- Transformers
- OpenCV + Pillow + NumPy
- DashScope API 用于 VLM 与 Inpaint

---

## 本地开发快速开始

### 环境要求
- Python 3.10+
- Node.js 18+
- npm 9+
- 推荐 CUDA 12.x，以获得可接受的推理速度
- `analyze`、`segment` 与 inpaint 相关流程需要 DashScope API Key

### 1. 启动后端

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
python run.py
```

如果本机没有 CUDA，可直接安装普通依赖后运行：

```bash
python run.py --cpu
```

### 2. 配置前端

```bash
cd frontend
copy .env.example .env
npm install
npm run dev
```

默认前端配置如下：

```env
VITE_AICSS_BACKEND=http://localhost:8000
```

### 3. 验证系统

- 后端健康检查：`http://localhost:8000/health`
- 后端文档：`http://localhost:8000/docs`
- 前端开发服务器：`http://localhost:5173`

### 4. 使用应用

1. 打开前端页面。
2. 在顶部工具栏中输入 DashScope API Key。
3. 导入一张图像。
4. 点击 `Analyze`。
5. 选择图层并为对象分层。
6. 点击 `Split Image`。
7. 在 3D 视图中查看 Billboard 效果。

---

## 配置总览

### 前端

| 变量 | 默认值 | 作用 |
|---|---|---|
| `VITE_AICSS_BACKEND` | `http://localhost:8000` | 后端基础地址 |

### 后端

后端真实配置以 `backend/app/config.py` 为准。

| 变量 | 默认值 | 作用 |
|---|---|---|
| `AICSS_HOST` | `0.0.0.0` | 监听地址 |
| `AICSS_PORT` | `8000` | 服务端口 |
| `AICSS_RELOAD` | `true` | 开发模式自动重载 |
| `AICSS_DEVICE` | `cuda` | `cuda` 或 `cpu` |
| `AICSS_HF_TOKEN` | 空 | HuggingFace token |
| `AICSS_DEPTH_MODEL` | `depth-anything/Depth-Anything-V2-Large-hf` | 深度模型 ID |
| `AICSS_GROUNDING_DINO_MODEL` | `IDEA-Research/grounding-dino-base` | 检测模型 ID |
| `AICSS_SAM2_MODEL_SIZE` | `vit_l` | SAM2 权重规模 |
| `AICSS_SEGMENTATION_PROMPT` | 内置默认类别列表 | 回退提示词 |
| `AICSS_DASHSCOPE_API_KEY` | 空 | 服务端 DashScope Key 回退值 |
| `AICSS_DASHSCOPE_MODEL` | `wanx2.1-imageedit` | inpaint 模型 |
| `AICSS_INPAINT_TIMEOUT` | `120` | inpaint 超时时间（秒） |

---

## API 范围

所有后端端点都挂载在 `/api/aicss` 下。

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/analyze` | 完整分析流程，请求体需要 `imageUrl`、`shotId`、`apiKey` |
| `POST` | `/depth` | 仅生成深度图 |
| `POST` | `/segment` | 仅分割，请求体需要 `imageUrl`、`apiKey` |
| `POST` | `/layers` | 根据 `depthMap` 和 objects 重建图层 |
| `POST` | `/scene-graph` | 重建场景图 |
| `POST` | `/billboard` | 生成透明切图 |
| `POST` | `/multiface` | 生成 6 面伪 3D 贴图 |
| `POST` | `/inpaint` | 遮罩局部重绘，若已配置环境变量则 `apiKey` 可省略 |
| `GET` | `/health` | 运行状态 |

精确的请求/响应结构建议直接查看：
- `http://localhost:8000/docs`
- `backend/app/endpoints.py`
- `frontend/src/services/aicssService.ts`

---

## 开发说明

- 前端在分析前会先把导入图像统一为 1920×1080。
- 前端在工具栏输入 DashScope Key，并在 `analyze` 与 inpaint 请求中使用它。
- IndexedDB 会话恢复能力已经存在，但当前 UI 只会尝试恢复最近一次会话，没有完整的会话管理界面。
- 前端状态里存在 `crop` 与 billboard offset 相关数据，但交互流程尚未完整暴露给用户。
- 后端模型会在 FastAPI 启动阶段通过 lifespan 预加载。

---

## 已知问题与风险

- `backend/SPEC.md` 与当前运行代码并未完全对齐。
- `backend/app/utils/inpaint_utils.py` 仍包含硬编码本地调试路径，建议后续移除或改为临时目录。
- 当前仓库没有后端 `.env.example`。
- 当前代码库没有自动化测试与部署文档。
- 当前 CORS 对所有来源开放，便于开发，但不适合直接作为生产配置。

---

## 建议阅读顺序

- 先看本文件：`README-zh.md`
- 后端安装与接口细节：`backend/README.md`
- 前端结构与工作流：`frontend/README.md`
- 后端配置真相来源：`backend/app/config.py`
- 后端接口真相来源：`backend/app/endpoints.py`

---

## 当前文档范围说明

本次文档主要覆盖本地开发与代码理解，不包含以下内容：

- 生产部署指南
- Docker 配置
- CI/CD 说明
- 自动化测试流程

这些内容建议在项目进入交接或发布阶段后单独补齐。
