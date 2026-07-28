# AICinematicSpatialSystem 项目完成度评估报告

> **项目目标**：基于纸雕（paper diorama）风格的 AI 自动化影视分镜生产系统。
>
> **目标输出**：一段约 3 分半的纸雕风格动画短片。
>
> **评估日期**：2026-07-27
>
> **评估范围**：对照用户提出的 11 个模块逐一评估实现状态。

---

## 一、总体进度概览

| 模块编号 | 模块名称 | 完成度 | 优先级 |
|:--------:|----------|:------:|:------:|
| 1 | 自动化剧本拆解 | 90% | - |
| 2 | 人物资产生成与动作提取 | 75% | P1 |
| 3 | 场景分层分割 | 85% | P1 |
| 4 | 遮挡区域补全与三维面片导出 | 70% | P2 |
| 5 | 文件整合与分镜归档 | 60% | P3 |
| 6 | Blender 场景自动搭建 | 40% | P0 |
| 7 | 纸张材质统一应用 | 50% | P2 |
| 8 | 环境与光照自动配置 | 30% | P2 |
| 9 | 场景运动与角色动画 | 25% | P2 |
| 10 | 镜头运镜与渲染输出 | 20% | P0 |
| 11 | 后期剪辑与成片 | 10% | P0 |

**综合完成度估算**：

- **已完成**：约 45%
- **进行中**：约 25%
- **未开始**：约 30%

---

## 二、各模块详细评估

### 模块 1：自动化剧本拆解 —— 90%

#### 能力矩阵

| 功能点 | 状态 | 实现文件 |
|--------|:----:|----------|
| 两段式 LLM 解析（规范化 → 结构化） | ✅ | `services/script_parser.py` |
| 多语言支持（中/英/日） | ✅ | `services/script_parser.py` |
| 角色提取（Character dataclass） | ✅ | `services/script_parser.py` |
| 场景提取（Scene dataclass） | ✅ | `services/script_parser.py` |
| 故事段落提取（StoryParagraph） | ✅ | `services/script_parser.py` |
| LLM 不可用时启发式 fallback | ✅ | `services/script_parser.py` |
| 分镜表生成（镜号/景别/运镜/动作/时长） | ✅ | `services/shot_generator.py` |
| 景别枚举（10 种） | ✅ | `services/shot_generator.py` |
| 运镜枚举（13 种） | ✅ | `services/shot_generator.py` |
| 场景视觉提示词生成 | ✅ | `services/scene_generator.py` |
| 人物动作提示词生成 | ✅ | `services/shot_generator.py` |
| 镜头运动提示词生成 | ✅ | `services/shot_generator.py` |
| 场景转换提示词生成 | ✅ | `services/shot_generator.py` |
| 人物动作序列提示词生成 | ✅ | `services/shot_generator.py` |
| 前端分镜表网格化展示 | ⚠️ | `components/ScriptEditor.tsx` |
| 网格化分镜表展示组件 | ❌ | - |

#### 缺口说明

1. **前端网格化展示组件缺失**：`ScriptEditor.tsx` 的 `StoryboardTab` 当前以 JSON 卡片列表形式展示分镜，缺少将分镜表渲染为视觉化网格的组件（类似电影分镜本的格子布局）。这是唯一阻止达到 100% 的缺口。

2. **缺少分镜预览图像**：分镜表目前只有文字描述，没有生成预览图像（shot thumbnail）。

#### API 端点状态

| 端点 | 方法 | 状态 |
|------|:----:|:----:|
| `/api/aicss/v2/scripts/parse` | POST | ✅ |
| `/api/aicss/v2/scripts/characters/extract` | POST | ✅ |
| `/api/aicss/v2/scripts/shots` | POST | ✅ |
| `/api/aicss/v2/scripts/scene-prompts` | POST | ✅ |
| `/api/aicss/v2/scripts/action-sequences` | POST | ✅ |
| `/api/aicss/v2/scripts/visual-prompt` | POST | ✅ |

---

### 模块 2：人物资产生成与动作提取 —— 75%

#### 能力矩阵

| 功能点 | 状态 | 实现文件 |
|--------|:----:|----------|
| 角色视觉提示词生成 | ✅ | `services/character_generator.py` |
| 角色参考图生成（wanx-v1） | ✅ | `services/character_generator.py` |
| 正面/侧面/背面三视图生成 | ✅ | `services/character_generator.py` |
| 自动三视图批量生成（脚本解析后） | ✅ | `services/auto_three_view.py` |
| 角色变体生成（wanx-v1-imageedit） | ✅ | `services/character_generator.py` |
| 动作视频生成（wan2.7-i2v） | ✅ | `services/motion_extractor.py` |
| 三种视频 Provider（dashscope/local_wan/svd） | ✅ | `services/video_adapter.py` |
| ffmpeg 帧提取 | ⚠️ | `services/motion_extractor.py` |
| SAM2 逐帧人物抠像 | ✅ | `services/motion_extractor.py` |
| PNG 序列帧导出（角色名_动作名_帧号） | ✅ | `services/motion_extractor.py` |
| **绿幕人物动作视频合成** | ❌ | - |
| 抠像后边缘羽化（feathering） | ⚠️ | 仅生成，未调用 |
| 首尾帧一致性检查 | ❌ | - |

#### 缺口说明

1. **绿幕功能完全缺失（核心缺口）**：当前视频生成 pipeline 生成的是自然场景中的人物动作视频，然后通过 SAM2 直接从自然背景中抠像。如果业务目标是"先让角色在纯绿幕环境中做动作，再分离出纯人物"，则需要新增绿幕合成步骤。`video_adapter.py` 中三个 Provider 均无 `greenscreen` / `chroma_key` 相关逻辑。

2. **边缘羽化未启用**：`sam2_loader.py` 中存在 `refine_mask_edges()` 函数（可做 Canny 边缘吸附），但 `motion_extractor.py` 未调用，导致抠像边缘偏硬。

3. **ffmpeg 外部依赖**：`extract_frames_from_video()` 依赖系统 PATH 中的 ffmpeg，若未安装则返回空列表而不抛异常。

---

### 模块 3：场景分层分割 —— 85%

#### 能力矩阵

| 功能点 | 状态 | 实现文件 |
|--------|:----:|----------|
| 场景图像生成（Z-Image-Turbo / SDXL） | ✅ | `services/image_generator.py` |
| Qwen3-VL 场景分类（4 类） | ✅ | `models/qwen3vl_loader.py` |
| Qwen3-VL 物体类别推断 | ✅ | `utils/vlm_utils.py` |
| Grounding DINO 目标检测 | ✅ | `models/grounding_dino_loader.py` |
| DepthAnything V2 深度估计 | ✅ | `models/depth_loader.py` |
| SAM2 自动分割 + 边缘贴合 | ✅ | `models/sam2_loader.py` |
| 遮挡关系推断（空间场景图） | ✅ | `utils/spatial_utils.py` |
| 深度层级分配（前景/中景/背景/天空） | ✅ | `utils/spatial_utils.py` |
| 前端多边形自由选区（PolygonDrawTool） | ✅ | `components/PolygonDrawTool.tsx` |
| **图层 PNG 导出端点** | ❌ | - |
| 前端自由选区导出到后端 | ⚠️ | 注释标注 TBD |
| 逐层剥离（strip-stack）PNG 导出 | ❌ | - |

#### 缺口说明

1. **图层 PNG 导出端点不存在**：虽然 `utils/spatial_utils.assign_to_depth_layer()` 可将物体分配到前景/中景/背景/天空层，但**没有 API 端点将每一层的可见区域从原图中裁剪出来并导出为独立 PNG 文件**。前端需要 `layer_foreground.png`、`layer_midground.png` 等用于 3D 重建。

2. **前端 PolygonDrawTool 选区未集成到导出管线**：`endpoints_mesh.py` 第 355-357 行注释明确标注："Full Blender integration (build PlaneGeometry per polygon at correct Z) is TBD"。

---

### 模块 4：遮挡区域补全与三维面片导出 —— 70%

#### 能力矩阵

| 功能点 | 状态 | 实现文件 |
|--------|:----:|----------|
| LaMa 图像修复模型 | ✅ | `models/lama_loader.py` |
| 图像修复（支持 RGBA/L 模式 mask） | ✅ | `utils/inpaint_utils.py` |
| 遮挡关系推理（场景图构建） | ✅ | `utils/spatial_utils.py` |
| FBX/GLB 导出（Blender Headless） | ✅ | `services/mesh_exporter.py` |
| 物体级 mesh 导出 | ✅ | `services/mesh_exporter.py` |
| 深度层 mesh 导出 | ✅ | `services/mesh_exporter.py` |
| 完整场景 mesh 导出 | ✅ | `services/mesh_exporter.py` |
| mesh 持久化服务 | ✅ | `services/project_store_mesh.py` |
| 层级固定厚度（0.08/0.12/0.20/0.30） | ✅ | `services/mesh_exporter.py` |
| 厚度纹理图生成（距离变换场） | ✅ | `utils/paper_diorama.py` |
| 法线贴图生成（Sobel 梯度） | ✅ | `utils/paper_diorama.py` |
| **精细像素级 Z 轴偏移（depthValue → Z）** | ⚠️ | 仅前端实现 |
| **厚度纹理用于非均匀几何厚度** | ❌ | - |
| **strip-stack 逐层剥离导出** | ❌ | - |

#### 缺口说明

1. **精细 Z 轴偏移未在后端实现**：`mesh_exporter.py` 使用 bucket 级别固定 Z 偏移（sky=-20, background=-12, midground=-6, foreground=-2），精细像素级 Z 偏移逻辑仅在 `frontend/src/utils/depthUtils.ts` 中实现，后端导出 Blender 时未使用 `depthValue` 做精细 Z 偏移。

2. **厚度纹理未用于几何厚度**：`paper_diorama.py` 生成的 `thicknessGrayUrl`（厚度纹理灰度图）只作为纹理贴图使用，不会改变 mesh 的实际几何厚度。`mesh_exporter.py` 中每个 layer 的 thickness 是固定值，无法生成非均匀厚度的几何体。

---

### 模块 5：文件整合与分镜归档 —— 60%

#### 能力矩阵

| 功能点 | 状态 | 实现文件 |
|--------|:----:|----------|
| 项目目录结构定义 | ✅ | `services/project_store.py` |
| v1 目录结构（图像分析类） | ✅ | `services/project_store.py` |
| v2 目录结构（剧本/分镜类） | ✅ | `services/project_store.py` |
| manifest.json 原子写入 | ✅ | `services/project_store.py` |
| per-project 并发锁 | ✅ | `services/project_store.py` |
| 角色资产持久化（front/side/back PNG） | ✅ | `services/project_store.py` |
| 动作序列持久化（JSON + 帧文件） | ✅ | `services/project_store.py` |
| **自动化归档脚本（场景名_镜号目录结构）** | ❌ | - |
| **Blender 导入包生成（shot 级别 ZIP）** | ❌ | - |

#### 缺口说明

当前 `project_store.py` 按 `project_id` 组织目录，缺少按"场景名_镜号"归类的中间层目录结构。Blender 插件需要的导入包（FBX + 角色帧序列 + 场景提示词打包）没有自动化生成脚本。

---

### 模块 6：Blender 场景自动搭建 —— 40%

#### 能力矩阵

| 功能点 | 状态 | 实现文件 |
|--------|:----:|----------|
| Blender Headless 导出服务 | ✅ | `services/mesh_exporter.py` |
| Blender 自动检测（4.2/4.1/4.0/3.6） | ✅ | `services/mesh_exporter.py` |
| 动态超时计算（60s–300s） | ✅ | `services/mesh_exporter.py` |
| Base64 纹理解码与临时文件管理 | ✅ | `services/mesh_exporter.py` |
| GLB 格式导出 | ✅ | `services/mesh_exporter.py` |
| FBX 格式导出 | ✅ | `services/mesh_exporter.py` |
| **Blender 独立 .py 插件文件** | ❌ | - |
| Blender 插件一键导入功能 | ❌ | - |
| 角色纸片自动放置到坐标 | ❌ | - |
| 场景层次关系自动构建 | ❌ | - |
| Blender Cycles 渲染测试 | ⚠️ | 未完整验证 |

#### 缺口说明

1. **最核心缺口**：当前导出通过 `subprocess` 调用系统 Blender Headless，**不是 Blender 内置插件**。没有 `backend/blender/` 目录或任何 `.py` 插件文件。Blender 用户无法以插件形式安装和使用系统功能。

2. Blender 脚本中材质节点仅支持 Diffuse/BaseColor + Normal Map，`Roughness=0.9, Specular=0.0` 硬编码，无用户可调参数。

---

### 模块 7：纸张材质统一应用 —— 50%

#### 能力矩阵

| 功能点 | 状态 | 实现文件 |
|--------|:----:|----------|
| 卡通化纹理（双边滤波 + k-means） | ✅ | `utils/paper_diorama.py` |
| 厚度/高度场生成（距离变换） | ✅ | `utils/paper_diorama.py` |
| 法线贴图生成（Sobel 梯度） | ✅ | `utils/paper_diorama.py` |
| 纸雕描边（外轮廓 + 内轮廓 + 投影） | ✅ | `utils/paper_diorama.py` |
| 前端纸雕材质预览（Three.js） | ✅ | `components/Viewer3D.tsx` |
| 前端纸张材质参数面板 | ✅ | `components/DioramaSettingsPanel.tsx` |
| **Blender 纸张材质节点组** | ⚠️ | `mesh_exporter.py` 中部分实现 |
| **次表面散射（SSS）效果** | ❌ | - |
| **纸张纤维法线贴图强度控制** | ❌ | - |
| **用户可调节粗糙度/SSS 参数** | ❌ | - |

#### 缺口说明

1. **Blender 材质节点不完整**：`mesh_exporter.py` 中的 `make_paper_material()` 仅构建了 `ImageTexture` → `Principled BSDF` 的基础连接。完整的纸张材质节点组应包括：
   - 法线贴图（Normal Map 节点）
   - 次表面散射（Subsurface Scattering）
   - 纸张纤维法线贴图叠加
   - 漫反射纹理基础色

2. **次表面散射缺失**：用户需求中明确提到"模拟纸张在侧光或逆光下的边缘透光感"，但当前实现无 SSS。

---

### 模块 8：环境与光照自动配置 —— 30%

#### 能力矩阵

| 功能点 | 状态 | 实现文件 |
|--------|:----:|----------|
| 前端硬编码三光源配置 | ✅ | `components/Viewer3D.tsx` |
| 情绪标签数据模型 | ✅ | `services/shot_generator.py` |
| 场景类型数据模型 | ✅ | `services/script_parser.py` |
| 天空盒/地面纹理库定义 | ⚠️ | 无资源库 |
| **自动光照方案生成** | ❌ | - |
| **光照参数可调面板** | ❌ | - |
| **Blender 光照配置脚本** | ❌ | - |

#### 缺口说明

1. **光照方案硬编码**：`Viewer3D.tsx` 中的 `PaperDioramaLighting` 组件只有硬编码的 3 个 `DirectionalLight`，无根据情绪/场景类型动态切换光照方案的逻辑。

2. **无资源库**：没有天空背景板库、地面纹理库供脚本选择和匹配。

3. **Blender 光照无配置**：导出到 Blender 的 Python 脚本中无光照设置代码。

---

### 模块 9：场景运动与角色动画 —— 25%

#### 能力矩阵

| 功能点 | 状态 | 实现文件 |
|--------|:----:|----------|
| 前端视差分层动画（depthLayerZ） | ✅ | `components/Viewer3D.tsx` |
| 前端轻微随机晃动效果 | ✅ | `components/Viewer3D.tsx` |
| PNG 序列帧导出（角色名_动作名_帧号） | ✅ | `services/motion_extractor.py` |
| 帧序列播放器（SequencePlayer） | ✅ | `components/sequence/SequencePlayer.tsx` |
| **角色纸片帧动画播放（Three.js）** | ⚠️ | 有播放器，无角色绑定 |
| **Blender 帧序列导入** | ❌ | - |
| **Blender 角色帧动画播放** | ❌ | - |
| **Blender 场景图层运动动画** | ❌ | - |

#### 缺口说明

1. **Three.js 角色帧动画未绑定到角色**：`SequencePlayer.tsx` 支持帧级播放控制，但没有与角色实体绑定播放对应动作帧序列的功能。

2. **Blender 角色帧动画完全缺失**：角色 PNG 序列帧导出后，没有导入 Blender 作为帧序列纹理或驱动角色动画的流程。

3. **Blender 场景运动动画缺失**：图层面片的"视差分层移动"和"随机晃动"效果未在 Blender 中实现。

---

### 模块 10：镜头运镜与渲染输出 —— 20%

#### 能力矩阵

| 功能点 | 状态 | 实现文件 |
|--------|:----:|----------|
| 景别枚举（10 种） | ✅ | `services/shot_generator.py` |
| 运镜枚举（13 种） | ✅ | `services/shot_generator.py` |
| 分镜运镜数据生成 | ✅ | `services/shot_generator.py` |
| Three.js 相机手动控制（OrbitControls） | ✅ | `components/Viewer3D.tsx` |
| **运镜数据 → Three.js 相机路径动画** | ❌ | - |
| **运镜数据 → Blender 摄影机动画** | ❌ | - |
| **Blender Cycles 离线渲染管线** | ⚠️ | 未验证 |
| **多镜头自动渲染输出** | ❌ | - |
| **渲染队列管理** | ❌ | - |

#### 缺口说明

1. **运镜信息仅作元数据**：分镜中的 `CameraMovement` 枚举值（13 种运镜方式）只存储在 Shot 数据结构中，**没有转换为 Three.js 的相机路径动画代码或 Blender 的摄影机关键帧**。

2. `OrbitControls` 仅支持手动交互，无自动运镜播放功能。

3. Blender Cycles 渲染引擎在实际运行中是否正常工作未经验证。

---

### 模块 11：后期剪辑与成片 —— 10%

#### 能力矩阵

| 功能点 | 状态 | 实现文件 |
|--------|:----:|----------|
| 静态图片导出（PNG/JPEG） | ✅ | `components/ExportPanel.tsx` |
| 3D Mesh 导出（GLB/FBX 下载） | ✅ | `services/meshExportService.ts` |
| 帧序列播放器 | ✅ | `components/sequence/SequencePlayer.tsx` |
| **视频拼接管线** | ❌ | - |
| **ffmpeg 视频合成** | ❌ | - |
| **转场效果（cut/dissolve/fade/wipe）** | ⚠️ | 数据模型存在，无渲染 |
| **时间线编辑器 UI** | ❌ | - |
| **音频轨（配音/BGM/音效）** | ❌ | - |
| **色彩统一调整** | ❌ | - |

#### 缺口说明

1. **最严重缺口**：整个后期剪辑管线完全未实现。没有将多个分镜视频/图像合成为完整电影的端到端流程。

2. `SceneTransition` 数据模型已定义（cut/dissolve/fade/wipe），但仅有提示词，无实际渲染效果实现。

3. 无时间线编辑器、多轨合成、音频处理等功能。

---

## 三、关键缺口优先级矩阵

### P0 — 阻塞性缺口（必须实现才能达到目标）

| 优先级 | 缺口 | 影响模块 | 建议方案 |
|:-------:|------|:--------:|----------|
| P0-1 | Blender 独立插件 | 模块 6 | 开发 `backend/blender/` 插件目录，提供 `.py` 插件文件 |
| P0-2 | 后期剪辑管线 | 模块 11 | 集成 FFmpeg 的视频拼接 + 转场渲染端到端流程 |
| P0-3 | 镜头运镜自动播放 | 模块 10 | 将 13 种 CameraMovement 枚举转换为 Three.js 相机路径 + Blender 摄影机关键帧 |

### P1 — 核心功能缺口（严重影响最终效果）

| 优先级 | 缺口 | 影响模块 | 建议方案 |
|:-------:|------|:--------:|----------|
| P1-1 | 绿幕人物动作视频 | 模块 2 | 在 video_adapter 中新增 greenscreen provider 或后处理步骤 |
| P1-2 | 图层 PNG 导出端点 | 模块 3 | 新增 `POST /api/aicss/layers/export` 端点，按深度层二值化分割原图 |
| P1-3 | 前端网格化分镜表展示 | 模块 1 | 开发 StoryboardGrid 组件，类似电影分镜本布局 |

### P2 — 质量增强缺口（提升最终效果）

| 优先级 | 缺口 | 影响模块 | 建议方案 |
|:-------:|------|:--------:|----------|
| P2-1 | 精细 Z 轴/厚度纹理 | 模块 4 | 改造 `mesh_exporter.py` Blender 脚本，利用 depthValue 精细偏移 + thickness_map 生成非均匀厚度 |
| P2-2 | Blender 完整材质节点 | 模块 7 | 扩展 `make_paper_material()` 增加 Normal Map + SSS 节点 |
| P2-3 | 光照配置面板 + Blender 光照脚本 | 模块 8 | UI 面板 + 动态生成 Blender 光照 Python 代码 |
| P2-4 | Blender 角色帧动画 | 模块 9 | 实现 Blender 帧序列导入和角色播放流程 |
| P2-5 | 抠像边缘羽化 | 模块 2 | 在 `motion_extractor.py` 中调用 `refine_mask_edges()` |

### P3 — 便利性缺口（提升用户体验）

| 优先级 | 缺口 | 影响模块 | 建议方案 |
|:-------:|------|:--------:|----------|
| P3-1 | 自动化分镜归档脚本 | 模块 5 | 开发 `scripts/archive_shot.py`，按"场景名_镜号"组织导出包 |
| P3-2 | 首尾帧一致性检查 | 模块 2 | 在 motion generate 端点增加 start_image / end_image 一致性验证 |

---

## 四、技术债务与已知问题

### 模型管理

| 问题 | 影响 | 状态 |
|------|------|------|
| Z-Image-Turbo 首次下载 33GB | 部署门槛高 | 已知 |
| Qwen3-VL-4B 需 ~8GB VRAM | 单卡部署限制 | 已知 |
| SAM2 vit_l checkpoint ~375MB | 加载时间 | 已知 |
| 模型懒加载机制 | 首次调用慢 | 已解决（lazy_load=True） |

### 外部依赖

| 依赖 | 用途 | 风险 |
|------|------|------|
| ffmpeg | 帧提取 | 必须安装，在 PATH 中 |
| Blender 4.x | 3D 导出 | 必须安装，支持 4.2/4.1/4.0/3.6 |
| DashScope API | LLM + 图像生成 | 云端，需 API Key |
| CUDA 12.1+ | GPU 推理 | 推荐，CPU 可降级 |

### 数据一致性

| 问题 | 位置 | 说明 |
|------|------|------|
| 厚度纹理未用于几何厚度 | `mesh_exporter.py` | `thicknessGrayUrl` 仅作纹理 |
| PolygonDrawTool 选区未集成导出 | `endpoints_mesh.py` L355-357 | TBD 标注 |
| strip-stack 导出未实现 | `mesh_exporter.py` | 注释标注 TBD |
| Blender Cycles 渲染未验证 | - | 实际运行未测试 |

---

## 五、推荐实施路线图

### 阶段一：核心贯通（约 2 周）

1. 实现图层 PNG 导出端点（模块 3）→ 打通 2D → 3D 管线
2. 开发 Blender 独立插件（模块 6）→ 打通 Blender 集成
3. 实现镜头运镜自动播放 Three.js（模块 10）→ 打通预览环节

### 阶段二：质量提升（约 2 周）

4. 完善 Blender 材质节点 + 光照配置（模块 7+8）
5. 实现精细 Z 轴偏移和厚度纹理（模块 4）
6. 开发前端网格化分镜表展示（模块 1）

### 阶段三：后期管线（约 2 周）

7. 开发后期剪辑管线（模块 11）→ 集成 FFmpeg 视频拼接
8. 实现 Blender 帧动画和运镜渲染（模块 9+10）
9. 自动化分镜归档脚本（模块 5）

### 阶段四：优化打磨（约 1 周）

10. 绿幕功能（如需要）
11. 抠像边缘羽化
12. 首尾帧一致性检查
13. 端到端联调测试

---

## 六、附录：模块依赖关系图

```
模块 1: 剧本拆解
    │
    ├──► 模块 2: 人物三视图 ──► 模块 9: 角色动画
    │         │
    │         └──► 模块 2: 动作视频 ──► 模块 3: 场景分层 ──► 模块 4: 补全导出
    │
    └──► 模块 5: 分镜归档 ──► 模块 6: Blender 插件 ◄──► 模块 7: 材质
                                  │
                                  └──► 模块 8: 光照

模块 6: Blender 插件 ──► 模块 9: 角色动画 ──► 模块 10: 运镜渲染
          │                          │
          └──► 模块 4: 图层 mesh ─────┘

模块 10: 运镜渲染 ──► 模块 11: 后期剪辑
```

---

*本报告基于 2026-07-27 代码库状态生成。*
