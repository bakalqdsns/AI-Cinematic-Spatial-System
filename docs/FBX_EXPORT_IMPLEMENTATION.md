# 3D 网格 FBX/GLB 导出 — 实施文档

> 本文档详细记录 AICSS 项目中 **3D 网格导出** 功能的完整实施细节，包括架构设计、数据模型、API 协议、导出规格和目录结构。
>
> 适用版本：v2.1（新增）
> 文档更新：2026-07-21

---

## 目录

1. [功能概述](#1-功能概述)
2. [架构设计](#2-架构设计)
3. [数据模型](#3-数据模型)
4. [API 完整索引](#4-api-完整索引)
5. [导出规格](#5-导出规格)
6. [目录结构](#6-目录结构)
7. [使用示例](#7-使用示例)
8. [Blender 依赖说明](#8-blender-依赖说明)
9. [故障排查](#9-故障排查)

---

## 1. 功能概述

### 1.1 目的

将 Paper Diorama 场景中构建的 3D 层次结构（深度层 + 检测物体）导出为标准 3D 网格格式，用于第三方 3D 软件（Unity、Unreal Engine、Blender、Maya）进一步编辑或渲染。

### 1.2 支持的导出粒度

| 粒度 | 说明 | 输出 |
|------|------|------|
| **Depth Layer（层级）** | 每个深度层（前景/中景/背景/天空）导出为独立 mesh | 4 个 mesh 文件 |
| **Object（对象）** | 每个检测到的物体导出为独立 mesh | N 个 mesh 文件 |
| **Scene（场景）** | 所有层和物体组合为完整场景 | 1 个 mesh 文件 |

### 1.3 支持的导出格式

| 格式 | MIME Type | 主要用途 | 纹理嵌入 |
|------|-----------|----------|----------|
| **GLB** (glTF Binary) | `model/gltf-binary` | **推荐** — 跨平台兼容性最好，文件更小 | 支持 |
| **FBX** (Filmbox) | `application/octet-stream` | Unity / Unreal Engine / Maya / 3ds Max | 支持 |

### 1.4 与现有导出的区别

| 导出类型 | 格式 | 内容 | 用途 |
|----------|------|------|------|
| PNG 截图 | `image/png` | WebGL 视口截图 | 预览 |
| 项目持久化 | PNG/JSON | 2D 图像资产 | 存档/恢复 |
| **3D Mesh 导出** | **GLB/FBX** | **3D 几何体 + 材质** | **Unity/UE/Blender 二次编辑** |

---

## 2. 架构设计

### 2.1 Blender Headless 导出架构

```
┌──────────────┐     POST /export-*      ┌───────────────────────┐
│   前端 React  │ ─────────────────────────►  FastAPI Endpoint     │
│  ExportPanel │                          │  endpoints_mesh.py    │
└──────────────┘                          └──────────┬────────────┘
                                                      │
                                                      ▼
┌──────────────┐  SceneExportData     ┌───────────────────────────┐
│  Viewer3D    │ ◄────────────────── │  mesh_exporter.py        │
│  useAppStore │  (layers + objects) │  · build_scene_from_*() │
└──────────────┘                      │  · _generate_blender_   │
      │                              │    script()             │
      │                              │  · export_scene()       │
      │                              └───────────┬─────────────┘
      │                                          │
      │  base64 textures (download if needed)    │ Blender Python script
      │                                          ▼
      │                              ┌───────────────────────────┐
      │                              │  Blender Headless        │
      │                              │  bpy.ops.export_scene.*  │
      │                              │  GLB / FBX output       │
      │                              └───────────┬─────────────┘
      │                                          │
      ▼                                          ▼
┌──────────────┐                      ┌───────────────────────────┐
│ useAppStore  │ ◄────────────────── │  project_store_mesh.py   │
│ (3D assets)  │  MeshExportResult    │  · save_object_mesh()    │
└──────────────┘                      │  · save_layer_mesh()     │
                                      │  · save_scene_mesh()     │
                                      └───────────┬─────────────┘
                                                  │
                                                  ▼
                                      ┌───────────────────────────┐
                                      │ .workspace/projects/<id>/│
                                      │   meshes/               │
                                      │   ├── mesh_manifest.json│
                                      │   ├── objects/<id>.glb  │
                                      │   ├── layers/<key>.glb │
                                      │   └── scenes/<id>.glb   │
                                      └───────────────────────────┘
```

### 2.2 数据流向

```
[前端 3D 场景数据]
        │
        ├── analysisResult.objects[]      → ObjectMeshData → Blender mesh
        ├── depthLayerDioramaAssets{}      → LayerMeshData → Blender mesh
        ├── objectDioramaAssets{}         → 纹理路径（Diffuse/Normal）
        ├── billboardOffsets{}             → Blender transform (position/rotation)
        └── depthSplitResult{}            → 深度分层 RGBA PNG
                   │
                   ▼
        [SceneExportData]
                   │
                   ▼
        [_generate_blender_script()]
                   │
                   ▼
        [Blender Python Script (临时文件)]
                   │
                   ▼
        [blender --background --python script.py -- output.glb]
                   │
                   ▼
        [GLB/FBX 二进制文件]
                   │
        ┌──────────┴──────────┐
        ▼                      ▼
  [临时目录]          [.workspace/.../meshes/]
                                  │
                                  ▼
                          [mesh_manifest.json]
```

### 2.3 Blender Python 脚本工作流

```
1. bpy.ops.object.delete()     清空默认场景
2. make_box_mesh()              为每个对象/层创建 BoxGeometry
3. make_paper_material()        为每个 mesh 创建 Principled BSDF 材质
4. bpy.ops.object.modifiers.new("BEVEL")  添加斜接（Bevel）模拟纸模边缘
5. bpy.ops.export_scene.gltf(export_format="GLB")  导出 GLB
   或
   bpy.ops.export_scene.fbx()                         导出 FBX
```

---

## 3. 数据模型

### 3.1 后端 Python 类型

**文件：** `backend/app/services/mesh_exporter.py`

```python
@dataclass
class Vertex:
    x: float
    y: float
    z: float

@dataclass
class ObjectMeshData:
    object_id: str
    class_label: str
    parent_layer: str           # foreground | midground | background | sky
    vertices: list[Vertex]     # 8 个顶点 (BoxGeometry)
    faces: list[Face]          # 12 个三角形 (2 per face × 6 faces)
    position: tuple[float, float, float]  # (x, y, z)
    rotation: tuple[float, float, float]  # Euler angles
    scale: tuple[float, float, float]    # (1, 1, 1) 默认
    diffuse_texture: Optional[str]   # base64 或文件路径
    normal_texture: Optional[str]
    thickness_texture: Optional[str]
    thickness: float = 0.05       # 纸模厚度 (world units)
    bevel_width: float = 0.005     # 斜接宽度

@dataclass
class LayerMeshData:
    layer_key: str            # foreground | midground | background | sky
    layer_name: str
    width: float = 20.0      # 场景宽度 (world units)
    height: float = 15.0      # 场景高度
    thickness: float           # 层厚度
    position_z: float         # Z 轴位置
    diffuse_texture: Optional[str]
    normal_texture: Optional[str]
    outlined_texture: Optional[str]
    bevel_width: float = 0.005

@dataclass
class SceneExportData:
    scene_id: str
    objects: list[ObjectMeshData]
    layers: list[LayerMeshData]
    textures_dir: Optional[str]    # 临时纹理目录
    output_format: str = "glb"    # glb | fbx
    include_textures: bool = True

@dataclass
class MeshExportResult:
    mesh_id: str
    file_path: str
    file_size: int
    file_sha256: str
    format: str                  # glb | fbx
    object_count: int
    vertex_count: int
    face_count: int
    success: bool
    error: Optional[str] = None
```

### 3.2 ProjectStoreMesh 类型

**文件：** `backend/app/services/project_store_mesh.py`

```python
@dataclass
class MeshArtifactFile:
    name: str           # "foreground.glb"
    size: int           # 字节数
    sha256: str        # SHA-256 内容哈希
    saved_at: str       # ISO 8601

@dataclass
class MeshEntry:
    mesh_id: str         # "mesh-a1b2c3d4"
    project_id: str
    scope: str           # "object" | "layer" | "scene"
    target_id: str       # object_id | layer_key | scene_id
    format: str          # "glb" | "fbx"
    file_name: str
    file_size: int
    file_sha256: str
    object_count: int
    vertex_count: int
    face_count: int
    include_textures: bool
    created_at: str

@dataclass
class MeshManifest:
    project_id: str
    meshes: list[MeshEntry]
    updated_at: str
```

### 3.3 前端 TypeScript 类型

**文件：** `frontend/src/services/meshExportService.ts`

```typescript
interface MeshExportResponse {
  mesh_id: string;
  scope: 'object' | 'layer' | 'scene';
  format: 'glb' | 'fbx';
  file_name: string | null;
  file_size: number | null;
  file_sha256: string | null;
  object_count: number;
  vertex_count: number;
  face_count: number;
  include_textures: boolean;
  success: boolean;
  error: string | null;
  blender_available: boolean;
  project_id: string | null;
  download_url: string | null;
}

interface MeshListItem {
  mesh_id: string;
  scope: string;
  target_id: string;
  format: string;
  file_name: string;
  file_size: number;
  created_at: string;
  download_url: string;
}

interface BlenderCheckResponse {
  available: boolean;
  path: string | null;
  version: string | null;
  message: string;
  error: string | null;
}
```

---

## 4. API 完整索引

### 4.1 Blender 可用性检查

**GET** `/api/aicss/v2/meshes/check`

```json
// Response 200
{
  "available": true,
  "path": "C:\\Program Files\\Blender Foundation\\Blender 4.2\\blender.exe",
  "version": "Blender 4.2.0",
  "message": "Blender is available for 3D mesh export"
}
```

### 4.2 导出检测到的物体

**POST** `/api/aicss/v2/meshes/export-objects`

```json
// Request
{
  "project_id": "optional",
  "analysis_result": { ... },          // AicssResult JSON
  "object_ids": ["obj-1", "obj-2"],      // 可选，None = 全部
  "object_assets": { "obj-1": { ... } }, // 可选，包含纹理
  "format": "glb",                       // glb | fbx
  "include_textures": true
}
// Response
{
  "mesh_id": "mesh-a1b2c3d4",
  "scope": "object",
  "format": "glb",
  "file_name": "objects_proj1.glb",
  "file_size": 524288,
  "file_sha256": "sha256:abc123...",
  "object_count": 5,
  "vertex_count": 2048,
  "face_count": 1024,
  "include_textures": true,
  "success": true,
  "error": null,
  "blender_available": true,
  "project_id": null,
  "download_url": "/api/aicss/v2/meshes/mesh-a1b2c3d4/download"
}
```

### 4.3 导出深度分层

**POST** `/api/aicss/v2/meshes/export-layers`

```json
// Request
{
  "project_id": "optional",
  "layer_assets": {
    "foreground": { "rgbaUrl": "...", "outlinedUrl": "...", "normalMapUrl": "..." },
    "midground": { ... },
    "background": { ... },
    "sky": { ... }
  },
  "format": "glb",
  "include_textures": true
}
// Response — 同上，scope: "layer"
```

### 4.4 导出完整场景

**POST** `/api/aicss/v2/meshes/export-scene`

```json
// Request
{
  "project_id": "optional",
  "analysis_result": { ... },            // AicssResult
  "depth_split_result": { ... },        // 前端 splitDepthLayers() 结果
  "layer_assets": { ... },               // depthLayerDioramaAssets
  "object_assets": { ... },              // objectDioramaAssets
  "billboard_offsets": { ... },          // 物体 3D 偏移
  "format": "glb",
  "include_textures": true
}
// Response — 同上，scope: "scene"
```

### 4.5 列出已导出的 mesh

**GET** `/api/aicss/v2/meshes/list?project_id=<pid>`

```json
// Response 200
{
  "meshes": [
    {
      "mesh_id": "mesh-a1b2c3d4",
      "scope": "layer",
      "target_id": "foreground",
      "format": "glb",
      "file_name": "foreground.glb",
      "file_size": 2097152,
      "object_count": 1,
      "vertex_count": 24,
      "created_at": "2026-07-21T13:00:00.000Z",
      "download_url": "/api/aicss/v2/meshes/mesh-a1b2c3d4/download"
    }
  ]
}
```

### 4.6 获取 mesh 元数据

**GET** `/api/aicss/v2/meshes/{mesh_id}/info?project_id=<pid>`

```json
// Response 200 — 包含完整 MeshEntry 字段
```

### 4.7 下载 mesh 文件

**GET** `/api/aicss/v2/meshes/{mesh_id}/download?project_id=<pid>`

- 返回：`model/gltf-binary`（GLB）或 `application/octet-stream`（FBX）
- 文件名：`Content-Disposition: attachment; filename=<file_name>`

### 4.8 删除 mesh 导出

**DELETE** `/api/aicss/v2/meshes/{mesh_id}?project_id=<pid>`

```json
// Response 200
{ "deleted": true, "mesh_id": "mesh-a1b2c3d4" }
```

---

## 5. 导出规格

### 5.1 几何体规格

| 属性 | 规格 |
|------|------|
| 几何体类型 | BoxGeometry（6 面体） |
| 顶点坐标系统 | Y-up，Blender 默认坐标系 |
| 场景坐标系 | X: -10 ~ +10, Y: -7.5 ~ +7.5（对应场景 20×15 世界单位） |
| 深度范围 | 0-50m → Z: -5 ~ +5 世界单位 |
| 层 Z 位置 | sky=-20, background=-12, midground=-6, foreground=-2 |
| 层厚度 | sky=0.08, background=0.12, midground=0.20, foreground=0.30（世界单位） |
| 物体厚度 | 默认 0.05（可配置） |
| Bevel（斜接） | 宽度 0.005，segments=2，ANGLE 限制 |
| 法线 | 自动计算（Blender 默认） |
| UV 坐标 | Blender 自动生成（正面 UV） |

### 5.2 材质规格

| 材质通道 | Blender 节点 | 纹理来源 |
|---------|-------------|----------|
| **Base Color (Diffuse)** | Principled BSDF → Base Color | `paperStyleUrl` / `outlinedUrl` / `rgbaUrl` |
| **Normal Map** | Image Texture (Non-Color) → Normal Map → Normal | `normalMapUrl` |
| **Roughness** | Principled BSDF → Roughness | 固定 0.9（哑光纸面效果） |
| **Specular** | Principled BSDF → Specular IOR Level | 固定 0.0（无高光） |
| **Displacement** | 未实现（可用 thickness_gray 替代） | — |

### 5.3 纹理处理规格

| 纹理类型 | 格式 | 处理方式 |
|---------|------|----------|
| Base64 data URL | PNG/JPG | 解码后写入临时文件，Blender 加载文件路径 |
| HTTP/HTTPS URL | PNG/JPG | 直接作为文件路径传递给 Blender |
| 文件路径 | PNG/JPG | 直接传递 |
| embedded in mesh | — | GLB/FBX 格式内置 |

### 5.4 坐标系和缩放约定

| 软件 | 轴向 | 缩放 |
|------|------|------|
| Blender（导出源） | Y-up | 1.0 |
| GLB/FBX（中间格式） | Y-up 或 Z-up（可选） | 1.0 |
| Unity | Y-up | 1.0（GLB 默认），需要手动调整 |
| Unreal Engine | Z-up | 需要在导入时设置 |
| Maya | Y-up | 1.0（FBX 默认） |

**导出参数：**
- GLB: `export_yup=True`（Y-up）
- FBX: `axis_forward="-Z"`, `axis_up="Y"`（Z-forward, Y-up）

### 5.5 输出文件规格

| 属性 | GLB | FBX |
|------|-----|-----|
| 格式类型 | Binary glTF 2.0 | Binary FBX 7.x |
| 纹理嵌入 | 支持（通过 GLB 二进制） | 支持（通过 `embed_textures`） |
| 材质 | PBR（Principled BSDF） | PBR / Standard |
| 动画 | 不支持（`export_animations=False`） | 不支持 |
| 相机 | 不导出 | 不导出 |
| 灯光 | 不导出 | 不导出 |
| 典型文件大小 | 100KB - 5MB | 200KB - 10MB |

---

## 6. 目录结构

### 6.1 meshes/ 目录

```
.workspace/projects/<project_id>/
├── manifest.json                  ← ProjectStore 主索引（ML 工件）
│
├── meshes/                        ← 3D mesh 导出（ProjectStoreMesh 管理）
│   ├── mesh_manifest.json        ← mesh 导出索引（独立于主 manifest）
│   ├── objects/
│   │   ├── obj-001.glb
│   │   ├── obj-002.glb
│   │   └── obj-001.fbx
│   ├── layers/
│   │   ├── foreground.glb
│   │   ├── midground.glb
│   │   ├── background.glb
│   │   ├── sky.glb
│   │   └── foreground.fbx
│   └── scenes/
│       ├── scene_001.glb
│       └── full_scene.fbx
│
├── depth/
├── masks/
├── paper/
└── ...
```

### 6.2 mesh_manifest.json 结构

```json
{
  "projectId": "20260721_143200_shot-1",
  "meshes": [
    {
      "mesh_id": "mesh-a1b2c3d4",
      "project_id": "20260721_143200_shot-1",
      "scope": "layer",
      "target_id": "foreground",
      "format": "glb",
      "file_name": "foreground.glb",
      "file_size": 2097152,
      "file_sha256": "sha256:abc123def456...",
      "object_count": 1,
      "vertex_count": 24,
      "face_count": 12,
      "include_textures": true,
      "created_at": "2026-07-21T13:00:00.000Z",
      "error": null
    }
  ],
  "updated_at": "2026-07-21T13:00:00.000Z"
}
```

---

## 7. 使用示例

### 7.1 前端调用示例

```typescript
import {
  checkBlenderAvailable,
  exportMeshLayers,
  exportMeshScene,
  downloadMeshFile,
} from '../services/meshExportService';
import { useAppStore } from '../store/useAppStore';

// 检查 Blender 可用性
const blender = await checkBlenderAvailable();
if (!blender.available) {
  alert('请安装 Blender 以导出 3D mesh\n' + blender.message);
  return;
}

// 导出深度层
const result = await exportMeshLayers({
  project_id: 'my-project-001',
  layer_assets: depthLayerDioramaAssets,
  format: 'glb',
  include_textures: true,
});

if (result.success) {
  // 自动下载
  downloadMeshFile(result.mesh_id, 'my-project-001', result.file_name);
} else {
  console.error('导出失败:', result.error);
}

// 导出完整场景
const sceneResult = await exportMeshScene({
  project_id: 'my-project-001',
  analysis_result: analysisResult,
  depth_split_result: depthSplitResult,
  layer_assets: depthLayerDioramaAssets,
  object_assets: objectDioramaAssets,
  billboard_offsets: billboardOffsets,
  format: 'fbx',  // Unity 推荐 FBX
  include_textures: true,
});
```

### 7.2 后端直接调用示例

```python
from app.services.mesh_exporter import (
    export_objects_only,
    export_layers_only,
    export_full_scene,
    check_blender_available,
)
from app.services.project_store_mesh import project_store_mesh

# 检查可用性
blender_info = check_blender_available()
print(blender_info)

# 仅导出深度层
result = export_layers_only(
    layer_assets=layer_assets,
    output_format="glb",
    include_textures=True,
)
print(f"导出成功: {result.success}, 文件: {result.file_path}")

# 持久化到项目
if result.success:
    entry = await project_store_mesh.save_layer_mesh(
        project_id="my-project",
        layer_key="foreground",
        mesh_data=Path(result.file_path).read_bytes(),
        format="glb",
        object_count=result.object_count,
        vertex_count=result.vertex_count,
        face_count=result.face_count,
    )
    print(f"已保存: {entry.mesh_id}")
```

### 7.3 导出完整场景到 Unity

```python
# Unity 导入建议：
# 1. 导出时使用 GLB 格式（Unity glTFast 插件直接支持）
# 2. 或使用 FBX 格式（Unity 内置支持）
result = export_full_scene(
    analysis_result=analysis_result,
    layer_assets=layer_assets,
    object_assets=object_assets,
    output_format="glb",
    include_textures=True,
)

# Unity 导入设置：
# - Scale Factor: 1.0
# - Generate Colliders: False
# - Animation Type: None
# - Import Materials: Import and Detect
```

---

## 8. Blender 依赖说明

### 8.1 系统要求

| 要求 | 规格 |
|------|------|
| 最低版本 | Blender >= 3.0（LTS 推荐 3.6 或 4.x） |
| 磁盘空间 | ~300MB（基础安装）|
| 内存 | 2GB+（场景复杂度相关） |
| 操作系统 | Windows 10+, macOS 10.15+, Ubuntu 20.04+ |

### 8.2 安装说明

#### Windows

1. 下载：https://www.blender.org/download/
2. 安装到默认路径：`C:\Program Files\Blender Foundation\Blender 4.x\`
3. **添加到 PATH**（可选，用于 `blender` 命令行）：
   - 设置 → 系统 → 关于 → 高级系统设置 → 环境变量
   - 在 `Path` 中添加 `C:\Program Files\Blender Foundation\Blender 4.2\`
4. 验证：`blender --version`

#### macOS

```bash
brew install --cask blender
# 验证
blender --version
```

#### Linux (Ubuntu/Debian)

```bash
sudo apt install blender
# 或从 https://www.blender.org/download/ 下载 .tar.xz
```

### 8.3 环境变量配置

| 环境变量 | 说明 | 示例 |
|----------|------|------|
| `BLENDER_EXECUTABLE` | 强制指定 Blender 路径 | `C:\Program Files\Blender 4.2\blender.exe` |
| `BLENDER_USER_SCRIPTS` | Blender 用户脚本目录 | `~/.config/blender/4.2/scripts` |

### 8.4 Headless 模式说明

Blender Headless 模式（`blender --background`）：
- 不显示 GUI 窗口
- 适合服务器/自动化环境
- 支持完整 Python API
- GPU 渲染需要额外配置（NVIDIA GPU Cycles）
- Eevee 渲染在 Headless 下可能有限制

---

## 9. 故障排查

### 9.1 Blender 不可用

**症状**：`checkBlenderAvailable()` 返回 `available: false`

**检查项：**
1. Blender 是否已安装？运行 `blender --version` 验证
2. 是否已添加到系统 PATH？
3. `BLENDER_EXECUTABLE` 环境变量是否正确设置？

**解决：**
```bash
# Windows PowerShell
$env:BLENDER_EXECUTABLE = "C:\Program Files\Blender Foundation\Blender 4.2\blender.exe"

# 或添加到系统环境变量后重启后端服务
```

### 9.2 导出超时

**症状**：导出请求返回 `error: "Blender export timed out after 300 seconds"`

**原因**：
- 场景过大（超过 1000 个物体）
- 纹理文件过大或网络下载缓慢
- 系统资源不足

**解决：**
1. 减少导出对象数量（使用 `object_ids` 过滤）
2. 先完成纹理下载到本地
3. 增加超时时间（修改 `subprocess.run(timeout=300)`）

### 9.3 纹理未正确加载

**症状**：导出的 mesh 没有纹理

**原因**：
- base64 data URL 无法被 Blender 直接读取
- HTTP URL 防火墙阻止

**解决**：
- `_prepare_textures()` 自动将 base64 解码为临时 PNG 文件
- 确保 Blender 进程有磁盘写入权限
- 检查 Blender stderr 日志输出

### 9.4 FBX 导出在 Unity 中有问题

**症状**：FBX 导入 Unity 后模型倒置或缩放异常

**解决**：
1. 使用 GLB 格式替代（Unity glTFast 插件兼容性更好）
2. 或在 Blender 导出时调整轴向设置
3. Unity 导入时设置：
   - Scale Factor: 100（如果场景使用米制单位）
   - Animation Type: None

### 9.5 文件名冲突

**症状**：同名 mesh 文件被覆盖

**解决**：`project_store_mesh.py` 中的 `save_mesh()` 已实现自动序号：

```
foreground.glb      → foreground.glb
foreground.glb      → foreground_1.glb
foreground.glb      → foreground_2.glb
```

---

## 附录：API 方法对应关系

| API 端点 | MeshExporter 函数 | ProjectStoreMesh 方法 |
|----------|-----------------|---------------------|
| POST /export-objects | `export_objects_only()` | `save_object_mesh()` |
| POST /export-layers | `export_layers_only()` | `save_layer_mesh()` |
| POST /export-scene | `export_full_scene()` | `save_scene_mesh()` |
| GET /list | — | `list_mesh_exports()` |
| GET /{id}/info | — | `get_mesh_export_info()` |
| GET /{id}/download | — | `get_mesh_file_path()` |
| DELETE /{id} | — | `delete_mesh_export()` |
