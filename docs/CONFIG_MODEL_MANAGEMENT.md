# 配置与模型管理文档

> **适用范围**：AICinematicSpatialSystem 后端 (`backend/app`)
>
> **评估日期**：2026-07-27
>
> **相关文件**：`config.py`、`model_manager.py`、`gpu_concurrency.py`、`main.py`、各模型 Loader 文件

---

## 目录

1. [配置系统](#1-配置系统)
2. [DashScope API 调用](#2-dashscope-api-调用)
3. [模型加载器](#3-模型加载器)
4. [模型生命周期管理](#4-模型生命周期管理)
5. [GPU 并发控制](#5-gpu-并发控制)
6. [启动与健康检查](#6-启动与健康检查)
7. [快速参考](#7-快速参考)

---

## 1. 配置系统

### 1.1 核心配置类

**文件**: [backend/app/config.py](backend/app/config.py)

所有配置集中在 `Settings` 类中（第 59-154 行），支持环境变量覆盖（前缀 `AICSS_`）。

#### 1.1.1 缓存与目录

| 配置项 | 默认值 | 环境变量 | 说明 |
|--------|--------|----------|------|
| `CACHE_DIR` | `BASE_DIR / ".cache"` | - | 所有模型权重的统一缓存根目录 |
| `HF_HOME` | `.cache/huggingface` | - | HuggingFace 全局缓存根目录 |
| `HF_HUB_CACHE` | `.cache/huggingface/hub` | - | 模型权重缓存子目录 |
| `TRANSFORMERS_CACHE` | `.cache/huggingface/transformers` | - | Transformers 专用缓存 |
| `workspace_dir` | `BASE_DIR / ".workspace"` | `AICSS_WORKSPACE_DIR` | 项目存储根目录 |

#### 1.1.2 HuggingFace 网络优化

所有 HuggingFace 下载均通过以下三重保护机制处理：

```python
HF_HUB_DOWNLOAD_TIMEOUT = "600"     # 10分钟（默认10秒太短，解决 WinError 10060）
HF_HUB_DISABLE_XET = "1"           # 禁用 Xet 绕过 hf-mirror 认证问题
HF_ENDPOINT = "https://hf-mirror.com"  # 使用国内镜像站点
```

#### 1.1.3 模型选择

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `depth_model` | `"depth-anything/Depth-Anything-V2-Large-hf"` | DepthAnything V2 Large |
| `grounding_dino_model` | `"IDEA-Research/grounding-dino-base"` | Grounding DINO Base |
| `sam2_model_size` | `"vit_l"` | SAM2 模型尺寸: vit_l / vit_b / vit_s / vit_t |
| `vlm_model` | `"Qwen/Qwen3-VL-4B-Instruct"` | Qwen3-VL-4B-Instruct（本地 VLM） |
| `image_model_id` | `"Tongyi-MAI/Z-Image-Turbo"` | 主图像生成模型，可降级到 SDXL |
| `video_provider` | `"dashscope"` | 视频生成提供者: dashscope / local_wan / svd |

#### 1.1.4 显存与加载策略

| 配置项 | 默认值 | 环境变量 | 说明 |
|--------|--------|----------|------|
| `device` | `"cuda"` | `AICSS_DEVICE` | 推理设备，可设为 `"cpu"` |
| `lazy_load` | `True` | `AICSS_LAZY_LOAD` | **按需懒加载**，节省 16-22GB 常驻显存 |
| `hf_token` | `""` | `HF_TOKEN` | HuggingFace token（无需认证则留空） |

**懒加载说明**：开启时模型在首次 API 请求时才加载到显存，显存占用接近 0。关闭时（`AICSS_LAZY_LOAD=false`）在服务启动时加载全部模型，首次推理无延迟但启动慢。

#### 1.1.5 检查点目录

| 配置项 | 默认路径 |
|--------|----------|
| `sam2_checkpoint_dir` | `.cache/sam2/` |
| `grounding_dino_checkpoint_dir` | `.cache/grounding-dino/` |
| `depth_checkpoint_dir` | `.cache/depth/` |
| `lama_checkpoint_dir` | `.cache/lama/` |
| `vlm_checkpoint_dir` | `.cache/qwen3vl/` |
| `image_checkpoint_dir` | `.cache/z-image/` |

#### 1.1.6 LLM 配置（本地 llama.cpp）

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `llm_base_url` | `"http://localhost:8080/v1"` | 本地 llama.cpp 服务器地址 |
| `llm_model` | `"qwen2.5-7b-q4_k_m"` | 模型名称 |
| `llm_timeout` | `600.0` 秒 | CPU 推理超时（5 分钟） |

#### 1.1.7 深度分层配置

```python
depth_buckets = {
    (0, 5): "foreground",     # 0-5 米：最前图层
    (5, 15): "midground",      # 5-15 米：中间图层
    (15, 50): "background",     # 15-50 米：背景图层
    (50, float("inf")): "sky",  # 50 米以上：天空
}
```

---

## 2. DashScope API 调用

### 2.1 全量清单

| 模型 | 用途 | 调用状态 | API Key |
|------|------|----------|---------|
| **wan2.7-i2v** | 视频生成 | ✅ 生产使用中 | ✅ 必需 |
| **wanx-v1** | 文生图 | ❌ 代码存在但未调用 | 未显式传递 |
| **wanx2.1-imageedit** | 图像编辑 | ❌ **已废弃**，改用本地 LaMa | N/A |
| **VLM (视觉语言模型)** | 场景分析 | ❌ **已废弃**，改用本地 Qwen3-VL | N/A |

> **注意**：脚本解析（`script_parser.py`）默认走 DashScope 云端，若调用失败则自动降级到本地 llama.cpp Qwen2.5-7B-Instruct Q4_K_M GGUF。

### 2.2 唯一生产调用：wan2.7-i2v 视频生成

**文件**: [backend/app/services/video_adapter.py](backend/app/services/video_adapter.py)

**类**: `DashScopeFilmProvider`（第 77-163 行）

```python
# 导入
import dashscope
from dashscope.api.entities.dashscope import FilmConcurrentRequest

# 创建任务
request = FilmConcurrentRequest(model="wan2.7-i2v", prompt=prompt)
request.add_clip_first_frame(base64_str, width, height)
request.add_clip_last_frame(base64_str, width, height)
task_resp = dashscope.Film.call(
    request=request,
    api_key=os.getenv("DASHSCOPE_API_KEY", ""),
)

# 轮询状态
task_status = dashscope.Film.fetch(task_id=task_resp.output.task_id)
video_url = task_status.output.video.video_url
```

**API Key 注入方式**: 通过环境变量 `DASHSCOPE_API_KEY` 注入，代码中默认值为空字符串（**必须设置，否则请求失败**）。

**错误处理**:

| 错误类型 | 处理方式 |
|----------|----------|
| 任务创建失败（`status != 200`） | 返回 `None` |
| 任务执行失败（`failed` / `error`） | 返回 `None` |
| 超时（300 秒） | 返回 `None` |
| 网络异常 | 捕获并返回 `None` |
| 视频下载失败 | 捕获并返回 `None` |

### 2.3 未调用代码

#### `generate_image`（wanx-v1 文生图）

**文件**: [backend/app/utils/inpaint_utils.py](backend/app/utils/inpaint_utils.py) 第 274-304 行

```python
from dashscope import ImageSynthesis

response = ImageSynthesis.call(
    model="wanx-v1",
    prompt=prompt,
    size="1024*1024",
    n=1,
)
```

**状态**: 代码存在但未在任何业务逻辑中被调用，仅作保留。

#### `generate_video`（wan2.7-i2v 视频）

**文件**: [backend/app/utils/inpaint_utils.py](backend/app/utils/inpaint_utils.py) 第 307-351 行

```python
from dashscope.api.entities.dashscope import FilmConcurrentRequest

request = FilmConcurrentRequest(model="wan2.7-i2v", prompt=prompt)
task_response = dashscope.Film.call(request=request)
```

**状态**: 代码存在但未在任何业务逻辑中被调用，仅作保留。实际视频生成通过 `video_adapter.py` 中的 `DashScopeFilmProvider` 实现。

### 2.4 配置存储

| 配置项 | 文件 | 行号 |
|--------|------|------|
| `dashscope_api_key` 默认空字符串 | `config.py` | 107 |
| `video_provider` 默认为 dashscope | `config.py` | 138 |
| 敏感字段掩码 | `settings_manager.py` | 34, 38 |

---

## 3. 模型加载器

### 3.1 总览

| 模型 | 文件 | 显存需求 | 磁盘占用 | 下载源 |
|------|------|----------|----------|--------|
| DepthAnything V2 Large | `depth_loader.py` | ~1.5 GB | ~400 MB | HuggingFace Hub |
| Grounding DINO Base | `grounding_dino_loader.py` | ~3 GB | ~1.5 GB | HuggingFace Hub |
| SAM2 (vit_l) | `sam2_loader.py` | ~3 GB | ~1.5 GB | HuggingFace Hub + Meta CDN |
| Qwen3-VL-4B-Instruct | `qwen3vl_loader.py` | ~8 GB | ~8 GB (bf16) | HuggingFace Hub |
| LaMa (big-lama) | `lama_loader.py` | ~1 GB | ~200 MB | GitHub Release |
| Z-Image-Turbo | `z_image_loader.py` | ~6-10 GB | ~33 GB | HuggingFace Hub + ModelScope |

### 3.2 DepthAnything V2

**文件**: [backend/app/models/depth_loader.py](backend/app/models/depth_loader.py)

```python
self._processor = AutoImageProcessor.from_pretrained(model_name, local_files_only=...)
self._model = AutoModelForDepthEstimation.from_pretrained(model_name, local_files_only=...)
```

- **加载库**: `transformers`
- **精度**: 默认 float32
- **设备**: 自动 CUDA / CPU 降级
- **下载策略**: 两阶段（在线 → 本地缓存），无独立重试（依赖 transformers 内部处理）
- **输出**: HxW float32 归一化深度图（0-1，0=近，1=远）

### 3.3 Grounding DINO

**文件**: [backend/app/models/grounding_dino_loader.py](backend/app/models/grounding_dino_loader.py)

```python
self._processor = AutoProcessor.from_pretrained(model_name, trust_remote_code=True, ...)
self._model = AutoModelForZeroShotObjectDetection.from_pretrained(model_name, trust_remote_code=True, ...)
```

- **加载库**: `transformers`
- **关键参数**: `trust_remote_code=True`（必需，因有自定义后处理代码）
- **输出**: `Detection` dataclass，含 `box` / `label` / `score` / `object_id`

### 3.4 SAM2

**文件**: [backend/app/models/sam2_loader.py](backend/app/models/sam2_loader.py)

**模型规格**:

| 尺寸 | HuggingFace Repo | 显存 |
|------|------------------|------|
| `vit_l` | `facebook/sam2.1-hiera-large` | ~3 GB |
| `vit_b` | `facebook/sam2.1-hiera-base-plus` | ~2 GB |
| `vit_s` | `facebook/sam2.1-hiera-small` | ~1.5 GB |
| `vit_t` | `facebook/sam2.1-hiera-tiny` | ~1 GB |

**下载策略（三层）**：
1. HuggingFace Hub（经 hf-mirror.com，3 次重试 + 指数退避）
2. Meta CDN 直接下载（`https://dl.fbaipublicfiles.com/segment_anything_2/092824/`）
3. 本地缓存

**加载路径（两条）**：
1. **优先**: `ultralytics` 包装器（`SAM(weight_path)`）
2. **备选**: SAM2 官方 `build_sam2()` + `SAM2ImagePredictor`

**额外功能**: Canny 边缘精化、Mask 轮廓吸附（`refine_mask_edges()`）、多边形提取

### 3.5 Qwen3-VL-4B-Instruct

**文件**: [backend/app/models/qwen3vl_loader.py](backend/app/models/qwen3vl_loader.py)

```python
self._processor = AutoProcessor.from_pretrained(model_name, ...)
self._model = Qwen3VLForConditionalGeneration.from_pretrained(
    model_name,
    dtype=torch.bfloat16,   # bfloat16 节省显存
    local_files_only=...,
).to(self.device).eval()
```

- **加载库**: `transformers`
- **精度**: `torch.bfloat16`（节省约 50% 显存）
- **评估模式**: `.eval()` + `torch.no_grad()`
- **下载策略**: 两阶段（与 DepthAnything 相同）

### 3.6 LaMa（大图像修复）

**文件**: [backend/app/models/lama_loader.py](backend/app/models/lama_loader.py)

```python
from simple_lama_inpainting import SimpleLama
model = SimpleLama(checkpoint=os.path.join(checkpoint_dir, "big-lama.pt"))
```

- **下载源**: `https://github.com/enesmsahin/simple-lama-inpainting/releases/download/v0.1.0/big-lama.pt`
- **下载策略**: 直接 HTTP + 3 次重试 + 指数退避 + 断点续传
- **缓存查找顺序**: `backend/.cache/lama/` → `~/.cache/lama/` → glob 递归搜索
- **单例**: 模块级 `_lama_model` 全局变量（独立于 ModelManager）

### 3.7 Z-Image-Turbo（主图像生成模型）

**文件**: [backend/app/models/z_image_loader.py](backend/app/models/z_image_loader.py)

```python
local_dir = snapshot_download(repo_id="Tongyi-MAI/Z-Image-Turbo", cache_dir=..., allow_patterns=[...])
```

- **下载源**: HuggingFace Hub（经 hf-mirror.com）→ ModelScope 镜像
- **磁盘占用**: ~33 GB（transformer + text-encoder + VAE + scheduler + tokenizer）
- **只下载必要文件**: 跳过 `.msgpack`、`.h5`、`.onnx`、`.pt` 等非必要文件
- **ModelScope 镜像**: 若 HF Hub 失败，自动降级到 ModelScope 并复制到项目缓存目录
- **缓存完整性检查**: 验证 `transformer/`、`text_encoder/`、`vae/` 三个子目录都存在
- **单例**: 模块级 `_z_image_model` 全局变量（独立于 ModelManager）
- **注意**: `ZImageModel` 只负责下载，实际推理由 `LocalImageGenerator` 通过 `ZImagePipeline` 完成

---

## 4. 模型生命周期管理

**文件**: [backend/app/models/model_manager.py](backend/app/models/model_manager.py)

### 4.1 懒加载机制

每个模型通过 `@property` 实现首次访问才加载：

```python
@property
def depth_model(self) -> DepthModel:
    if self._depth is None:
        self.load_depth()
    return self._depth
```

管理的 6 个模型: `depth_model` / `grounding_dino` / `sam2` / `qwen3vl` / `lama_model` / `image_model`

### 4.2 管线"用完即弃"设计

```
POST /analyze 管线执行顺序:
1. DepthAnything → depth_map 提取后立即卸载
2. Qwen3-VL      → detected_classes 字符串列表拿到后立即卸载
3. Grounding DINO → boxes/scores numpy 提取后立即卸载
4. SAM2          → masks numpy 提取后立即卸载

管线结束显存峰值 ≈ Grounding DINO + SAM2 ≈ 4-7 GB
(vs 原来 16-22 GB 全量常驻)
```

### 4.3 卸载方法

每个 `unload_*` 方法执行两步：
1. 将模型引用置 `None`
2. 调用 `_clear_cuda_cache()` → `torch.cuda.empty_cache()` + `torch.cuda.synchronize()`

### 4.4 批量操作

| 方法 | 用途 |
|------|------|
| `load_all()` | `lazy_load=False` 时启动全量加载 |
| `unload_all()` | 服务关闭时释放全部显存 |
| `ensure_all_downloaded()` | 启动时预下载所有检查点到磁盘 |

### 4.5 模型状态查询

| 端点 | 功能 |
|------|------|
| `/health` | 返回 device / lazy_load / all_loaded / 各模型加载状态 / llm_alive |
| `/health/models` | 返回 all_ready / per-model 可用性 / missing list / download hints |

---

## 5. GPU 并发控制

**文件**: [backend/app/utils/gpu_concurrency.py](backend/app/utils/gpu_concurrency.py)

### 5.1 核心机制

```python
_MAX_CONCURRENT_GPU_JOBS = 2   # 硬上限
_GPU_SEM: Optional[asyncio.Semaphore] = None  # 进程级单例

def get_gpu_sem() -> asyncio.Semaphore:
    global _GPU_SEM
    if _GPU_SEM is None:
        _GPU_SEM = asyncio.Semaphore(_MAX_CONCURRENT_GPU_JOBS)
    return _GPU_SEM
```

### 5.2 设计背景

多个后台 worker（角色三视图、场景关键帧等）竞争同一 GPU，若各自持有信号量，叠加的 SDXL/Z-Image 请求可能超出 VRAM 引发 OOM。

### 5.3 容量校准

- **适用 GPU**: RTX 4060 Ti (16GB)
- **配额分配**: 2 个并行任务（1 角色 + 1 场景，或 2 个场景）
- **适用操作**: txt2img + img2img + inpaint 均计入同一配额

---

## 6. 启动与健康检查

**文件**: [backend/app/main.py](backend/app/main.py)

### 6.1 Lifespan 启动流程

```
1. 配置 LLM 客户端和图像生成器
2. 打印 GPU 基线显存状态 (vram_before_warmup)
3. 启动 llama-server (若未运行)
4. 启动 auto-unload 后台管理器
5. 执行 checkpoint 预下载 (ensure_all_downloaded)
6. 根据 lazy_load 决定:
   - True (默认):  仅做预下载，不加载模型到显存
   - False:        load_all() + warmup_image_generator()
7. yield — 服务运行中
8. 关闭: unload_all() + stop llama-server
```

### 6.2 健康检查端点

| 端点 | 路径 | 返回内容 |
|------|------|----------|
| `/health` | main.py:187-206 | device / lazy_load / all_loaded / models / llm_alive |
| `/health/models` | main.py:209-241 | all_ready / per-model 可用性 / missing / hints |

### 6.3 CUDA 诊断

启动时打印 GPU 名称、显存大小和 PyTorch CUDA 版本。若无 CUDA，输出警告并提示安装驱动。

### 6.4 路由注册

所有路由以 `/api/aicss` 为前缀：

| 路由 | 用途 |
|------|------|
| `endpoints_router` | 核心 AICSS 分析 |
| `projects_router` | 项目管理 |
| `sequence_router` | 序列管理 (v2) |
| `shots_router` | 镜头管理 (v2) |
| `script_router` | 剧本与运动 (v2) |
| `mesh_router` | 3D 网格导出 (v2) |
| `llm_router` | LLM 服务器 |
| `settings_router` | 设置 |

---

## 7. 快速参考

### 7.1 环境变量速查

| 环境变量 | 用途 | 默认值 |
|----------|------|--------|
| `DASHSCOPE_API_KEY` | DashScope API Key（视频生成必需） | 空 |
| `AICSS_DEVICE` | 推理设备 | `"cuda"` |
| `AICSS_LAZY_LOAD` | 是否懒加载 | `"true"` |
| `AICSS_WORKSPACE_DIR` | 工作空间根目录 | `backend/.workspace` |
| `HF_TOKEN` | HuggingFace Token | 空 |
| `HF_ENDPOINT` | HF Hub 地址 | `https://hf-mirror.com` |
| `HF_HUB_DOWNLOAD_TIMEOUT` | 下载超时（秒） | `600` |
| `SAM2_CHECKPOINT_DIR` | SAM2 缓存目录 | `backend/.cache/sam2` |
| `LAMA_DOWNLOAD_TIMEOUT` | LaMa 下载超时（秒） | `600` |
| `LAMA_DOWNLOAD_RETRIES` | LaMa 下载重试次数 | `3` |

### 7.2 模型显存占用

```
启动时（lazy_load=False）:
├── Z-Image-Turbo:      ~6-10 GB  ← 最大
├── Qwen3-VL-4B:        ~8 GB (bf16)
├── Grounding DINO:     ~3 GB
├── SAM2 (vit_l):       ~3 GB
├── DepthAnything:       ~1.5 GB
└── LaMa:               ~1 GB
总峰值: ~22-26 GB

管线执行时（用完即弃）:
├── Grounding DINO:     ~3 GB  ← 最重
├── SAM2 (vit_l):       ~3 GB
└── 峰值: ~6 GB  ← 节省 ~70% 显存
```

### 7.3 模型文件路径

```
backend/.cache/
├── huggingface/
│   └── hub/
│       ├── models--depth-anything--Depth-Anything-V2-Large-hf/
│       ├── models--IDEA-Research--grounding-dino-base/
│       └── models--Qwen--Qwen3-VL-4B-Instruct/
├── sam2/
│   ├── sam2.1_hiera_l.yaml
│   └── sam2.1_hiera_large.pt
├── lama/
│   └── big-lama.pt
└── z-image/
    └── hub/Tongyi-MAI--Z-Image-Turbo/snapshots/
```

### 7.4 首次部署清单

1. 安装 ffmpeg（帧提取必需，在 PATH 中）
2. 安装 Blender 4.x（3D 导出必需，4.2/4.1/4.0/3.6 均支持）
3. 设置 `DASHSCOPE_API_KEY`（视频生成必需）
4. 安装 CUDA 12.1+（GPU 推理推荐，CPU 可降级）
5. 运行后端：`python -m uvicorn app.main:app --reload`
6. 访问 Swagger UI: `http://localhost:8000/docs`
