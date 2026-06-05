# AICSS Backend — 规格说明

本文档是 AICSS 后端的轻量参考说明。运行时的事实来源是：

- `backend/app/config.py`
- `backend/app/endpoints.py`
- `backend/app/main.py`

如果本文与代码冲突，请以代码为准。

---

## 概览

AICSS 后端是一个 FastAPI 推理服务，接收前端传入的图像数据，执行深度估计与分割流程，推导空间元数据，并将场景结构化结果返回给 UI。

---

## 运行时架构

```text
Frontend → FastAPI → Model Manager
                    ├── DepthAnything V2
                    ├── Grounding DINO
                    ├── SAM2
                    ├── DashScope VLM
                    └── DashScope Inpaint
```

---

## 有效 API 端点

除特别说明外，所有端点都挂载在 `/api/aicss` 下。

| 方法 | 路径 | 用途 |
|---|---|---|
| `POST` | `/analyze` | 完整管线 |
| `POST` | `/depth` | 仅生成深度图 |
| `POST` | `/segment` | 仅执行分割 |
| `POST` | `/layers` | 重建空间分层 |
| `POST` | `/scene-graph` | 重建场景图 |
| `POST` | `/billboard` | RGBA Billboard 切图 |
| `POST` | `/multiface` | 六面伪 3D 贴图生成 |
| `POST` | `/inpaint` | 基于 DashScope 的遮罩局部重绘 |
| `GET` | `/health` | 服务健康状态 |
| `GET` | `/` | 根路径服务元信息 |

---

## 请求说明

### `POST /api/aicss/analyze`

当前请求模型：

```json
{
  "imageUrl": "data:image/png;base64,...",
  "shotId": "shot_001",
  "apiKey": "your_dashscope_key"
}
```

说明：
- 当前请求结构中 `apiKey` 为必填。
- 响应中可能包含 `vlmDetectedClasses` 与 `vlmDetectedScene`。

### `POST /api/aicss/segment`

当前请求模型：

```json
{
  "imageUrl": "data:image/png;base64,...",
  "apiKey": "your_dashscope_key"
}
```

### `POST /api/aicss/layers`

当前请求模型：

```json
{
  "depthMap": "data:image/png;base64,...",
  "objects": [],
  "imageWidth": 1024,
  "imageHeight": 768
}
```

### `POST /api/aicss/inpaint`

当前请求模型：

```json
{
  "imageUrl": "data:image/png;base64,...",
  "maskDataUrl": "data:image/png;base64,...",
  "prompt": "remove the object and reconstruct the background",
  "apiKey": "your_dashscope_key"
}
```

说明：
- 只有在后端配置了 `AICSS_DASHSCOPE_API_KEY` 时，`apiKey` 才可以省略。

---

## 模型

| 模型 | 用途 | 运行时默认 |
|---|---|---|
| `depth-anything/Depth-Anything-V2-Large-hf` | 深度估计 | 启用 |
| `IDEA-Research/grounding-dino-base` | 目标检测 | 启用 |
| `SAM2` | 实例分割 | `AICSS_SAM2_MODEL_SIZE=vit_l` |
| DashScope 的 `Qwen-VL` | 场景与类别检测 | 在 analyze/segment 流程中使用 |
| DashScope 的 `wanx2.1-imageedit` | 遮罩局部重绘 | 用于 `/inpaint` |

---

## 深度分桶

当前 `app/config.py` 中的默认值：

| 层级 | 范围 |
|---|---|
| foreground | 0–5 |
| midground | 5–15 |
| background | 15–50 |
| sky | 50+ |

---

## 环境变量

后端统一使用 `AICSS_` 前缀。

| 变量 | 默认值 |
|---|---|
| `AICSS_HOST` | `0.0.0.0` |
| `AICSS_PORT` | `8000` |
| `AICSS_RELOAD` | `true` |
| `AICSS_DEVICE` | `cuda` |
| `AICSS_HF_TOKEN` | 空 |
| `AICSS_DEPTH_MODEL` | `depth-anything/Depth-Anything-V2-Large-hf` |
| `AICSS_GROUNDING_DINO_MODEL` | `IDEA-Research/grounding-dino-base` |
| `AICSS_SAM2_MODEL_SIZE` | `vit_l` |
| `AICSS_SEGMENTATION_PROMPT` | 内置回退字符串 |
| `AICSS_DASHSCOPE_API_KEY` | 空 |
| `AICSS_DASHSCOPE_MODEL` | `wanx2.1-imageedit` |
| `AICSS_DASHSCOPE_FUNCTION` | `description_edit_with_mask` |
| `AICSS_INPAINT_TIMEOUT` | `120` |

---

## 运行说明

- 启动时会通过 FastAPI lifespan 预加载模型
- 日志会写入 `backend/logs/aicss.log`
- 当前 CORS 对所有来源开放，便于开发调试
- 推荐使用 `python run.py` 启动后端

---

## 已知缺口

- 本文档是简化版参考，若后续不与代码同步维护，仍可能滞后于实现
- 当前没有部署或 Docker 规范
- 当前没有自动化测试契约说明
- `app/utils/inpaint_utils.py` 曾包含硬编码调试路径，这类问题需要持续清理
