# 3D 网格 FBX/GLB 导出 — 架构决策文档

> 撰写日期：2026-07-21
> 适用版本：v2.1
> 状态：✅ 已实施

---

## 一、问题陈述

将 Paper Diorama 场景中构建的 3D 层次结构（深度层 + 检测物体）导出为标准 3D 网格格式，供 Unity、Unreal Engine、Blender、Maya 等第三方软件进一步编辑或渲染。

**核心约束：**
- 后端服务环境（无 GPU 图形界面）
- 必须保留纸模纹理（paper_style / outlined / normal_map / thickness_gray）
- 必须保留几何体厚度（BoxGeometry 而非 PlaneGeometry）
- 必须支持 Unity/UE4 原生导入

---

## 二、关键数据转换节点

### 节点 1 — 前端 Store → API 请求

```
useAppStore（前端）
    │
    ├─ analysisResult.objects[]              ─┐
    ├─ depthLayerDioramaAssets{}             ─┤
    ├─ objectDioramaAssets{}                 ─┼─► ExportSceneRequest
    ├─ billboardOffsets{}                     ─┤
    └─ depthSplitResult{}                    ─┘
```

| 前端字段 | API 字段 | 类型 |
|---------|---------|------|
| `analysisResult` | `analysis_result` | `dict`（AicssResult JSON） |
| `depthLayerDioramaAssets` | `layer_assets` | `dict[str, DepthLayerDioramaAsset]` |
| `objectDioramaAssets` | `object_assets` | `dict[str, ObjectDioramaAsset]` |
| `billboardOffsets` | `billboard_offsets` | `dict[str, BillboardOffset]` |
| `depthSplitResult` | `depth_split_result` | `dict` |

### 节点 2 — API 请求 → Blender 场景数据

```
ExportSceneRequest
    │
    ├─ analysis_result.objects[]              ─┐
    ├─ layer_assets{}                         ─┤─► SceneExportData
    └─ billboard_offsets{}                    ─┘
```

| API 字段 | SceneExportData 字段 | Blender 表现 |
|---------|---------------------|-------------|
| `objects[]` | `objects: list[ObjectMeshData]` | `bpy.data.objects.new("Object_xxx")` |
| `layer_assets[fg/mg/bg/sky]` | `layers: list[LayerMeshData]` | `bpy.data.objects.new("Layer_xxx")` |
| `object_assets[id].rgbaUrl` | `obj.diffuse_texture` | Principled BSDF → Base Color |
| `billboardOffsets[id].offsetX/Z` | `obj.position` | `obj.location = (x, y, z)` |

### 节点 3 — 几何体参数映射

| 来源数据 | 参数 | Blender 值 |
|---------|------|-----------|
| 场景尺寸 | 层宽高 | `width=20.0, height=15.0` |
| bounding box | 物体宽高 | `bbox_w * 10, bbox_h * 7.5` |
| `layer_key` | 层 Z 位置 | sky=-20, bg=-12, mg=-6, fg=-2 |
| `depth_meters` | 物体深度 | `depth / 50 * 10 - 5` |
| `thickness_range` | 层厚度 | sky=0.08, bg=0.12, mg=0.20, fg=0.30 |
| — | 物体厚度 | 固定 `0.05`（可配置） |
| — | Bevel 宽度 | 固定 `0.005` |

### 节点 4 — 纹理处理决策

| 纹理类型 | 格式 | 处理方式 | Blender 加载 |
|---------|------|---------|-------------|
| `data:image/png;base64,...` | Base64 URL | **✅ 解码为临时 PNG** | `bpy.data.images.load(temp_png)` |
| `http://.../texture.png` | HTTP URL | **✅ 直接作为路径** | `bpy.data.images.load(http_path)` |
| 文件系统路径 | 绝对路径 | **✅ 直接作为路径** | `bpy.data.images.load(abs_path)` |
| 无纹理 | — | **✅ 纯几何体导出** | 无 Image Texture 节点 |

**决策依据：** Blender Headless 无法直接读取 `data:` URL，必须先写入磁盘。`_prepare_textures()` 统一处理此逻辑。

---

## 三、架构决策（5 项）

### 决策 1：导出工具选择

| 选项 | 优点 | 缺点 |
|------|------|------|
| Three.js GLTFExporter.js | 无外部依赖，速度快 | 无法导出 Bevel modifier；PBR 材质需手动构造 |
| **Blender Headless** | **完整 Principled BSDF + Bevel + 多材质** | **需安装 Blender** |
| pyransac (纯 Python) | 无外部依赖 | 不支持材质导出；复杂场景性能差 |

**最终决策：Blender Headless**

**理由：** Paper Diorama 的核心价值在于纸模材质（Diffuse + Normal + Bevel）。Three.js GLTFExporter 无法导出 Bevel modifier，pyransac 无法处理材质。Blender Headless `--background` 模式无需 GUI，适合服务端使用。

---

### 决策 2：Blender 脚本生成方式

| 选项 | 问题 |
|------|------|
| f-string `f'''...'''` | Blender 脚本内有 `f"Layer_{layer_key}"` 和 `{vert_map[vi]}`，Python 解析器在生成阶段将其作为 f-string 表达式求值，导致 `SyntaxError: empty expression` 或变量未定义错误 |
| `.format()` | 同理，`.format()` 模板中 `{expr}` 同样被求值 |
| **raw string `r'''...'''` + `.format()`** | **raw string 中所有 `{` 和 `}` 为字面值，`{{` 和 `}}` 才在 `.format()` 后变为 `{` 和 `}`，彻底隔离两层求值环境** |

**最终决策：raw string `r'''...'''` + `.format()`**

**理由：** 这是 Python 生成动态代码文本的标准技术，Blender 脚本本身包含 Python 语法（f-string 格式），必须与外层生成脚本的模板语法完全隔离。

**关键替换规则：**
```
模板中写         → .format() 后变为
─────────────────────────────────
{{ vert_map }}   → { vert_map }   （Blender 脚本中的 dict 变量）
{{{{"MESH"}}}}  → {"MESH"}       （Blender 脚本中的 set literal）
{unit_scale}    → 1.0             （外层模板变量，由 .format() 注入）
{scene_json}    → {"scene_id":...}（外层模板变量，由 .format() 注入）
```

---

### 决策 3：manifest 管理策略

| 选项 | 问题 |
|------|------|
| 复用 `manifest.json` | mesh 导出是独立 feature scope；与 ML 工件耦合会导致 manifest.json 膨胀；并发写入竞争风险 |
| **独立 `mesh_manifest.json`** | **mesh 与 ML 工件完全解耦；独立锁机制；职责清晰** |

**最终决策：独立 `meshes/mesh_manifest.json`**

**理由：** `project_store.py` 的 manifest 管理已有完整的事务模型（原子写入、per-project 锁）。mesh 导出作为新 feature，理应有独立的 manifest 和独立的锁，避免与现有端点产生写入竞争。

---

### 决策 4：主导出格式

| 选项 | 优点 | 缺点 |
|------|------|------|
| FBX 优先 | Unity/UE4/Maya 原生支持 | 文件大；跨版本兼容差；需要 FBX SDK |
| **GLB 优先，FBX 备选** | **文件更小（gltf binary）；无版本问题；Unity glTFast 插件原生支持；Blender 原生支持** | 部分传统 DCC 软件不支持 |

**最终决策：GLB 优先，FBX 作为兼容选项**

**理由：** GLB（glTF Binary）是 2020 年代跨平台 3D 资产的事实标准。Unity 通过 glTFast 插件可直接导入，UE4/Blender/Maya 原生支持。FBX 保留用于特殊场景（如骨骼动画、UV 通道传递）。

---

### 决策 5：纹理嵌入方式

| 选项 | 问题 |
|------|------|
| base64 内嵌到 GLB | GLB 支持嵌入二进制，但 Blender 的 glTF 导出器需要特殊参数 |
| 外部文件 + GLB 引用 | **✅ 最可靠，Blender 原生支持** |
| 分离文件 + 单独下载 | 需管理多个文件路径 |

**最终决策：外部临时文件（`_prepare_textures()` 统一解码 base64）**

**理由：** `_prepare_textures()` 在导出前将所有 base64 纹理解码到 `tempdir/textures/` 目录，然后以文件路径方式传递给 Blender。Blender 的 `bpy.ops.export_scene.gltf(export_materials="EXPORT")` 会自动将纹理嵌入 GLB 二进制。

---

## 四、API 端点设计决策

### 三种导出粒度的 scope 分工

| 端点 | scope | 粒度 | scene_id 规则 | 目标用户 |
|------|-------|------|---------------|---------|
| `POST /export-objects` | `object` | 每个检测到的物体 | `objects_<project>` | 需要单独处理每个物体时 |
| `POST /export-layers` | `layer` | 每个深度层 | `layers_<project>` | 只需背景层次时 |
| `POST /export-scene` | `scene` | 完整场景 | `scene_<project>` | **主要使用场景** |

**决策说明：** `scene` 是最常用场景（一次性导出完整纸模），但保留 `object` 和 `layer` 端点以支持精细化导出需求。

### `project_id` 可选设计

```json
// 有 project_id → 导出 + 持久化
{ "project_id": "xxx", ... }

// 无 project_id → 仅导出，临时文件在响应后丢弃
{ ... }
```

**决策依据：** 允许用户在不需要项目化管理时直接导出网格，提升灵活性。

---

## 五、持久化决策

### 原子写入流程

```
写入流程（与 project_store.py 完全一致）：
    1. 读取现有 manifest
    2. 追加新 MeshEntry
    3. 写入 <manifest>.json.tmp（临时文件）
    4. os.replace(tmp, manifest)  ← 原子替换
    5. 成功
```

**决策依据：** `os.replace()` 是跨平台的原子文件替换操作，避免在写入过程中（进程崩溃、断电）产生不完整的 manifest 文件。

### 文件名冲突解决

```
foreground.glb         → foreground.glb      （首个）
foreground.glb         → foreground_1.glb    （第 2 次）
foreground.glb         → foreground_2.glb    （第 3 次）
```

**决策依据：** 在 `save_mesh()` 中用 while 循环检测同名文件，加序号后缀，避免覆盖用户已有导出。

### per-project 锁机制

```python
_locks: dict[str, asyncio.Lock]  # 类变量，进程共享

async def _get_lock(project_id: str) -> asyncio.Lock:
    async with self._locks_lock:
        if project_id not in self._locks:
            self._locks[project_id] = asyncio.Lock()
        return self._locks[project_id]
```

**决策依据：** FastAPI 使用 asyncio，每个请求在独立协程中运行。多个并发请求操作同一项目的 mesh 时，`asyncio.Lock` 防止 manifest.json 读写竞争。

---

## 六、Blender 集成决策

### Blender 路径查找优先级

```
1. 环境变量 BLENDER_EXECUTABLE  （强制指定，适合非标准安装）
2. Windows Registry 查找         （Windows 官方安装程序注册表）
3. 常见安装路径扫描              （C:\Program Files\Blender Foundation\Blender 4.x）
4. 系统 PATH 中的 blender 命令   （Unix-like 系统）
```

**决策依据：** Blender 安装路径在不同操作系统、不同版本间差异极大，优先使用环境变量覆盖，其次通过多种策略自动探测，保证开箱即用。

### 导出参数决策

| 参数 | 值 | 理由 |
|------|---|------|
| `export_format` | `"GLB"` | 二进制 glTF，无需额外文件 |
| `export_yup` | `True` | Y-up 坐标系（Blender 默认），Unity/UE 兼容性好 |
| `export_animations` | `False` | 纸模场景无骨骼动画 |
| `export_lights/cameras` | `False` | 仅导出 mesh 和材质 |
| FBX `axis_forward` | `"-Z"` | Z-forward（UE 习惯） |
| FBX `axis_up` | `"Y"` | Y-up |

### 超时与错误处理

| 场景 | 处理 |
|------|------|
| Blender 未安装 | 返回 `MeshExportResult{success=False, error=...}`，不抛异常 |
| 导出超时（300s） | `subprocess.TimeoutExpired` → 返回错误响应 |
| 输出文件为空 | 检查文件大小 > 0，否则返回错误 |
| 脚本执行失败 | 捕获 stderr 输出，记录到 `MeshExportResult.error` |

---

## 七、数据模型决策

### ObjectMeshData 顶点数据

**BoxGeometry 参数：**
```
前端 boundingBox { x, y, w, h }
    │
    ▼
世界坐标转换：
    cx = (x + w/2) * scene_width   → obj.position.x
    cy = (1 - (y + h/2)) * scene_height → obj.position.y
    cz = depth_meters / 50 * 10 - 5 → obj.position.z
    size_x = w * scene_width         → box 宽度
    size_y = h * scene_height        → box 高度
    size_z = thickness               → box 厚度
```

### LayerMeshData Z 位置映射

| layer_key | Z 位置 | 层厚度 | 说明 |
|-----------|--------|--------|------|
| `sky` | -20.0 | 0.08 | 最远层 |
| `background` | -12.0 | 0.12 | 远景 |
| `midground` | -6.0 | 0.20 | 中景 |
| `foreground` | -2.0 | 0.30 | 近景（最厚，视觉最突出） |

**决策依据：** 纸模的视觉规律——近景物体通常最大最厚。用 `position_z` 差 6-8 个单位拉开层次，确保 Z-fighting 不会发生。

---

## 八、决策日志

| 日期 | 决策 | 变更原因 |
|------|------|---------|
| 2026-07-21 | Blender Headless 替代 Three.js GLTFExporter | Three.js 无法导出 Bevel modifier，无法满足纸模材质需求 |
| 2026-07-21 | raw string + .format() 替代 f-string | f-string 内嵌 Blender 脚本时 `{expr}` 冲突 |
| 2026-07-21 | 独立 mesh_manifest.json | 与 ML 工件 manifest 解耦，避免并发写入竞争 |
| 2026-07-21 | GLB 优先 | glTF 二进制是跨平台事实标准，Unity glTFast 原生支持 |
| 2026-07-21 | base64 解码为临时文件 | Blender Headless 不支持 data: URL |
