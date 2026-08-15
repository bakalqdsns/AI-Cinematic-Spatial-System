# AICinematicSpatialSystem 项目完成度评估报告

> **项目目标**：基于纸雕（paper diorama）风格的 AI 自动化影视分镜生产系统。
>
> **目标输出**：一段约 3 分半的纸雕风格动画短片。
>
> **评估日期**：2026-08-10（耦合度分析基于 2026-08-10；功能评估基于 2026-08-09）
>
> **评估范围**：对照用户提出的 11 个模块 + 模型管理与运行时配置（新增）逐一评估实现状态。

---

## 一、总体进度概览

| 模块编号 | 模块名称 | 完成度 | 优先级 |
|:--------:|----------|:------:|:------:|
| 1 | 自动化剧本拆解 | 95% | - |
| 2 | 人物资产生成与动作提取 | 80% | P1 |
| 3 | 场景分层分割 | 85% | P1 |
| 4 | 遮挡区域补全与三维面片导出 | 70% | P2 |
| 5 | 文件整合与分镜归档 | 80% | P3 |
| 6 | Blender 场景自动搭建 | 40% | P0 |
| 7 | 纸张材质统一应用 | 50% | P2 |
| 8 | 环境与光照自动配置 | 30% | P2 |
| 9 | 场景运动与角色动画 | 25% | P2 |
| 10 | 镜头运镜与渲染输出 | 20% | P0 |
| 11 | 后期剪辑与成片 | 10% | P0 |
| **12** | **模型管理（新增）** | **85%** | **P0** |
| **13** | **运行时配置（新增）** | **90%** | **P0** |

**综合完成度估算**：

- **已完成**：约 50%
- **进行中**：约 25%
- **未开始**：约 25%

---

## 二、各模块详细评估

### 模块 1：自动化剧本拆解 —— 95%

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
| **自动场景三关键帧批量生成（wide/closeup/mood）** | ✅ | `services/auto_scene_view.py` |
| 场景视觉提示词生成（中/英/日） | ✅ | `services/scene_generator.py` |
| 场景关键帧生成（txt2img + img2img） | ✅ | `services/scene_generator.py` |
| 场景资产持久化（`scenes/<scene_name>/...`） | ✅ | `services/project_store.save_scene_asset` |
| `/scripts/scenes/batch-status` 轮询 | ✅ | `endpoints_script.py` |
| 人物动作提示词生成 | ✅ | `services/shot_generator.py` |
| 镜头运动提示词生成 | ✅ | `services/shot_generator.py` |
| 场景转换提示词生成 | ✅ | `services/shot_generator.py` |
| 人物动作序列提示词生成 | ✅ | `services/shot_generator.py` |
| 前端分镜表网格化展示 | ✅ | `components/ScriptEditor.tsx`（StoryboardTab） |
| 网格化分镜表展示组件 | ✅ | `components/ScriptEditor.tsx`（`grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4`） |
| 分镜详情侧栏（编辑景别/运镜/时长） | ✅ | `components/ScriptEditor.tsx` |
| 网格化组件支持 4 列响应式布局 | ✅ | `components/ScriptEditor.tsx` |
| 场景级自动三视图+关键帧批量生成（fire-and-forget） | ✅ | `services/auto_three_view.py` + `services/auto_scene_view.py` |
| `/scripts/characters/batch-status` 轮询 | ✅ | `endpoints_script.py` |
| `/scripts/scenes/batch-status` 轮询 | ✅ | `endpoints_script.py` |

#### 缺口说明

1. **分镜预览图像缺失**：分镜表卡片目前显示文本和场景引用，但尚未生成 shot-level 缩略图。建议在后续阶段接入 SceneAsset 的 wide 缩略图作为分镜卡片预览。
2. **单 grid 视图样式朴素**：当前 `StoryboardTab` 为均匀四列网格，没有按"页码"分组的电影分镜本式布局（带场景名/镜号分隔条），属于风格增强而非阻塞性缺口。

**更新（2026-08-15）**：上述两项缺口已实际补齐，详见 `frontend/src/components/ScriptEditor.tsx`：

- `StoryboardTabProps` 增加了 `sceneAssets?: Record<string, SceneAsset>`，并在 `ScriptEditor` 顶层 `<StoryboardTab>` 调用处注入；
- 组件内部用 `useMemo` 按 `sceneId` 把 shots 分组，按剧本场景顺序排序（未知 scene 排到末尾），每组渲染为 `<section>` 包裹 `<header>`（Scene 标签 + 场景名 + 时间 + 镜数 + 渐变分割线）+ 4 列 shot 网格，构成电影分镜本式布局；
- 每个 shot 卡片顶端新增 `aspect-video` 缩略图槽：优先取 `sceneAssets[shot.sceneId]?.keyframeImages?.wide`，缺图时降级为本组 hero 缩略图，再缺时显示"无预览 · <场景名>"灰色占位。

**进一步更新（2026-08-15）**：将视觉提示词框升级为**双向**：

- 在 `useScriptStore` 中新增 `resolveCharacterVisualPrompts` / `resolveSceneVisualPrompts`：自动调用后端 `/v2/scripts/visual-prompt` 端点（已存在但之前无人调用），把 LLM 生成的 `visual_prompt` 写回 `parsedScript.characters[i]` / `parsedScript.scenes[i]` 与 `extractedCharacters`；
- `parseScript` 完成后默认自动触发上述解析（`autoResolvePromptsEnabled` 开关，默认开启）；
- `pollAutoThreeView` / `pollAutoSceneAsset` / `generateCharacterThreeView` / `generateSceneAsset` 成功后，**额外**回填 `parsedScript`（仅当原本空），保持 `parsedScript` 为唯一权威源；
- `CharactersTab` 提示词框升级：除 `<textarea>` 外新增 `PromptSourceBadge`（空 / AI 自动 / 人工编辑）+ 三个按钮"生成初始提示词"（输入侧）、"用此提示词生成三视图"（输出侧 1）、"以此为种子生成变体"（输出侧 2，调用 `generateCharacterVariation`）；
- `ScenesTab` 提示词 `<pre>` 改 `<textarea>`，新增"生成初始提示词"与"用此提示词生成关键帧"按钮；
- `CharactersTab` / `ScenesTab` 列表卡片下方加一行斜体 `line-clamp-2` 提示词预览，未生成时显示"正在生成提示词…"；
- `MotionTab` 把单行 `actionPrompt` 改为可折叠 `<details>`，展开后展示动作 / 场景 / 相机 / 转场 四件套。

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
| 自动三视图全 None 时显式标记 failed | ✅ | `services/auto_three_view.py`（新增视图完整性检查） |
| 云端图像失败错误信息明确（API key/配额/网络） | ✅ | `services/character_generator.py`（_generate_via_cloud 重抛 RuntimeError） |
| 启动时缺 DashScope key 警告 | ✅ | `app/config.py`（启动期 health check） |
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

2. **边缘羽化未启用**：`sam2_loader.py` 中存在 `refine_mask_edges()` 函数（可做 Canny 边缘吸附），但 `motion_extractor.py` 未调用，导致抠像边缘偏硬。`models/sam2_loader.py` 中 `_canny_edges()` 与 `refine_mask_edges()` 已实现完整，但需在 `motion_extractor.py` 中串联调用。

3. **ffmpeg 外部依赖**：`extract_frames_from_video()` 依赖系统 PATH 中的 ffmpeg，若未安装则返回空列表而不抛异常。

4. **云端图像生成静默失败（已修复）**：早期版本 `_generate_via_cloud` 失败时仅 log warning 并返回 `None`，导致前端看不到错误。本次更新后已改为抛出带诊断信息的 `RuntimeError`，由 `auto_three_view` 的 `except` 捕获并标记 `status='failed'`。**说明**：此项已修复，从缺口清单移除并转为已完成项。

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

### 模块 5：文件整合与分镜归档 —— 80%

#### 能力矩阵

| 功能点 | 状态 | 实现文件 |
|--------|:----:|----------|
| 项目目录结构定义 | ✅ | `services/project_store.py` |
| v1 目录结构（图像分析类） | ✅ | `services/project_store.py` |
| v2 目录结构（剧本/分镜类） | ✅ | `services/project_store.py` |
| **v3 目录结构（角色/动作/场景子目录）** | ✅ | `services/project_store.py` |
| manifest.json 原子写入 | ✅ | `services/project_store.py` |
| per-project 并发锁 | ✅ | `services/project_store.py` |
| 角色资产持久化（front/side/back PNG） | ✅ | `services/project_store.py` |
| 动作序列持久化（JSON + 帧文件） | ✅ | `services/project_store.py` |
| 角色名/场景名/动作名 slugify（保留 CJK） | ✅ | `services/project_store.py` |
| 自动从剧本标题生成 `project_id` (`<ts>_<slug>`) | ✅ | `services/project_store.make_project_id` |
| v1/v2 → v3 目录迁移工具 | ✅ | `services/project_store.migrate_v1v2_to_v3` |
| 跨角色/动作/帧号的 asset 检索接口 | ✅ | `services/project_store.list_character_assets` |
| **自动化归档脚本（场景名_镜号目录结构）** | ⚠️ | 部分（v3 布局已就位，但缺独立的归档打包 CLI） |
| **Blender 导入包生成（shot 级别 ZIP）** | ❌ | - |

#### 缺口说明

当前 `project_store.py` 已实现 v3 目录布局：
```
.workspace/projects/<timestamp>_<script_title>/
    characters/<character_name>/<action_or_view>/frame_<idx>.json
    motions/<character_name>/<action_slug>/frame_<idx>.<ext>
    scenes/<scene_name>/<scene_id>_<kind>.<ext>
```
并提供 v1/v2 → v3 一键迁移。**剩余缺口**：Blender 插件需要的导入包（FBX + 角色帧序列 + 场景提示词打包 ZIP）尚无独立 CLI，建议新增 `scripts/archive_shot.py`。

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

### 模块 12：模型管理（新增） —— 85%

> **背景**：原 `PROJECT_STATUS.md`（2026-07-27）版本未覆盖此模块。该模块在 2026-07-28 提交 `a3dc66a` 中作为独立子系统引入，承担本地模型的下载/加载/卸载/状态跟踪，是模块 3（场景分层）和模块 4（补全导出）正常运行的前置条件。

#### 能力矩阵

| 功能点 | 状态 | 实现文件 |
|--------|:----:|----------|
| 6 个本地模型 loader（Depth/SAM2/Qwen3-VL/GroundingDINO/LaMa/Z-Image） | ✅ | `models/*_loader.py` |
| 统一 ModelManager 单例（懒加载 + 用完即卸） | ✅ | `models/model_manager.py` |
| 云端/本地模式路由（`use_cloud` 属性） | ✅ | `models/model_manager.py` |
| 模型下载状态查询 `GET /api/aicss/models/status` | ✅ | `endpoints_models.py` |
| 模型下载触发 `POST /api/aicss/models/download/{name}` | ✅ | `endpoints_models.py` |
| 异步下载任务池与状态注册表 | ✅ | `services/download_jobs.py` |
| HF Mirror + Xet 禁用 + 10min 超时（国内网络适配） | ✅ | `config.py`（env 注入） |
| 模型检查点路径可配置 | ✅ | `config.py` |
| **下载进度条（百分比）** | ⚠️ | loader 未透传进度，前端仅显示 downloading 状态 |
| **下载失败重试** | ⚠️ | 当前一次失败即终止 |
| **断点续传** | ❌ | - |

#### API 端点状态

| 端点 | 方法 | 状态 |
|------|:----:|:----:|
| `/api/aicss/models/status` | GET | ✅ |
| `/api/aicss/models/download/{name}` | POST | ✅ |

#### 缺口说明

1. **下载进度不可见**：`_get_model_download_info` 仅返回 `status=downloading`，没有真实百分比。前端无法显示进度条，仅可显示 spinner。
2. **无重试/断点续传**：大模型（Z-Image 33GB、Qwen3-VL 8GB）下载中断后必须从头开始。

---

### 模块 13：运行时配置（新增） —— 90%

> **背景**：原 `PROJECT_STATUS.md`（2026-07-27）版本未覆盖此模块。该模块在 2026-07-28~2026-07-29 提交中独立出来，将原本硬编码在 `config.py` 中的模式（cloud/local）和模型选择项通过 `settings_manager.py` 暴露为前端可热更新的 API。

#### 能力矩阵

| 功能点 | 状态 | 实现文件 |
|--------|:----:|----------|
| 4 组件模式开关（model/vlm/image/video） | ✅ | `services/settings_manager.py` |
| 4 组件 DashScope API key 热更新（运行时生效） | ✅ | `services/settings_manager.py` |
| DashScope 模型 ID 热更新（LLM/VLM/Image） | ✅ | `services/settings_manager.py` |
| 本地 LLM base_url/model 热更新 | ✅ | `services/local_llm.configure_llm` |
| 本地 Image model_id/dtype 热更新 | ✅ | `services/image_generator.configure_image_generator` |
| 切换到 local 时自动启动 llama-server | ✅ | `services/llama_server_manager` |
| 切换到 cloud 时自动 set_use_cloud | ✅ | `services/local_llm.set_use_cloud` |
| 视频模式切换 → video_provider 自动联动 | ✅ | `services/settings_manager.py` |
| API key 写入 process env（dashscope SDK 立即生效） | ✅ | `services/settings_manager.py` |
| 敏感字段返回时打码（`***`） | ✅ | `services/settings_manager.SENSITIVE_FIELDS` |
| 前端设置面板（LLM/VLM/Image/Video 四组） | ✅ | `components/SettingsPanel.tsx` |
| **运行时 model_mode → 三组件模式联动** | ⚠️ | 仅日志，未自动同步 vlm/image/video_mode |
| **磁盘持久化（重启后保持用户偏好）** | ❌ | 改动仅在内存，进程退出即丢失 |

#### API 端点状态

| 端点 | 方法 | 状态 |
|------|:----:|:----:|
| `/api/aicss/settings` | GET | ✅ |
| `/api/aicss/settings` | PATCH | ✅ |

#### 缺口说明

1. **设置不持久化**：当前 `settings_manager.update_settings` 仅修改内存中的 `settings` 对象并写进程 env，重启后需重新设置。生产环境应在 `~/.aicss/settings.json` 持久化用户偏好，并在启动时加载。
2. **未做 model_mode → 子模式级联**：当用户把 `model_mode` 切到 local 时，`vlm_mode/image_mode/video_mode` 不会自动跟随，需要用户逐一手动调整。

---

## 三、关键缺口优先级矩阵

### P0 — 阻塞性缺口（必须实现才能达到目标）

| 优先级 | 缺口 | 影响模块 | 建议方案 |
|:-------:|------|:--------:|----------|
| P0-1 | Blender 独立插件 | 模块 6 | 开发 `backend/blender/` 插件目录，提供 `.py` 插件文件 |
| P0-2 | 后期剪辑管线 | 模块 11 | 集成 FFmpeg 的视频拼接 + 转场渲染端到端流程 |
| P0-3 | 镜头运镜自动播放 | 模块 10 | 将 13 种 CameraMovement 枚举转换为 Three.js 相机路径 + Blender 摄影机关键帧 |
| ~~P0-4~~ | ~~P3 缺归档脚本（已部分解决）~~ | ~~模块 5~~ | v3 布局已就位，缺独立 CLI |

### P1 — 核心功能缺口（严重影响最终效果）

| 优先级 | 缺口 | 影响模块 | 建议方案 |
|:-------:|------|:--------:|----------|
| P1-1 | 绿幕人物动作视频 | 模块 2 | 在 video_adapter 中新增 greenscreen provider 或后处理步骤 |
| P1-2 | 图层 PNG 导出端点 | 模块 3 | 新增 `POST /api/aicss/layers/export` 端点，按深度层二值化分割原图 |
| ~~P1-3~~ | ~~前端网格化分镜表展示~~ | ~~模块 1~~ | **已完成**：`StoryboardTab` 已实现 4 列响应式网格 |

### P2 — 质量增强缺口（提升最终效果）

| 优先级 | 缺口 | 影响模块 | 建议方案 |
|:-------:|------|:--------:|----------|
| P2-1 | 精细 Z 轴/厚度纹理 | 模块 4 | 改造 `mesh_exporter.py` Blender 脚本，利用 depthValue 精细偏移 + thickness_map 生成非均匀厚度 |
| P2-2 | Blender 完整材质节点 | 模块 7 | 扩展 `make_paper_material()` 增加 Normal Map + SSS 节点 |
| P2-3 | 光照配置面板 + Blender 光照脚本 | 模块 8 | UI 面板 + 动态生成 Blender 光照 Python 代码 |
| P2-4 | Blender 角色帧动画 | 模块 9 | 实现 Blender 帧序列导入和角色播放流程 |
| P2-5 | 抠像边缘羽化 | 模块 2 | 在 `motion_extractor.py` 中调用 `refine_mask_edges()` |
| P2-6 | 模型下载进度条 | 模块 12 | loader 透传进度百分比到 `download_jobs` 注册表 |
| P2-7 | 模型下载断点续传 | 模块 12 | 集成 `huggingface_hub` `resume_download=True` |

### P3 — 便利性缺口（提升用户体验）

| 优先级 | 缺口 | 影响模块 | 建议方案 |
|:-------:|------|:--------:|----------|
| P3-1 | 自动化分镜归档 CLI | 模块 5 | 开发 `scripts/archive_shot.py`，按 v3 布局打包 shot 级别 ZIP |
| P3-2 | 首尾帧一致性检查 | 模块 2 | 在 motion generate 端点增加 start_image / end_image 一致性验证 |
| P3-3 | 运行时配置磁盘持久化 | 模块 13 | 把用户偏好持久化到 `~/.aicss/settings.json` |

---

## 四、技术债务与已知问题

### 模型管理

| 问题 | 影响 | 状态 |
|------|------|------|
| Z-Image-Turbo 首次下载 33GB | 部署门槛高 | 已优化（异步下载 + 状态查询） |
| Qwen3-VL-4B 需 ~8GB VRAM | 单卡部署限制 | 已知 |
| SAM2 vit_l checkpoint ~375MB | 加载时间 | 已知 |
| 模型懒加载机制 | 首次调用慢 | 已解决（lazy_load=True） |
| **模型下载进度不可见** | 用户体验 | 已知 |
| **模型下载无断点续传** | 大模型下载易失败 | 已知 |
| **设置不持久化** | 重启后用户偏好丢失 | 已知 |

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
4. **运行时设置持久化（模块 13）→ 用户偏好跨重启保留**
5. **模型下载进度条 + 断点续传（模块 12）→ 大模型下载可靠性**

#### ✅ 阶段一完成状态 (2026-08-14)

| 子任务 | 状态 | 关键交付物 |
| --- | --- | --- |
| 1.1 图层 PNG 导出端点 | ✅ 完成 | `app/services/layer_exporter.py`, `app/endpoints_layers.py`, `POST /api/aicss/layers/export` |
| 1.2 Blender 独立插件 | ✅ 完成 | `backend/blender/addons/aicss_scene_builder/`（10 文件 + 3 灯光预设 + README） |
| 1.3 运镜 Three.js 自动播放 | ✅ 完成 | `frontend/src/utils/cameraAnimation.ts`, `components/CameraPathPlayer.tsx`, `components/ShotPlaybackControls.tsx`, `POST /api/aicss/v2/scripts/camera-path` |
| 1.4.1 settings observer 重构 | ✅ 完成 | `app/services/settings_observer.py` |
| 1.4.2 LLMMode 上下文变量 | ✅ 完成 | `LLMMode`, `_llm_mode_ctx`, `llm_mode_scope()` |
| 1.4.3 ImageGenerator 接口 + RLock | ✅ 完成 | `app/services/image_generator_interface.py` |
| 1.4.4 v1 端点 Pydantic 响应模型 | ✅ 完成 | 12 个 response models（11 个 v1 端点 + layers/export） |
| 1 Exit 验收测试 | ✅ 完成 | `backend/test_phase1_exit.py`（7 项检查全部通过） |

### 阶段二：质量提升（约 2 周）

6. 完善 Blender 材质节点 + 光照配置（模块 7+8）
7. 实现精细 Z 轴偏移和厚度纹理（模块 4）
8. ~~开发前端网格化分镜表展示（模块 1）~~ → **已完成**

### 阶段三：后期管线（约 2 周）

9. 开发后期剪辑管线（模块 11）→ 集成 FFmpeg 视频拼接
10. 实现 Blender 帧动画和运镜渲染（模块 9+10）
11. 自动化分镜归档 CLI（模块 5）

### 阶段四：优化打磨（约 1 周）

12. 绿幕功能（如需要）
13. 抠像边缘羽化
14. 首尾帧一致性检查
15. 端到端联调测试

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

模块 12: 模型管理 ──► 模块 3: 场景分层 (DepthAnything/SAM2)
              └──► 模块 4: 补全导出 (LaMa)
              └──► 模块 6: Blender 插件 (本地推理兜底)

模块 13: 运行时配置 ──► 模块 12 (选择 model_mode = local/cloud)
                    ──► 模块 2 (image_mode / dashscope_image_model 热更新)
                    ──► 模块 3 (vlm_mode 热更新)
                    ──► 模块 9 (video_mode / video_provider 热更新)
```

---

---

## 七、模块耦合度与端口协议分析

> **评估日期**：2026-08-10
>
> **评估范围**：后端 52 个 Python 文件 + 前端 5 个 TypeScript service 文件

### 7.1 模块依赖矩阵

```
┌──────────────────────────────────────────────────────────────────┐
│ 模块依赖图（箭头表示"依赖"）                                       │
└──────────────────────────────────────────────────────────────────┘

main.py ──► config.py (全局单例)
             │
             ├──► models/model_manager.py ──► 6个 *_loader.py (仅读配置)
             │              │
             │              └──► cloud_client (providers/)
             │
             ├──► providers/
             │    ├── base.py (抽象接口)
             │    └── cloud_router.py ──► base.py
             │
             ├──► services/
             │    ├── local_llm.py ──► config, cloud_router
             │    ├── settings_manager.py ──► config (直接修改单例属性)
             │    ├── image_generator.py ──► config (模块级单例)
             │    ├── script_parser.py ──► local_llm
             │    ├── character_generator.py ──► local_llm, cloud_router, image_generator
             │    ├── scene_generator.py ──► local_llm, cloud_router, image_generator
             │    ├── shot_generator.py ──► local_llm, cloud_router
             │    ├── project_store.py ──► config
             │    ├── mesh_exporter.py ──► (无外部服务依赖)
             │    └── motion_extractor.py ──► model_manager
             │
             └──► endpoints/ (HTTP层，依赖各 service)
                  ├── endpoints.py ──► model_manager, utils, project_store
                  ├── endpoints_script.py ──► 所有 services/ 模块
                  ├── endpoints_settings.py ──► settings_manager
                  └── endpoints_models.py ──► model_manager

前端 services/ (HTTP 调用，无内部依赖)
├── settingsService.ts ──► GET/POST /api/aicss/settings
├── scriptService.ts ──► /api/aicss/v2/scripts/*
└── ...
```

### 7.2 耦合度评级

| 评级 | 含义 |
|:----:|------|
| A | 高度内聚，无外部状态依赖 |
| B | 少量依赖，耦合可控 |
| C | 中度耦合，存在全局状态 |
| D | 高度耦合，隐式共享状态 |

| 模块 | 内聚 | 外部依赖数 | 耦合类型 | 评级 |
|------|:----:|:----------:|---------|:----:|
| `config.py` | 高 | 0 | — | A |
| `providers/base.py` | 高 | 0 | — | A |
| `services/mesh_exporter.py` | 高 | 0 | — | A |
| `utils/spatial_utils.py` | 高 | 1 (config) | 数据耦合 | B |
| `services/project_store.py` | 高 | 1 (config) | 数据耦合 | B |
| `models/model_manager.py` | 高 | 2 (config, loaders) | 数据耦合 | B |
| `services/script_parser.py` | 高 | 1 (local_llm) | 数据耦合 | B |
| `services/character_generator.py` | 高 | 3 (services) | 数据耦合 | B |
| `services/scene_generator.py` | 高 | 3 (services) | 数据耦合 | B |
| `services/shot_generator.py` | 高 | 3 (services) | 数据耦合 | B |
| `services/motion_extractor.py` | 中 | 1 (model_manager) | 数据耦合 | B |
| `providers/cloud_router.py` | 中 | 2 (config, base) | 数据耦合+缓存 | B |
| `services/local_llm.py` | 中 | 模块级全局变量 | **控制耦合** | C |
| `services/image_generator.py` | 中 | 模块级全局单例 | **控制耦合** | C |
| `services/settings_manager.py` | 中 | 直接修改单例属性 | **内容耦合** | D |
| `endpoints/*.py` | 高 | 对应服务 | 数据耦合 | B |

**关键发现**：
- 无循环导入（circular import）
- `settings_manager.py` 是唯一 **D 级** 模块，直接 `setattr(settings, key, coerced)` 修改全局单例
- `local_llm.py` 和 `image_generator.py` 为 **C 级**，使用模块级全局变量管理运行时状态

### 7.3 端口协议（API边界）清晰度

#### 后端 API 端点

| 端点路由 | 请求模型 | 响应模型 | 协议清晰度 |
|---------|:--------:|:--------:|:----------:|
| `POST /api/aicss/v2/scripts/*` (全部) | Pydantic ✅ | Pydantic ✅ | **高** |
| `POST /api/aicss/v2/sequences/*` | Pydantic ✅ | Pydantic ✅ | **高** |
| `GET /api/aicss/v2/meshes/*` | — | Pydantic ✅ | **高** |
| `POST /api/aicss/analyze` | Pydantic ✅ | `-> dict` ⚠️ | 中 |
| `POST /api/aicss/inpaint` | Pydantic ✅ | `-> dict` ⚠️ | 中 |
| `POST /api/aicss/paper-diorama` | Pydantic ✅ | `-> dict` ⚠️ | 中 |
| `POST /api/aicss/depth` | Pydantic ✅ | `-> dict` ⚠️ | 低 |
| `POST /api/aicss/segment` | Pydantic ✅ | `-> dict` ⚠️ | 低 |
| `POST /api/aicss/layers` | Pydantic ✅ | `-> dict` ⚠️ | 低 |
| `GET /api/aicss/settings` | — | 隐式dict ⚠️ | 低 |

**问题**：v1 端点（`endpoints.py`，约 850 行）大量使用 `-> dict` 返回类型，OpenAPI schema 无法推断响应结构，前端只能阅读源代码了解字段名。

#### 前端-后端耦合

前端通过手写 axios 调用，无类型安全的 API 客户端。字段映射（snake_case ↔ camelCase）依赖字符串约定：

```typescript
// scriptService.ts - 隐式依赖 snake_case 字段名
const data = await api.post('/v2/scripts/parse', {
  raw_text: request.rawText,      // 依赖 snake_case
  language: request.language,
});
```

若后端字段改名，前端不报错，风险较高。

### 7.4 代码级耦合问题详解

#### 问题 1：`settings_manager` 直接修改全局单例（内容耦合）—— D级 ⚠️

**位置**：`services/settings_manager.py` 第 125-140 行

```python
def update_settings(updates: dict) -> dict:
    for key, value in updates.items():
        setattr(settings, key, coerced)  # ← 直接修改全局单例
        changes[key] = coerced
```

**影响**：任何调用 `update_settings()` 的端点都会影响 `local_llm`、`image_generator`、`cloud_router` 的行为，因为它们每次调用时都 `from app.config import settings`。

#### 问题 2：`local_llm` 模块级全局状态（控制耦合）—— C级 ⚠️

**位置**：`services/local_llm.py` 第 280-340 行

```python
_use_cloud: bool = False  # ← 模块级全局变量

def get_llm_client() -> "LocalLLMClient | CloudRouterProxy":
    if _use_cloud:       # ← 依赖全局状态决定返回类型
        return CloudRouterProxy()
    # ...
```

**影响**：`script_parser.py`、`character_generator.py`、`scene_generator.py` 均通过 `get_llm_client()` 隐式依赖此全局状态，`settings_manager` 调用 `set_use_cloud()` 修改状态后这些模块的行为随之改变。

#### 问题 3：`image_generator` 模块级单例（控制耦合）—— C级 ⚠️

**位置**：`services/image_generator.py` 第 760-810 行

```python
_img_gen: Optional[LocalImageGenerator] = None
_img_gen_lock = _threading.Lock()

def configure_image_generator(model_id: str, dtype_name: str) -> None:
    global _img_gen
    if _img_gen is not None:
        _img_gen.unload()  # ← 在生成过程中卸载可能引发竞态
    _img_gen = None
    _img_gen = LocalImageGenerator(...)
```

**影响**：如果在生成过程中调用 `configure_image_generator()`，正在执行的 `generate()` 调用可能遇到竞态条件。

#### 问题 4：v1 端点响应无 Pydantic 模型（协议不清）—— 中等 ⚠️

**位置**：`endpoints.py` 第 230-1080 行

整个文件约 850 行，所有端点返回 `-> dict` 而非 Pydantic 响应模型。OpenAPI schema 无法推断响应结构。

#### 问题 5：`spatial_utils` 隐式依赖全局配置（间接耦合）—— 轻微 ⚠️

**位置**：`utils/spatial_utils.py` 第 5 行

```python
from ..config import settings  # 仅用 settings.depth_buckets
```

如果配置被热更新，`assign_to_depth_layer()` 的行为会隐式变化。

### 7.5 解耦改进建议

#### 高优先级

| 优先级 | 建议 | 目标 |
|:------:|------|------|
| P0-1 | `settings_manager` 引入 observer 模式，消除对 `settings` 单例的直接写操作 | 消除 D 级内容耦合 |
| P0-2 | 为 `endpoints.py` 所有 v1 端点补充 Pydantic 响应模型 | 提升协议清晰度 |
| P1-1 | `local_llm` 全局 `_use_cloud` 变量改为 `LLMMode` 上下文 | 消除 C 级控制耦合 |
| P1-2 | 前端集成 `openapi-typescript-codegen` 自动生成类型安全客户端 | 消除隐式字段依赖 |

#### 中优先级

| 优先级 | 建议 | 目标 |
|:------:|------|------|
| P2-1 | 为 `CloudRouter` 缓存加 `threading.Lock` | 线程安全 |
| P2-2 | 工具模块（`spatial_utils` 等）参数化配置依赖 | 消除隐式依赖 |
| P2-3 | 为 `image_generator` 引入 `ImageGeneratorInterface` 抽象 | 便于替换实现 |

---

*本报告基于 2026-08-09 代码库状态生成，相比 2026-07-27 版本：模块 1 网格化展示已完成、模块 2 云端错误传播已修复、模块 3 自动场景三视图已加入、模块 5 v3 目录布局已实现，并新增模块 12 模型管理和模块 13 运行时配置两个子系统。*
*耦合度分析基于 2026-08-10 代码审查。*
