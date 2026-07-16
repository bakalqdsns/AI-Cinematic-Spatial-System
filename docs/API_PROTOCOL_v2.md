# AICSS API 协议规范

> AI Cinematic Spatial System API Protocol
> 版本：2.0.0
> 状态：草稿

---

## 目录

1. [概述](#一概述)
2. [基础类型](#二基础类型)
3. [v1 API - 单图分析](#三v1-api--单图分析)
4. [v1 API - 项目管理](#四v1-api--项目管理)
5. [v1 API - 图像生成](#五v1-api--图像生成)
6. [v2 API - 序列分析](#六v2-api--序列分析)
7. [v2 API - 镜头管理](#七v2-api--镜头管理)
8. [WebSocket 实时事件](#八websocket-实时事件)
9. [错误处理](#九错误处理)
10. [端点汇总](#十端点汇总)

---

## 一、概述

### 1.1 服务架构

```
┌─────────────────────────────────────────────────────────────┐
│                      AICSS Backend                          │
├─────────────────────────────────────────────────────────────┤
│  模型层                                                       │
│  ├── DepthAnything V2    — 深度估计                        │
│  ├── Grounding DINO      — 物体检测                        │
│  ├── SAM2                — 实例分割                        │
│  └── Qwen3-VL           — 视觉语言模型 (本地，无 API Key)   │
├─────────────────────────────────────────────────────────────┤
│  处理管道                                                     │
│  ├── /analyze           — 完整管道                         │
│  ├── /depth             — 仅深度估计                        │
│  ├── /segment           — 仅分割                           │
│  ├── /layers            — 构建空间层                       │
│  └── /scene-graph       — 构建场景图                       │
├─────────────────────────────────────────────────────────────┤
│  生成服务                                                     │
│  ├── /billboard         — RGBA 贴图                       │
│  ├── /multiface         — 6 面伪 3D 纹理                  │
│  ├── /inpaint           — 图像修复 (DashScope)             │
│  ├── /paper-style       — 纸艺风格化                      │
│  ├── /paper-diorama     — 物体纸艺                        │
│  └── /paper-layer       — 层级纸艺                        │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 版本策略

| 版本 | 前缀 | 说明 |
|------|------|------|
| v1 | `/api/aicss/` | 现有单图处理 API，保持兼容 |
| v2 | `/api/aicss/v2/` | 新增序列处理 API |

### 1.3 设计原则

1. **RESTful 风格**：标准 HTTP 方法和资源路径
2. **向后兼容**：v2 端点与 v1 共存
3. **统一响应**：可选的 `ApiResponse<T>` 包装
4. **无 API Key**：VLM 使用本地 Qwen3-VL，无需 DashScope Key

---

## 二、基础类型

### 2.1 通用类型

```typescript
// 时间戳
type Timestamp = string;  // ISO 8601: "2024-01-15T10:30:00Z"

// UUID
type UUID = string;  // "550e8400-e29b-41d4-a716-446655440000"

// 归一化坐标 (0-1)
type NormalizedFloat = number;

// 深度值 (米)
type DepthMeters = number;

// 状态
type Status = "pending" | "processing" | "completed" | "failed";

// 场景类型
type SceneType = "outdoor" | "indoor" | "night" | "nature";

// 深度层
type DepthLayerKey = "foreground" | "midground" | "background" | "sky";

// 关系类型
type RelationType = "leftOf" | "rightOf" | "inFrontOf" | "behind" | "above" | "below";
```

### 2.2 空间对象

```typescript
interface BoundingBox {
  x: NormalizedFloat;      // 左上角 x (0-1)
  y: NormalizedFloat;      // 左上角 y (0-1)
  w: NormalizedFloat;      // 宽度 (0-1)
  h: NormalizedFloat;      // 高度 (0-1)
}

interface PolygonPoint {
  x: NormalizedFloat;
  y: NormalizedFloat;
}

interface SpatialObject {
  id: string;                    // 物体 ID
  classLabel: string;            // 类别标签 (英文小写)
  depth: DepthMeters;            // 深度值 (米)
  boundingBox: BoundingBox;      // 归一化边界框
  maskDataUrl?: string;          // mask PNG (base64)
  polygon?: PolygonPoint[];       // 多边形顶点
  layer: DepthLayerKey;          // 所属深度层
  confidence?: number;           // 置信度 [0, 1]
}

interface SpatialLayer {
  id: string;                    // "layer_foreground_0"
  name: DepthLayerKey;           // 层名称
  zMin: DepthMeters;            // 层深度下限
  zMax: DepthMeters;            // 层深度上限
  objects: SpatialObject[];     // 该层包含的物体
}
```

### 2.3 深度层定义

```python
depth_buckets = [
    (0, 5, "foreground"),      # 近景 0-5米
    (5, 15, "midground"),      # 中景 5-15米
    (15, 50, "background"),    # 远景 15-50米
    (50, inf, "sky"),          # 天空 >50米
]
```

### 2.4 深度图格式

- 格式：灰度 PNG
- 像素值 0-255 → 深度 0-50米
- 计算公式：`depth_m = pixel_value * 50.0 / 255.0`

---

## 三、v1 API - 单图分析

### 3.1 完整分析管道

```
POST /api/aicss/analyze
Content-Type: application/json
```

**功能**：完整 AICSS 分析管道

1. 加载图像
2. DepthAnything V2 → 深度图
3. Qwen3-VL → 场景类型 + 物体类别
4. Grounding DINO + SAM2 → 物体检测 + 实例分割
5. 分配到空间深度层
6. 构建场景关系图

**请求体：**

```json
{
  "imageUrl": "string (必需) - 图像 URL 或 base64 data URL",
  "shotId": "string (必需) - 镜头 ID",
  "projectId": "string (可选) - 项目 ID，结果将持久化到 .workspace/projects/<id>/"
}
```

**响应：**

```json
{
  "analysisId": "string - 分析 ID",
  "depthMapUrl": "string - 深度图 (base64 PNG)",
  "objects": [
    {
      "id": "string",
      "classLabel": "string",
      "depth": 3.5,
      "boundingBox": {"x": 0.4, "y": 0.3, "w": 0.2, "h": 0.5},
      "maskDataUrl": "string (base64 PNG)",
      "polygon": [[0.4, 0.3], [0.6, 0.3], [0.6, 0.8], [0.4, 0.8]],
      "layer": "foreground"
    }
  ],
  "layers": [
    {
      "id": "layer_foreground_0",
      "name": "foreground",
      "zMin": 0.0,
      "zMax": 5.0,
      "objects": [...]
    }
  ],
  "sceneGraph": {
    "shotId": "string",
    "nodes": [
      {
        "id": "string",
        "classLabel": "string",
        "depth": 3.5,
        "layer": "foreground",
        "relations": [
          {"type": "leftOf", "targetId": "other_id"}
        ]
      }
    ]
  },
  "vlmDetectedClasses": ["person", "car", "tree"],
  "vlmDetectedScene": "outdoor",
  "savedArtifacts": ["depth/depth_map.png", "segment/objects.json", ...]
}
```

---

### 3.2 深度估计

```
POST /api/aicss/depth
Content-Type: application/json
```

**请求体：**

```json
{
  "imageUrl": "string (必需)",
  "projectId": "string (可选)"
}
```

**响应：**

```json
{
  "depthMapUrl": "string - 深度图 (base64 PNG)",
  "savedArtifacts": ["depth/depth_map.png"]
}
```

---

### 3.3 物体分割

```
POST /api/aicss/segment
Content-Type: application/json
```

**功能**：使用 Grounding DINO + SAM2 进行物体检测和分割

**请求体：**

```json
{
  "imageUrl": "string (必需)",
  "projectId": "string (可选)"
}
```

**响应：**

```json
{
  "objects": [
    {
      "id": "string",
      "classLabel": "string",
      "depth": 3.5,
      "boundingBox": {"x": 0.4, "y": 0.3, "w": 0.2, "h": 0.5},
      "maskDataUrl": "string",
      "polygon": [...],
      "layer": "foreground"
    }
  ],
  "savedArtifacts": ["segment/objects.json", "segment/mask_xxx.png", ...]
}
```

---

### 3.4 构建空间层

```
POST /api/aicss/layers
Content-Type: application/json
```

**请求体：**

```json
{
  "depthMap": "string (必需) - base64 编码的深度 PNG",
  "objects": "array (必需) - SpatialObject 列表",
  "imageWidth": 1024,
  "imageHeight": 768,
  "projectId": "string (可选)"
}
```

**响应：**

```json
{
  "layers": [
    {
      "id": "layer_foreground_0",
      "name": "foreground",
      "zMin": 0.0,
      "zMax": 5.0,
      "objects": [...]
    }
  ],
  "savedArtifacts": ["layers/layer_assignments.json"]
}
```

---

### 3.5 构建场景图

```
POST /api/aicss/scene-graph
Content-Type: application/json
```

**请求体：**

```json
{
  "shotId": "string (必需)",
  "objects": "array (必需) - SpatialObject 列表",
  "projectId": "string (可选)"
}
```

**响应：**

```json
{
  "sceneGraph": {
    "shotId": "string",
    "nodes": [
      {
        "id": "string",
        "classLabel": "string",
        "depth": 3.5,
        "layer": "foreground",
        "relations": [
          {"type": "leftOf", "targetId": "string"},
          {"type": "inFrontOf", "targetId": "string"}
        ]
      }
    ]
  },
  "savedArtifacts": ["scene/scene_graph.json"]
}
```

---

## 四、v1 API - 项目管理

### 4.1 创建项目 (multipart)

```
POST /api/aicss/projects
Content-Type: multipart/form-data
```

**表单字段：**

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| shotId | string | 是 | 镜头 ID |
| image | file | 是 | 原始图像文件 |
| imageWidth | int | 否 | 图像宽度 |
| imageHeight | int | 否 | 图像高度 |

**响应：**

```json
{
  "projectId": "string - 项目 ID",
  "shotId": "string",
  "createdAt": "2024-01-15T10:30:00Z",
  "inputHash": "string - 图像 SHA256",
  "imageWidth": 1920,
  "imageHeight": 1080
}
```

---

### 4.2 创建项目 (JSON)

```
POST /api/aicss/projects/json
Content-Type: application/json
```

**请求体：**

```json
{
  "shotId": "string (必需)",
  "imageBase64": "string (必需) - base64 编码的图像",
  "imageWidth": 1920,
  "imageHeight": 1080
}
```

**响应：** 同上

---

### 4.3 列出项目

```
GET /api/aicss/projects
```

**响应：**

```json
{
  "count": 5,
  "projects": [
    {
      "projectId": "string",
      "shotId": "string",
      "createdAt": "string",
      "inputHash": "string"
    }
  ]
}
```

---

### 4.4 获取项目 Manifest

```
GET /api/aicss/projects/{projectId}/manifest
```

**响应：**

```json
{
  "projectId": "string",
  "shotId": "string",
  "createdAt": "string",
  "steps": {
    "input": {...},
    "depth": {...},
    "segment": {...},
    "layers": {...},
    "scene": {...}
  },
  "artifacts": [...]
}
```

---

### 4.5 获取产物文件

```
GET /api/aicss/projects/{projectId}/artifacts/{step}/{filename}
```

**示例：** `GET /api/aicss/projects/proj_001/artifacts/depth/depth_map.png`

---

### 4.6 记录断点

```
POST /api/aicss/projects/{projectId}/checkpoint
Content-Type: application/json
```

**请求体：**

```json
{
  "phase": "string - 阶段名称",
  "startedAt": "ISO8601 时间戳",
  "finishedAt": "ISO8601 时间戳",
  "durationMs": 1500
}
```

**响应：**

```json
{
  "ok": true,
  "projectId": "string",
  "phase": "string"
}
```

---

### 4.7 删除项目

```
DELETE /api/aicss/projects/{projectId}
```

**响应：**

```json
{
  "ok": true,
  "projectId": "string",
  "deleted": true
}
```

---

## 五、v1 API - 图像生成

### 5.1 生成 RGBA 贴图

```
POST /api/aicss/billboard
Content-Type: application/json
```

**功能**：裁剪物体并生成带透明度的 RGBA 贴图

**请求体：**

```json
{
  "imageUrl": "string (必需)",
  "objectId": "string (必需)",
  "boundingBox": {
    "x": 0.4,
    "y": 0.3,
    "w": 0.2,
    "h": 0.5
  },
  "polygon": [
    [0.4, 0.3],
    [0.6, 0.3],
    [0.6, 0.8],
    [0.4, 0.8]
  ],
  "projectId": "string (可选)"
}
```

**响应：**

```json
{
  "billboardUrl": "string - RGBA PNG (base64)",
  "savedArtifacts": ["billboards/billboard_xxx.png"]
}
```

**说明**：`polygon` 优先于 `boundingBox`，多边形能精确跟随物体轮廓

---

### 5.2 生成 6 面伪 3D 纹理

```
POST /api/aicss/multiface
Content-Type: application/json
```

**功能**：生成 6 个方向的纹理用于伪 3D 效果

**请求体：** 同 `/billboard`

**响应：**

```json
{
  "faces": {
    "front": "string - 正面 (base64)",
    "back": "string - 背面 (水平翻转)",
    "left": "string - 左面 (逆时针90度)",
    "right": "string - 右面 (顺时针90度)",
    "top": "string - 顶面",
    "bottom": "string - 底面"
  },
  "savedArtifacts": [...]
}
```

---

### 5.3 图像修复 (Inpaint)

```
POST /api/aicss/inpaint
Content-Type: application/json
```

**功能**：使用 DashScope wanx2.1-imageedit 进行图像修复

**请求体：**

```json
{
  "imageUrl": "string (必需) - 原始图像",
  "maskDataUrl": "string (必需) - 修复掩码 (RGBA)",
  "prompt": "string (必需) - 修复描述",
  "apiKey": "string (可选) - DashScope API Key",
  "projectId": "string (可选)",
  "mode": "repair | restyle (可选，默认 repair)",
  "style": "string (可选) - 仅 restyle 模式使用"
}
```

**maskDataUrl 说明：**
- 白色 (alpha=255)：要编辑的区域
- 黑色 (alpha=0)：保留的区域

**mode 说明：**
- `repair`：保守修复，延续原图
- `restyle`：强风格迁移

**style 选项：**
`photographic`, `anime`, `oil painting`, `watercolor`, `sketch`, `3d cartoon`, `chinese painting`, `flat illustration`

**响应：**

```json
{
  "inpaintResultUrl": "string - 修复结果 (base64)",
  "mode": "repair",
  "function": "description_edit_with_mask",
  "maskWhiteRatio": 0.15,
  "effectivePrompt": "string",
  "warnings": [
    {
      "code": "small_mask",
      "reason": "Mask covers only 0.05% of the image...",
      "suggested": "..."
    }
  ]
}
```

---

### 5.4 纸艺风格化

```
POST /api/aicss/paper-style
Content-Type: application/json
```

**功能**：将照片转换为纸艺/插画风格

**请求体：**

```json
{
  "imageUrl": "string (必需)",
  "colorLevels": 12,
  "styleStrength": 0.7,
  "edgeLow": 50,
  "edgeHigh": 150,
  "projectId": "string (可选)"
}
```

**参数说明：**
- `colorLevels`：颜色量化级别 (3-30)，越小越扁平
- `styleStrength`：双边滤波强度 (0-1)
- `edgeLow`/`edgeHigh`：Canny 边缘检测阈值

**响应：**

```json
{
  "styledImageUrl": "string (base64 PNG)"
}
```

---

### 5.5 物体纸艺纹理

```
POST /api/aicss/paper-diorama
Content-Type: application/json
```

**功能**：为单个物体生成完整纸艺纹理集

**请求体：**

```json
{
  "imageUrl": "string (必需)",
  "maskDataUrl": "string (必需) - 物体掩码 (255=物体, 0=背景)",
  "thicknessMin": 1.0,
  "thicknessMax": 5.0,
  "outlineWidth": 3,
  "colorLevels": 12,
  "styleStrength": 0.7,
  "projectId": "string (可选)"
}
```

**响应：**

```json
{
  "paper_style_url": "string - 纸艺风格图 (base64)",
  "thickness_url": "string - 厚度图 (假彩色 PNG)",
  "normal_map_url": "string - 法线图",
  "outlined_url": "string - 描边图",
  "thickness_gray_url": "string - 灰度厚度图"
}
```

---

### 5.6 层级纸艺纹理

```
POST /api/aicss/paper-layer
Content-Type: application/json
```

**功能**：为整个深度层生成纸艺纹理

**请求体：**

```json
{
  "layerImageUrl": "string (必需) - 深度层图像 (RGBA PNG)",
  "layerMaskUrl": "string (可选) - 层级掩码",
  "thicknessMin": 1.0,
  "thicknessMax": 5.0,
  "outlineWidth": 3,
  "colorLevels": 12,
  "styleStrength": 0.7,
  "projectId": "string (可选)",
  "layerKey": "foreground | midground | background | sky (可选)"
}
```

**响应：** 同 `/paper-diorama`

---

## 六、v2 API - 序列分析

### 6.1 设计背景

处理的"帧"是**剧本生成的单场景帧**（非连续视频）：

```
剧本场景 ──生成──▶ 多个单场景帧
                     │
                     ├── 同一镜头的不同景别 (全景/中景/特写)
                     ├── 同一镜头的不同角度
                     └── 可能是 AI 生成的图像
```

### 6.2 追踪策略

```
┌─────────────────────────────────────────────────────────┐
│  追踪匹配策略                                           │
├─────────────────────────────────────────────────────────┤
│ 1. VLM 特征提取：Qwen3-VL 提取语义特征向量            │
│ 2. 语义一致性：类别标签匹配 + 场景类型约束              │
│ 3. IoU 校验：空间重叠度作为辅助校验                    │
│ 4. 多候选匹配：允许一个物体匹配多个候选                │
│ 5. 轨迹可视化：3D 视图中展示跨帧轨迹                  │
└─────────────────────────────────────────────────────────┘
```

### 6.3 分析图像序列

```
POST /api/aicss/v2/sequences
Content-Type: application/json
```

**请求体：**

```typescript
interface AnalyzeSequenceRequest {
  // --- 必需字段 ---
  shotId: string;                     // 镜头 ID
  frameIds: string[];               // 帧 ID 列表 (按顺序)
  imageUrls: string[];              // 图像 URL 列表

  // --- 可选字段 ---
  projectId?: string;                // 关联的项目 ID

  // --- 处理选项 ---
  enableTracking: boolean = true;     // 启用跨帧追踪
  trackingMode: TrackingMode = "vlm";  // 追踪模式

  // --- 帧元数据 (可选，由上游提供) ---
  frameTypes?: FrameType[];          // 每帧类型
  frameDescriptions?: string[];      // 每帧描述

  // --- 追踪配置 ---
  matchingThreshold: number = 0.6;   // 匹配阈值
  maxCandidatesPerObject: number = 5;

  // --- 扩展 ---
  metadata?: Record<string, any>;
}

type TrackingMode = "vlm" | "semantic" | "iou" | "hybrid";
type FrameType = "wide_shot" | "medium_shot" | "close_up" | "extreme_close_up" | "over_shoulder" | "pov" | "establishing";
```

**响应：**

```typescript
interface SequenceResult {
  // 基本信息
  sequenceId: string;
  shotId: string;
  projectId?: string;
  createdAt: string;
  frameCount: number;

  // 帧结果
  frames: FrameResult[];

  // 场景关联
  sceneLinks: SceneLink[];
  crossFrameObjects: CrossFrameObject[];

  // 处理统计
  metadata: SequenceMetadata;
}

interface FrameResult {
  frameId: string;
  frameIndex: number;
  frameType?: FrameType;

  depthMapUrl: string;
  objects: SpatialObject[];
  layers: SpatialLayer[];

  // 跨帧映射
  globalObjectIds: Record<string, string>;  // local_id -> global_id

  vlmScene?: SceneType;
  vlmClasses?: string[];
}

interface SceneLink {
  sourceFrameId: string;
  targetFrameId: string;
  linkType: SceneLinkType;
  confidence: number;
}

type SceneLinkType = "same_scene" | "same_character" | "continuity" | "contrast";

interface CrossFrameObject {
  globalId: string;
  classLabel: string;
  appearances: ObjectAppearance[];
}

interface ObjectAppearance {
  frameId: string;
  frameIndex: number;
  localId: string;
  bbox: BoundingBox;
  depth: DepthMeters;
  matchConfidence: number;
}

interface SequenceMetadata {
  totalProcessingTimeMs: number;
  framesProcessed: number;
  framesFailed: number;
  objectsTracked: number;
  trackingMode: TrackingMode;
}
```

---

### 6.4 从剧本场景分析

```
POST /api/aicss/v2/sequences/from-script
Content-Type: application/json
```

**请求体：**

```typescript
interface AnalyzeFromScriptRequest {
  shotId: string;
  scenes: ScriptScene[];
  projectId?: string;
  enableTracking?: boolean;
  trackingMode?: TrackingMode;
}

interface ScriptScene {
  sceneId: string;                   // 场景 ID
  frameId: string;                  // 帧 ID
  imageUrl: string;                 // 帧图像 URL
  sceneType?: FrameType;           // 帧类型
  description?: string;             // 帧描述
  characters?: string[];            // 出现的角色列表
  location?: string;                // 场景地点
  timeOfDay?: string;              // 时间 (day/night)
}
```

**响应：** 同 `SequenceResult`

---

### 6.5 获取场景关联图

```
GET /api/aicss/v2/sequences/{sequenceId}/scene-links
```

**响应：**

```typescript
interface SceneLinksResponse {
  sequenceId: string;
  shotId: string;
  frameLinks: FrameLink[];
  crossFrameObjects: CrossFrameObject[];
  statistics: {
    totalLinks: number;
    linksByType: Record<SceneLinkType, number>;
    uniqueObjects: number;
    averageAppearancesPerObject: number;
  };
}

interface FrameLink {
  sourceFrameId: string;
  targetFrameId: string;
  linkType: SceneLinkType;
  confidence: number;
  sharedObjects?: string[];
  sharedClasses?: string[];
}
```

---

### 6.6 获取跨帧物体详情

```
GET /api/aicss/v2/sequences/{sequenceId}/objects/{globalId}
```

**响应：**

```typescript
interface CrossFrameObjectDetail {
  globalId: string;
  classLabel: string;
  totalAppearances: number;
  appearances: ObjectAppearanceDetail[];
  trajectory: {
    positions: { frameId: string; x: number; y: number; depth: number }[];
    depthRange: [DepthMeters, DepthMeters];
    motionPattern: MotionPattern;
  };
  layerHistory: { frameId: string; layer: DepthLayerKey }[];
}

type MotionPattern = "static" | "slow" | "medium" | "fast" | "erratic";
```

---

## 七、v2 API - 镜头管理

### 7.1 创建镜头

```
POST /api/aicss/v2/projects/{projectId}/shots
Content-Type: application/json
```

**请求体：**

```json
{
  "shotId": "string (必需)",
  "description": "string (可选)",
  "sceneType": "string (可选)"
}
```

**响应：**

```json
{
  "shotId": "string",
  "projectId": "string",
  "createdAt": "string",
  "status": "pending"
}
```

---

### 7.2 列出镜头

```
GET /api/aicss/v2/projects/{projectId}/shots
```

**响应：**

```json
{
  "count": 3,
  "shots": [
    {
      "shotId": "string",
      "createdAt": "string",
      "status": "completed",
      "frameCount": 10
    }
  ]
}
```

---

### 7.3 获取镜头详情

```
GET /api/aicss/v2/projects/{projectId}/shots/{shotId}
```

**响应：**

```json
{
  "shotId": "string",
  "projectId": "string",
  "createdAt": "string",
  "updatedAt": "string",
  "status": "completed",
  "frameCount": 10,
  "artifacts": {
    "hasAnalysis": true,
    "hasSceneLinks": true,
    "hasCrossFrameObjects": true
  }
}
```

---

### 7.4 获取单帧

```
GET /api/aicss/v2/projects/{projectId}/shots/{shotId}/frames/{frameIndex}
```

**响应：**

```json
{
  "frameIndex": 0,
  "timestampMs": 0,
  "originalUrl": "string",
  "depthMapUrl": "string",
  "objects": [...],
  "layers": [...],
  "globalObjectIds": {...}
}
```

---

### 7.5 删除镜头

```
DELETE /api/aicss/v2/projects/{projectId}/shots/{shotId}
```

---

## 八、WebSocket 实时事件

### 8.1 连接

```
WS /api/aicss/v2/ws/sequences/{sequenceId}
```

### 8.2 事件类型

```typescript
// 连接成功
interface ConnectedEvent {
  type: "connected";
  sequenceId: string;
  totalFrames: number;
}

// 帧处理进度
interface FrameProgressEvent {
  type: "frame_progress";
  frameIndex: number;
  frameId: string;
  status: "started" | "completed" | "failed";
  processingTimeMs?: number;
  objectCount?: number;
}

// 追踪更新
interface TrackingUpdateEvent {
  type: "tracking_update";
  globalObjectId: string;
  classLabel: string;
  newAppearance: {
    frameId: string;
    frameIndex: number;
    matchConfidence: number;
  };
}

// 场景关联发现
interface SceneLinkDiscoveredEvent {
  type: "scene_link";
  sourceFrameId: string;
  targetFrameId: string;
  linkType: SceneLinkType;
  confidence: number;
  sharedObjects: string[];
}

// 序列完成
interface SequenceCompletedEvent {
  type: "completed";
  sequenceId: string;
  totalTimeMs: number;
  framesProcessed: number;
  objectsTracked: number;
}

// 错误
interface ErrorEvent {
  type: "error";
  code: string;
  message: string;
  frameIndex?: number;
}
```

---

## 九、错误处理

### 9.1 错误码定义

| 错误码 | HTTP 状态 | 说明 |
|--------|-----------|------|
| `VALIDATION_ERROR` | 400 | 请求参数校验失败 |
| `INVALID_IMAGE` | 400 | 图像格式错误 |
| `INVALID_FRAME_SEQUENCE` | 400 | 帧序列无效 |
| `SIZE_MISMATCH` | 400 | 图像尺寸不匹配 |
| `NOT_FOUND` | 404 | 资源不存在 |
| `PROJECT_NOT_FOUND` | 404 | 项目不存在 |
| `SHOT_NOT_FOUND` | 404 | 镜头不存在 |
| `SEQUENCE_NOT_FOUND` | 404 | 序列不存在 |
| `FRAME_NOT_FOUND` | 404 | 帧不存在 |
| `PROCESSING_ERROR` | 500 | 处理过程错误 |
| `MODEL_ERROR` | 500 | 模型推理错误 |
| `STORAGE_ERROR` | 500 | 存储操作失败 |
| `API_KEY_MISSING` | 503 | DashScope API Key 未配置 |
| `GPU_OOM` | 503 | GPU 显存不足 |
| `SERVICE_UNAVAILABLE` | 503 | 服务暂不可用 |

### 9.2 错误响应示例

```json
{
  "detail": "DashScope API key not configured. Pass apiKey in request body or set AICSS_DASHSCOPE_API_KEY env var."
}
```

---

## 十、端点汇总

### 10.1 v1 单图分析

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/aicss/analyze` | 完整分析管道 |
| POST | `/api/aicss/depth` | 深度估计 |
| POST | `/api/aicss/segment` | 物体分割 |
| POST | `/api/aicss/layers` | 构建空间层 |
| POST | `/api/aicss/scene-graph` | 构建场景图 |

### 10.2 v1 项目管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/aicss/projects` | 创建项目 (multipart) |
| POST | `/api/aicss/projects/json` | 创建项目 (JSON) |
| GET | `/api/aicss/projects` | 列出项目 |
| GET | `/api/aicss/projects/{projectId}/manifest` | 获取 Manifest |
| GET | `/api/aicss/projects/{projectId}/artifacts/{step}/{filename}` | 获取产物 |
| POST | `/api/aicss/projects/{projectId}/checkpoint` | 记录断点 |
| DELETE | `/api/aicss/projects/{projectId}` | 删除项目 |

### 10.3 v1 图像生成

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/aicss/billboard` | RGBA 贴图 |
| POST | `/api/aicss/multiface` | 6 面伪 3D 纹理 |
| POST | `/api/aicss/inpaint` | 图像修复 |
| POST | `/api/aicss/paper-style` | 纸艺风格化 |
| POST | `/api/aicss/paper-diorama` | 物体纸艺 |
| POST | `/api/aicss/paper-layer` | 层级纸艺 |

### 10.4 v2 序列分析

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/aicss/v2/sequences` | 分析图像序列 |
| POST | `/api/aicss/v2/sequences/from-script` | 从剧本分析 |
| GET | `/api/aicss/v2/sequences/{sequenceId}` | 获取序列详情 |
| GET | `/api/aicss/v2/sequences/{sequenceId}/scene-links` | 场景关联图 |
| GET | `/api/aicss/v2/sequences/{sequenceId}/objects/{globalId}` | 跨帧物体 |

### 10.5 v2 镜头管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/aicss/v2/projects/{projectId}/shots` | 创建镜头 |
| GET | `/api/aicss/v2/projects/{projectId}/shots` | 列出镜头 |
| GET | `/api/aicss/v2/projects/{projectId}/shots/{shotId}` | 镜头详情 |
| GET | `/api/aicss/v2/projects/{projectId}/shots/{shotId}/frames/{frameIndex}` | 单帧 |
| DELETE | `/api/aicss/v2/projects/{projectId}/shots/{shotId}` | 删除镜头 |

### 10.6 系统端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/` | 服务信息 |

---

## 附录：存储结构

```
.workspace/projects/
└── {projectId}/
    ├── manifest.json              # 项目索引
    │
    ├── input/                    # 原始输入
    │   └── original.png
    │
    ├── depth/                    # 深度图
    │   └── depth_map.png
    │
    ├── segment/                  # 分割结果
    │   ├── objects.json
    │   ├── mask_{obj_id}.png
    │   └── ...
    │
    ├── layers/                   # 空间层
    │   └── layer_assignments.json
    │
    ├── scene/                    # 场景图
    │   └── scene_graph.json
    │
    ├── billboards/               # RGBA 贴图
    │   └── billboard_{id}.png
    │
    ├── multiface/                # 多面纹理
    │   └── {id}_face_*.png
    │
    ├── inpaint/                  # 修复结果
    │   └── inpaint_*.png
    │
    └── paper/                    # 纸艺纹理
        ├── paper_style_*.png
        ├── thickness_*.png
        └── ...
```

---

## 实施状态

| 阶段 | 状态 | 说明 |
|------|------|------|
| 协议设计 | ✅ 完成 | v1 + v2 完整协议 |
| 后端实现 | 待开始 | |
| 前端实现 | 待开始 | |
