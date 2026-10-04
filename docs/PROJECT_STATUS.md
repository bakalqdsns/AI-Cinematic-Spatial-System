# AICinematicSpatialSystem 项目完成度评估报告

> **项目目标**：基于纸雕（paper diorama）风格的 AI 自动化影视分镜生产系统。
>
> **目标输出**：一段约 3 分半的纸雕风格动画短片。
>
> **评估日期**：2026-08-10（耦合度分析基于 2026-08-10；功能评估基于 2026-08-09）
>
> **代码对齐**：2026-09-27。已并入 `EXECUTION_TASKS.md` 的 T01–T17 全部交付物（后期剪辑管线、Blender 运镜/渲染队列/帧动画/图层运动/SSS/光照、settings 解耦、前端 openapi codegen）。
>
> **评估范围**：对照用户提出的 11 个模块 + 模型管理与运行时配置（新增）逐一评估实现状态。

---

## 一、总体进度概览

| 模块编号 | 模块名称 | 完成度 | 优先级 |
|:--------:|----------|:------:|:------:|
| 1 | 自动化剧本拆解 | 100% | - |
| 2 | 人物资产生成与动作提取 | 100% | - |
| 3 | 场景分层分割 | 100% | - |
| 4 | 遮挡区域补全与三维面片导出 | 100% | P2 |
| 5 | 文件整合与分镜归档 | 100% | - |
| 6 | Blender 场景自动搭建 | 95% | P0 |
| 7 | 纸张材质统一应用 | 90% | P2 |
| 8 | 环境与光照自动配置 | 90% | P2 |
| 9 | 场景运动与角色动画 | 90% | P2 |
| 10 | 镜头运镜与渲染输出 | 95% | P0 |
| 11 | 后期剪辑与成片 | 90% | P0 |
| **12** | **模型管理（新增）** | **95%** | **P0** |
| **13** | **运行时配置（新增）** | **100%** | **P0** |

**综合完成度估算**（2026-09-27，T01–T17 全部交付 + 阶段五技术债清理完成）：

- **已完成**：约 96%（13 个模块功能链路 + 技术债清理：settings 解耦、openapi codegen、tsc 零错误、check:schema 修复、paper-diorama 字段名确认无 bug）
- **进行中**：约 1%（paper-diorama 薄封装的 snake_case 回退分支为死代码，可选清理以减少困惑——非 bug）
- **未开始**：约 3%（依赖完整运行环境的 E2E 联调实跑：`backend/scripts/demo_pipeline.py` 需 ffmpeg/torch/Blender + DashScope key，当前环境无这些依赖）

---

## 二、各模块详细评估

### 模块 1：自动化剧本拆解 —— 100%

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

1. ~~**分镜预览图像缺失**~~（2026-08-15 已补齐）：`StoryboardTab` 注入 `sceneAssets`，卡片缩略图优先 `keyframeImages.wide`。
2. ~~**单 grid 视图样式朴素**~~（2026-08-15 已补齐）：按场景分组的电影分镜本式布局。
3. ~~**视觉提示词单向**~~（2026-08-15 已补齐）：双向提示词生成 / 回填 / 徽章。

模块 1 主产品链路达到 **100%**。

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

### 模块 2：人物资产生成与动作提取 —— 100%

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
| 动作视频生成（DashScope `wan2.5-i2v-preview`，另有 local_wan / svd） | ✅ | `services/video_adapter.py` + `services/motion_extractor.py` |
| 四种视频 Provider（dashscope / happyhorse / local_wan / svd） | ✅ | `services/video_adapter.py`（`_PROVIDER_REGISTRY`） |
| ffmpeg 帧提取 | ✅ | `services/motion_extractor.py` |
| SAM2 逐帧人物抠像 | ✅ | `services/motion_extractor.py` |
| PNG 序列帧导出（角色名_动作名_帧号） | ✅ | `services/motion_extractor.py` |
| 绿幕人物动作视频合成 | ✅  | `services/motion_extractor.py + video_adapter.py`（_apply_greenscreen_prompt + chroma_key_rgba + segment_frame_with_chroma_key） |
| 抠像后边缘羽化（feathering） | ✅ | `services/motion_extractor.py`（feather_edges=True, refine_mask_edges 已串联） |
| 首尾帧一致性检查 | ✅ | `services/motion_extractor.py`（`verify_keyframe_consistency()` — 三级策略：NCC≥0.70 快通 / MSE≤0.30 中速 / ORB特征匹配最严；结果写 `MotionSequence.first/last_frame_consistency` + `motion.error`；`serialize_motion_sequence()` 暴露 `first_frame_consistency` / `last_frame_consistency` 字段） |

---

### 模块 3：场景分层分割 —— 100%

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
| 深度层级分配（天空/背景/中景/前景/地面，百分位自适应 + 物体锚点） | ✅ | `services/layer_exporter.py`（`compute_sky_mask` + `_build_layer_masks`）|
| 前端多边形自由选区（PolygonDrawTool） | ✅ | `components/PolygonDrawTool.tsx` |
| **图层 PNG 导出端点**（`POST /api/aicss/layers/export`） | ✅ | `services/layer_exporter.py` + `endpoints_layers.py`（`main.py` 已挂载）。输出 **5 层**（sky / background / midground / foreground / ground），默认 `autoAnchor=True` 时由 GroundingDINO + SAM2 提供物体锚点，`reconstructGround=True` 时加 RANSAC 地面重建；`saveArchive=True` + `sceneId` 时将物体 PNG + JSON + manifest 持久化到 `backend/test_outputs/objects/<sceneId>/`。旧 API（`autoAnchor=False`）向后兼容，仍输出 5 层但物体为空。 |
| **图层 PNG 导出 → 前端消费** | ✅ | `components/ScriptEditor.tsx` ScenesTab 关键帧网格下方加 `生成分层` 按钮（`data-testid="layer-scene-{sceneId}"`），调 `useScriptStore.layerScene()` → `scriptService.exportSceneLayers()` → `POST /api/aicss/layers/export`，结果写回 `SceneAsset.layeredImages`（异步端点路径，方便测试）。<br/>*（2026-08-16 细化）* per-scene `layerErrors` + inline 错误条（不影响其它场景）；`AbortController` 注册表 `layerAbortControllers` 取消重触发时的旧请求；后端返回空 layers 时视为失败抛错；UI 元信息条显示源（wide/closeup/mood）+ 尺寸 + 生成时间 |
| **前端 strip-stack 流水线（生成器）** | ✅ | `components/SplitControls.tsx`（`useAppStore.stripStack`）+ `components/Viewer3D.tsx`（`StripStackMesh` 渲染） |
| **E2E 验证**（2026-08-17 扩展） | ✅ | Phase 1: `backend/test_layer_export_e2e.mjs`（Node 22，零依赖）：32/32 检查通过，4 层 RGBA PNG + SHA256 唯一性回归保护。<br/>Phase 2: `backend/test_layer_object_ground_e2e.py`：9 objects（person + tree×6 + grass×2）+ ground（RANSAC 法向量 ≈ up）+ archive 落盘完整验证。 |
| `regions` / `strip_stack` 字段 schema | ✅ | `endpoints_mesh.py` ExportSceneRequest |
| `regions` / `strip_stack` → Blender 实际消费 | ✅ | `mesh_exporter.export_full_scene` 透传 `strip_stack` → billboards + BackgroundPlane；`regions` → `_populate_regions_into_scene`（按 depthValue 精细 Z 的 PlaneGeometry）。E2E：`test_strip_stack_export_e2e.py`。 |

#### 缺口说明

1. ~~**图层 PNG 导出端点已就位、前端未消费**~~（2026-08-16 已修复，2026-08-17 扩展为 5 层）：`POST /api/aicss/layers/export` 已在 `ScriptEditor.tsx` ScenesTab 集成，用户点击"生成分层"按钮触发 `useScriptStore.layerScene()`，默认以 `wide` 关键帧作为输入。结果写回 `SceneAsset.layeredImages`（含 **5 张** RGBA PNG dataURI + zOffsets + source/generatedAt 元信息；`autoAnchor=True` 时额外返回 `objects[]` 和 `ground` 字段）。重跑覆盖原结果、不缓存到磁盘。

2. ~~**Z 区间双源不一致隐患**~~（2026-08-17 确认已解决）：`utils/spatial_utils.assign_to_depth_layer()` 读 `settings.depth_buckets`，而 `services/layer_exporter.LAYER_Z_RANGES` 写死 `(0,5) (5,15) (15,50) (50,inf)`。经代码核查，`config.py` 中 `depth_buckets` 的默认值与 `LAYER_Z_RANGES` 完全一致（均为前景 0-5 / 中景 5-15 / 背景 15-50 / 天空 50+），两者之间无漂移，无需修复。若后续在 settings 中调整 bucket 边界，需同步更新 `LAYER_Z_RANGES` 或改为统一读取 `settings.depth_buckets`。

3. ~~**前端 strip-stack 流水线已实现，Blender 端仍缺失**~~（2026-08-22 已完成）：`mesh_exporter.export_full_scene(strip_stack=...)` 已消费 `strip_stack`（billboard × N + BackgroundPlane）；`regions` → PlaneGeometry 亦已接入（见模块 4）。E2E：`test_strip_stack_export_e2e.py`。

模块 3 主产品链路达到 **100%**（含分层导出、前端消费、strip-stack、E2E）。

---

### 模块 4：遮挡区域补全与三维面片导出 —— 100%

#### 能力矩阵

| 功能点 | 状态 | 实现文件 |
|--------|:----:|----------|
| LaMa 图像修复模型 | ✅ | `models/lama_loader.py` |
| 图像修复（支持 RGBA/L 模式 mask） | ✅ | `utils/inpaint_utils.py` |
| 遮挡关系推理（场景图构建） | ✅ | `utils/spatial_utils.py` |
| **自动遮挡空洞检测** | ✅ | `services/occlusion_holes.py` + `POST /api/aicss/occlusion-holes`（peel / occluded_interior）；前端补全背景优先用 SAM mask |
| FBX/GLB 导出（Blender Headless） | ✅ | `services/mesh_exporter.py` |
| 物体级 mesh 导出 | ✅ | `services/mesh_exporter.py` |
| 深度层 mesh 导出 | ✅ | `services/mesh_exporter.py` |
| 完整场景 mesh 导出 | ✅ | `services/mesh_exporter.py` |
| mesh 持久化服务 | ✅ | `services/project_store_mesh.py` |
| 层级固定厚度（0.08/0.12/0.20/0.30） | ✅ | `services/mesh_exporter.py` |
| 厚度纹理图生成（距离变换场） | ✅ | `utils/paper_diorama.py` |
| 法线贴图生成（Sobel 梯度） | ✅ | `utils/paper_diorama.py` |
| 精细像素级 Z 轴偏移（depthValue → Z） | ✅ | `services/mesh_exporter.py` |
| 厚度纹理用于非均匀几何厚度 | ✅ | `services/mesh_exporter.py` |
| **strip-stack 逐层剥离导出** | ✅ | `mesh_exporter.export_full_scene(strip_stack=...)`；E2E `test_strip_stack_export_e2e.py` |
| **自由选区 regions → PlaneGeometry** | ✅ | `export_full_scene(regions=...)` → `_populate_regions_into_scene` |
| Strip undo 清理 billboard | ✅ | `useAppStore.undoLastStripStep` / `resetStripStack` |
| 补全不依赖 DashScope Key | ✅ | 本地 LaMa；`SplitControls` 已去掉 Key 拦截 |
| 纯函数单测 | ✅ | `backend/test_module4_unit.py`（mesh / inpaint_utils / occlusion_holes / endpoint） |

#### 缺口说明

原技术缺口（精细 Z、非均匀厚度、strip-stack、GLB 透明、软边缘、E2E 假 PASS、regions 导出、Strip undo、DashScope 假依赖、自动空洞检测、单测）均已关闭。模块 4 主产品链路达到 **100%**。

---

### 模块 5：文件整合与分镜归档 —— 100%

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
| v1/v2 → v3 目录迁移工具 | ✅ | `services/project_store.migrate_legacy_layout` |
| 跨角色/动作/帧号的 asset 检索接口 | ✅ | `services/project_store.list_character_assets` |
| **自动化归档脚本（场景名_镜号目录结构）** | ✅ | `scripts/archive_shot.py` + `services/shot_archiver.py` |
| **Blender 导入包生成（shot 级别 ZIP）** | ✅ | `shot_archiver.build_shot_archive` → `manifest.json` + layers/character/scene/mesh/camera/scripts；API：`POST/GET .../shots/{id}/archive`；前端 Storyboard「导出归档」 |

#### 缺口说明

~~原缺口（独立 CLI + shot ZIP）已关闭。~~ 解压 ZIP 后在 Blender 中启用 AICSS 插件，用 `aicss.import_layers` 选择 `manifest.json` 导入。仓库中没有 `scripts/blender_import.py`。模块 5 达到 **100%**。

---

### 模块 6：Blender 场景自动搭建 —— 95%

#### 能力矩阵

| 功能点 | 状态 | 实现文件 |
|--------|:----:|----------|
| Blender Headless 导出服务 | ✅ | `services/mesh_exporter.py` |
| Blender 自动检测（4.2/4.1/4.0/3.6） | ✅ | `services/mesh_exporter.py` |
| 动态超时计算（60s–300s） | ✅ | `services/mesh_exporter.py` |
| Base64 纹理解码与临时文件管理 | ✅ | `services/mesh_exporter.py` |
| GLB 格式导出 | ✅ | `services/mesh_exporter.py` |
| FBX 格式导出 | ✅ | `services/mesh_exporter.py` |
| **Blender 独立 .py 插件文件** | ✅ | `backend/blender/addons/aicss_scene_builder/` |
| Blender 插件导入图层 | ✅ | `operators/import_layers.py`（`aicss.import_layers`，读 `manifest.json`，按层建 Collection，平面放到规范 Z） |
| **角色纸片自动放置到坐标** | ✅ | `operators/import_layers.py`（T10：角色落位逻辑，按 manifest 的 `characters` 字段把角色 PNG 摆到指定坐标） |
| 场景层次关系自动构建 | ✅ | `import_layers.py`：按层建 Collection，平面放到规范 Z |
| **Blender Cycles 渲染验证** | ✅ | `operators/verify_cycles.py`（T10：Cycles 验证 operator） |
| **多镜头自动渲染 + 渲染队列** | ✅ | `operators/render_queue.py`（T07：批量 Cycles 渲染 operator） |
| **角色帧序列导入** | ✅ | `operators/import_character_frames.py`（T08） |
| **场景图层运动动画** | ✅ | `operators/layer_motion.py`（T09） |
| **摄影机运镜关键帧（13 种）** | ✅ | `operators/setup_camera.py` 的 `AICSS_OT_setup_camera_animation`（T06：读 manifest 的 `cameraPath` 写关键帧） |
| **Headless 导出带灯** | ✅ | `services/mesh_exporter.py` 的 `make_light()` + 灯光循环（T14） |

#### 缺口说明

1. ~~Headless 导出和插件两条路径~~：插件现已覆盖图层导入、角色落位、纸张材质、静态/动画相机、6 套光照预设、Cycles 验证、渲染队列、帧序列导入、图层运动。Headless 导出（`mesh_exporter.py`）现已带灯（`make_light` + 灯光循环）。
2. 剩余 5%：Blender Cycles 在实际 GPU 上的端到端渲染输出未在仓库内做实跑验证（`verify_cycles.py` 做的是配置校验，不是真实渲染产物比对）；多镜头渲染队列的产物落盘路径与前端 `compose` 管线的对接需在完整环境联调。

---

### 模块 7：纸张材质统一应用 —— 90%

#### 能力矩阵

| 功能点 | 状态 | 实现文件 |
|--------|:----:|----------|
| 卡通化纹理（双边滤波 + k-means） | ✅ | `utils/paper_diorama.py` |
| 厚度/高度场生成（距离变换） | ✅ | `utils/paper_diorama.py` |
| 法线贴图生成（Sobel 梯度） | ✅ | `utils/paper_diorama.py` |
| 纸雕描边（外轮廓 + 内轮廓 + 投影） | ✅ | `utils/paper_diorama.py` |
| 前端纸雕材质预览（Three.js） | ✅ | `components/Viewer3D.tsx` |
| 前端纸张材质参数面板 | ✅ | `components/DioramaSettingsPanel.tsx` |
| **Blender 纸张材质节点组** | ✅ | `materials/paper_material.py`（T12：Base Color + Normal + ColorRamp + SSS + 纤维节点）；`mesh_exporter.make_paper_material()` 同步加 `subsurface` 参数 |
| **次表面散射（SSS）效果** | ✅ | `paper_material.py`（T12：`Subsurface Weight=0.15`、`Subsurface Color #FFF5E6`、`Subsurface IOR 1.4`、`Subsurface Radius (0.1,0.05,0.02)`，默认开启逆光透纸感） |
| **纸张纤维法线贴图强度控制** | ✅ | `paper_material.py`（T12：纤维节点图已建，`PaperMaterialParams.use_fibre` 控制开关） |
| **用户可调节粗糙度/SSS 参数** | ✅ | `operators/apply_material.py`（T12：暴露 `subsurface` / `use_fibre` 属性）；Headless `make_paper_material` 加 `subsurface` 参数 |

#### 缺口说明

1. ~~Headless 材质没有 SSS / 纤维~~（T12 已补齐）：`make_paper_material()` 现接受 `subsurface` 参数；插件 `paper_material.py` 默认 SSS 权重 0.15 + 纤维节点图。
2. ~~插件 SSS 未生效~~（T12 已补齐）：`apply_material` 操作器暴露 `subsurface` / `use_fibre`，`paper_material.py` 写入 `Subsurface Weight` 默认 0.15。
3. 剩余 10%：SSS/纤维参数在真实 Cycles 渲染下的视觉表现未做实跑比对（节点图已建，参数已暴露，但渲染产物效果需 GPU 环境验证）；前端 DioramaSettingsPanel 与 Blender 插件参数的命名一致性可进一步统一。

---

### 模块 8：环境与光照自动配置 —— 90%

#### 能力矩阵

| 功能点 | 状态 | 实现文件 |
|--------|:----:|----------|
| 前端硬编码三光源配置 | ✅ | `components/Viewer3D.tsx`（`PaperDioramaLighting` 现读 `useAppStore.lightingPreset`/`lightingCustom`，不再纯硬编码） |
| 情绪标签数据模型 | ✅ | `services/shot_generator.py` |
| 场景类型数据模型 | ✅ | `services/script_parser.py` |
| 天空盒/地面纹理库定义 | ⚠️ | 无资源库（6 套光照预设 JSON 已就位，但天空盒/地面纹理库仍缺） |
| **自动光照方案生成** | ✅ | `blender/addons/aicss_scene_builder/operators/add_lighting.py`（T13/T14：6 套预设 `warm_interior`/`cool_exterior`/`dramatic`/`tense_night`/`soft_morning`/`misty_grey`）；前端 `lighting/presets.ts` 同步 6 套定义 |
| **光照参数可调面板** | ✅ | `components/LightingPanel.tsx`（T13：前端光照面板，选预设 + 自定义参数） |
| **Blender 光照配置脚本** | ✅ | `operators/add_lighting.py` + `presets/lighting/*.json`（6 套） |
| **Headless 导出带灯** | ✅ | `services/mesh_exporter.py` 的 `make_light()` + 灯光循环（T14：`export_lights` 链路打通） |
| **archive manifest 透传 lighting** | ✅ | `services/shot_archiver.py`（manifest 加 `lighting`/`lightingPreset` 字段）；`endpoints_shots.py` 的 `archive_shot` 加 `lighting_preset` 查询参数；前端 `ScriptEditor` 调用时传 `useAppStore.lightingPreset` |

#### 缺口说明

1. ~~光照方案硬编码~~（T13 已补齐）：`Viewer3D.tsx` 的 `PaperDioramaLighting` 现从 store 读取 `lightingPreset`/`lightingCustom`，前端 `LightingPanel` 可切换 6 套预设并自定义参数。
2. **无资源库**：天空背景板库、地面纹理库仍缺（6 套光照预设是灯光参数 JSON，不是天空盒/地面贴图资源）。
3. ~~Headless 导出不带灯~~（T14 已补齐）：`mesh_exporter.make_light()` + 灯光循环，`export_lights` 链路打通。
4. 剩余 10%：天空盒/地面纹理资源库未建；情绪标签 → 光照预设的**自动**映射规则（按 `shot.atmosphere`/`scene.time` 自动选预设）目前是前端手动选 + 后端 manifest 透传，未做全自动启发式选择。

---

### 模块 9：场景运动与角色动画 —— 90%

#### 能力矩阵

| 功能点 | 状态 | 实现文件 |
|--------|:----:|----------|
| 前端视差分层动画（depthLayerZ） | ✅ | `components/Viewer3D.tsx` |
| 前端轻微随机晃动效果 | ✅ | `components/Viewer3D.tsx` |
| PNG 序列帧导出（角色名_动作名_帧号） | ✅ | `services/motion_extractor.py` |
| 帧序列播放器（SequencePlayer） | ✅ | `components/sequence/SequencePlayer.tsx` |
| **角色纸片帧动画播放（Three.js）** | ✅ | `components/sequence/SequencePlayer.tsx`（已与角色实体绑定） |
| **Blender 帧序列导入** | ✅ | `operators/import_character_frames.py`（T08：`aicss.import_character_frames` operator，读 manifest 的 `characters` 帧序列） |
| **Blender 角色帧动画播放** | ✅ | `import_character_frames.py`（T08：把角色 PNG 序列帧导入为 Blender 帧序列纹理并驱动角色动画） |
| **Blender 场景图层运动动画** | ✅ | `operators/layer_motion.py`（T09：`aicss.layer_motion` operator，图层面片视差分层移动 + 随机晃动） |
| **manifest 字段对齐（角色帧序列）** | ✅ | `services/shot_archiver.py`（T11：manifest 加 `characters`/`cameraPath`/`lighting`/`lightingPreset` 字段） |

#### 缺口说明

1. ~~Three.js 角色帧动画未绑定到角色~~（已补齐）：`SequencePlayer` 已与角色实体绑定。
2. ~~Blender 角色帧动画完全缺失~~（T08 已补齐）：`import_character_frames.py` 实现帧序列导入 + 角色播放。
3. ~~Blender 场景运动动画缺失~~（T09 已补齐）：`layer_motion.py` 实现图层面片视差分层移动 + 随机晃动。
4. 剩余 10%：Blender 侧帧动画/图层运动的**真实渲染产物**未在 GPU 环境实跑验证（operator 逻辑已就位，但渲染输出与前端预览的视觉一致性比对未做）；角色帧序列与场景图层运动的时序协调（谁先动、叠加规则）需在联调环境细调。

---

### 模块 10：镜头运镜与渲染输出 —— 95%

#### 能力矩阵

| 功能点 | 状态 | 实现文件 |
|--------|:----:|----------|
| 景别枚举（10 种） | ✅ | `services/shot_generator.py` |
| 运镜枚举（13 种） | ✅ | `services/shot_generator.py` |
| 分镜运镜数据生成 | ✅ | `services/shot_generator.py` |
| Three.js 相机手动控制（OrbitControls） | ✅ | `components/Viewer3D.tsx` |
| **运镜数据 → Three.js 相机路径动画** | ✅ | `services/camera_path_generator.py`，`POST /api/aicss/v2/scripts/camera-path`，`utils/cameraAnimation.ts`，`components/CameraPathPlayer.tsx` |
| **运镜数据 → Blender 摄影机动画** | ✅ | `operators/setup_camera.py` 的 `AICSS_OT_setup_camera_animation`（T06：读 manifest 的 `cameraPath` 写 13 种运镜关键帧） |
| **Blender Cycles 离线渲染管线** | ✅ | `operators/verify_cycles.py`（T10：Cycles 配置验证）+ `operators/render_queue.py`（T07：批量 Cycles 渲染） |
| **多镜头自动渲染输出** | ✅ | `operators/render_queue.py`（T07：批量渲染多镜头并输出） |
| **渲染队列管理** | ✅ | `operators/render_queue.py` + `endpoints_compose.py` 的 `POST /render-queue`（T07：渲染队列 API） |
| **cameraPath 写入 archive manifest** | ✅ | `services/camera_path_generator.py` 的 `write_camera_path_to_archive()`（T06：把运镜路径写入 shot 归档 manifest） |

#### 缺口说明

1. **Three.js 运镜已播放**：`CameraMovement` 经 `camera_path_generator` 变成路径，`CameraPathPlayer` 驱动透视相机，`ShotPlaybackControls` 提供播放控制。
2. ~~Blender 侧仍是静态相机~~（T06 已补齐）：`setup_camera_animation` 读 manifest 的 `cameraPath` 写 13 种运镜关键帧。
3. ~~多镜头渲染和渲染队列没有~~（T07 已补齐）：`render_queue.py` 批量 Cycles 渲染 + `POST /render-queue` API。
4. 剩余 5%：Blender Cycles 在真实 GPU 上的渲染产物质量、渲染队列产物与前端 `compose` 管线的端到端衔接需在完整环境实跑验证（operator 与 API 已就位，但未做真实渲染产物比对）。

---

### 模块 11：后期剪辑与成片 —— 90%

#### 能力矩阵

| 功能点 | 状态 | 实现文件 |
|--------|:----:|----------|
| 静态图片导出（PNG/JPEG） | ✅ | `components/ExportPanel.tsx` |
| 3D Mesh 导出（GLB/FBX 下载） | ✅ | `services/meshExportService.ts` |
| 帧序列播放器 | ✅ | `components/sequence/SequencePlayer.tsx` |
| **视频拼接管线** | ✅ | `services/video_composer.py`（T01：全 async ffmpeg 封装 `compose_clips`）+ `endpoints_compose.py` 的 `POST /compose` |
| **ffmpeg 视频合成** | ✅ | `services/video_composer.py`（T01：`compose_clips` 调 ffmpeg 拼接 MP4） |
| **转场效果（cut/dissolve/fade/wipe）** | ✅ | `services/video_composer.py` 的 `apply_transition`（T02：4 种转场渲染实现） |
| **时间线编辑器 UI** | ✅ | `components/timeline/TimelineEditor.tsx` + `store/useTimelineStore.ts`（T03：多轨时间线、拖拽排序、转场设置、合成触发） |
| **音频轨（配音/BGM/音效）** | ✅ | `services/video_composer.py` 的 `mix_audio`（T04：BGM 循环、音效时间点、配音对齐 shot、响度归一化 `loudnorm`） |
| **色彩统一调整** | ✅ | `services/video_composer.py` 的 `apply_color_grade`（T05：LUT + brightness/contrast/saturation） |
| **合成产物流式回放** | ✅ | `endpoints_compose.py` 的 `GET /compose/{filename}`（FileResponse，支持 Range 请求）；前端 `composeService.outputPathToPlaybackUrl` 把绝对路径转流式 URL |
| **渲染队列 API** | ✅ | `endpoints_compose.py` 的 `POST /render-queue`（T07：批量提交渲染任务） |
| **前端 compose 客户端** | ✅ | `services/composeService.ts`（薄封装 + camelCase↔snake_case 映射 + `outputPathToPlaybackUrl`）；`ScriptEditor` 加 `timeline` tab 挂载 `TimelinePanel` |

#### 缺口说明

1. ~~最严重缺口：整个后期剪辑管线完全未实现~~（T01-T05 已补齐）：`video_composer.py` 全 async ffmpeg 封装（compose_clips/apply_transition/mix_audio/apply_color_grade），`endpoints_compose.py` 暴露 `POST /compose`、`POST /render-queue`、`GET /compose/{filename}`。
2. ~~`SceneTransition` 数据模型存在但无渲染~~（T02 已补齐）：`apply_transition` 实现 cut/dissolve/fade/wipe 4 种转场。
3. ~~无时间线编辑器、多轨合成、音频处理~~（T03/T04 已补齐）：`TimelineEditor` 多轨 UI + `useTimelineStore` 状态管理；`mix_audio` 处理 BGM/SFX/voiceover 三类音频轨。
4. 剩余 10%：合成管线**未在装 ffmpeg 的环境实跑验证**（`video_composer` 调系统 ffmpeg，当前环境无 ffmpeg）；渲染队列与 compose 的异步轮询（job id + poll endpoint）仍是同步返回，长视频合成时前端只能靠 faux progress bar；`POST /render-queue` 与 `POST /compose` 的产物落盘目录与前端 `outputPathToPlaybackUrl` 的 filename 提取需在联调环境对齐。

---

### 模块 12：模型管理（新增） —— 95%

> **背景**：原 `PROJECT_STATUS.md`（2026-07-27）版本未覆盖此模块。该模块在 2026-07-28 提交 `a3dc66a` 中作为独立子系统引入，承担本地模型的下载/加载/卸载/状态跟踪，是模块 3（场景分层）和模块 4（补全导出）正常运行的前置条件。
> **2026-08-16 更新**：补齐下载进度透传（tqdm 回调）、端点级重试（指数退避）、磁盘持久化进度组件、`files_done/total`、`current_file`、`speed_bps`、`eta_seconds` 等字段。

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
| **下载进度条（百分比 + ETA + 文件级）** | ✅ | `services/download_progress.py` + `services/download_jobs.py` |
| **下载失败重试（端点级指数退避，最多 N 次）** | ✅ | `endpoints_models._download_with_retry` |
| **断点续传（huggingface_hub `resume_download=True` + 部分文件持久化）** | ✅ | `snapshot_download` / SAM2 `.part` 落盘 |

#### API 端点状态

| 端点 | 方法 | 状态 |
|------|:----:|:----:|
| `/api/aicss/models/status` | GET | ✅（含进度字段：`progress` / `bytes_done` / `bytes_total` / `current_file` / `files_done` / `files_total` / `speed_bps` / `eta_seconds` / `attempt` / `max_attempts`） |
| `/api/aicss/models/download/{name}` | POST | ✅（默认 3 次重试 + 指数退避 2s/4s/8s，可通过 `AICSS_DOWNLOAD_RETRIES` 覆盖） |

#### 进度上报矩阵

| Loader | 进度上报机制 | 备注 |
|---|---|---|
| Depth | `huggingface_hub.snapshot_download` + tqdm callback | 标准 hf-mirror 路径 |
| GroundingDINO | 同上 | 同上 |
| Qwen3-VL | 同上 | 同上（最大 ~8GB） |
| SAM2（HF Hub 路径） | tqdm callback | 优先 |
| SAM2（Meta CDN 路径） | `report_file_progress` 每 ~1 MB 推一次 | 兜底 |
| LaMa | `report_file_progress` 每 ~1 MB 推一次 | 直接 HTTP，无 tqdm 接口 |
| Z-Image（HF Hub） | tqdm callback | 标准 |
| Z-Image（ModelScope） | 后台 watcher 线程轮询 `~/.cache/modelscope` 目录累计字节数 | 无 tqdm 接口的 workaround |

#### 缺口说明

无。模块 12 当前完整覆盖所有声明能力点和原缺口。

---

### 模块 13：运行时配置（新增） —— 100%

> **背景**：原 `PROJECT_STATUS.md`（2026-07-27）版本未覆盖此模块。该模块在 2026-07-28~2026-07-29 提交中独立出来，将原本硬编码在 `config.py` 中的模式（cloud/local）和模型选择项通过 `settings_manager.py` 暴露为前端可热更新的 API。
> **2026-08-16 更新**：增加 `~/.aicss/settings.json` 持久化（原子写入 + `apply_overrides()` 启动钩子），以及 `ModelModeCascadeObserver` 自动级联 `model_mode → vlm/image/video_mode`（仅在子模式为默认值时触发，保护用户已显式设置的子模式不被覆盖）。
> **2026-09-27 更新**（T15）：`settings_manager` 去掉 `setattr(settings, key, coerced)` 的 D 级内容耦合，改用 `_runtime_values` 字典作为运行时配置的唯一真相源；`local_llm` / `image_generator` / `cloud_router` 改读 `settings_manager.get()`；`settings_store` 改用 `seed_overrides()`；`settings_observer` 改用 `set_runtime_value()`。模块 13 升至 100%。

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
| **运行时 model_mode → 三组件模式联动** | ✅ | `services/settings_observer.ModelModeCascadeObserver` |
| **磁盘持久化（重启后保持用户偏好）** | ✅ | `services/settings_store.save_overrides/apply_overrides`，位置 `~/.aicss/settings.json`（POSIX 下 mode 0600） |
| **统一 Provider 注册表（自定义第三方模型无需后端改动）** | ✅ | `app/providers/` + `ProviderRegistry` UI — 见模块 16 |

#### API 端点状态

| 端点 | 方法 | 状态 |
|------|:----:|:----:|
| `/api/aicss/settings` | GET | ✅ |
| `/api/aicss/settings` | POST | ✅ |
| `/api/aicss/settings/store` | GET | ✅（返回持久化文件路径 + override 数） |
| `/api/aicss/settings/store` | DELETE | ✅（重置为「已记录但无 override」） |

#### 持久化策略

- **写入时机**：每次 `update_settings` 成功且包含非敏感字段的变更时同步落盘（原子 write via `tempfile.mkstemp` + `os.replace`）。
- **加载时机**：`app.main.lifespan` 启动时调用 `apply_overrides()`，覆盖 `config.settings` 上的默认值。
- **不打码字段**：除了 `SENSITIVE_FIELDS` 集合中的项外，所有运行期配置都参与持久化（包含 `providers` 列表）。
- **不持久化字段**：API key 永远不进 JSON 文件；只通过进程 env 热生效。
- **手动重置**：UI 上的「重置为默认值」按钮调用 `DELETE /api/aicss/settings/store`。

#### 级联策略

`ModelModeCascadeObserver` 在 `lifespan` 启动时自动注册。规则：
- 触发条件：`model_mode` 变更，且新值为 `cloud` / `local` 之一。
- 仅当子模式（`vlm_mode` / `image_mode` / `video_mode`）当前值在默认集合（`{cloud, local}`）内时才覆盖。
- 若用户此前已经手动设置子模式为特定值（例如 `vlm_mode=local` 而 `image_mode` 仍是 cloud），则只级联 `image_mode`，保留 `vlm_mode` 不动。
- 级联后立即持久化这些子模式值，下次启动仍然生效。

#### 缺口说明

无。模块 13 当前覆盖 13 项能力点 + 完整持久化 + 完整级联 + 完整 API 入口 + **D 级内容耦合已消除**（T15：`_runtime_values` 单一真相源，`setattr(settings, ...)` 已移除）。

---

## 三、关键缺口优先级矩阵

### P0 — 阻塞性缺口（必须实现才能达到目标）

| 优先级 | 缺口 | 影响模块 | 建议方案 |
|:-------:|------|:--------:|----------|
| ~~P0-1~~ | ~~Blender 独立插件~~ | ~~模块 6~~ | **已完成**：`backend/blender/addons/aicss_scene_builder/`。角色纸片自动落位、Cycles 验证仍开 |
| ~~P0-2~~ | ~~后期剪辑管线~~ | ~~模块 11~~ | **已完成**（T01-T05，2026-09-27）：`video_composer.py` 全 async ffmpeg 封装 + `endpoints_compose.py` 的 `POST /compose` / `POST /render-queue` / `GET /compose/{filename}`；前端 `TimelineEditor` + `useTimelineStore` + `composeService` |
| ~~P0-3~~ | ~~Blender 摄影机关键帧~~ | ~~模块 10~~ | **已完成**（T06，2026-09-27）：`operators/setup_camera.py` 的 `AICSS_OT_setup_camera_animation` 读 manifest 的 `cameraPath` 写 13 种运镜关键帧；`render_queue.py` 批量 Cycles 渲染 |
| ~~P0-4~~ | ~~P3 缺归档脚本（已部分解决）~~ | ~~模块 5~~ | v3 布局已就位，缺独立 CLI |

### P1 — 核心功能缺口（严重影响最终效果）

| 优先级 | 缺口 | 影响模块 | 建议方案 |
|:-------:|------|:--------:|----------|
| ~~P1-1~~ | ~~绿幕人物动作视频~~ | ~~模块 2~~ | **已完成**：`motion_extractor` greenscreen provider |
| ~~P1-2~~ | ~~图层 PNG 导出端点~~ | ~~模块 3~~ | **已完成**：`POST /api/aicss/layers/export` + 前端消费 |
| ~~P1-3~~ | ~~前端网格化分镜表展示~~ | ~~模块 1~~ | **已完成**：`StoryboardTab` 已实现 4 列响应式网格 |

### P2 — 质量增强缺口（提升最终效果）

| 优先级 | 缺口 | 影响模块 | 建议方案 |
|:-------:|------|:--------:|----------|
| ~~P2-1~~ | ~~精细 Z 轴/厚度纹理~~ | ~~模块 4~~ | **已完成**（2026-08-22）：`_compute_fine_z_offset()` + `make_displaced_plane()`；strip-stack / regions 导出已通 |
| ~~P2-2~~ | ~~Blender SSS 与纤维法线~~ | ~~模块 7~~ | **已完成**（T12，2026-09-27）：`paper_material.py` SSS 权重 0.15 + 纤维节点图；`apply_material` 暴露 `subsurface`/`use_fibre`；`mesh_exporter.make_paper_material` 加 `subsurface` 参数 |
| ~~P2-3~~ | ~~光照按情绪自动切换 + 前端面板~~ | ~~模块 8~~ | **已完成**（T13/T14，2026-09-27）：插件 `add_lighting` 6 套预设；前端 `LightingPanel` + `lighting/presets.ts`；`Viewer3D` 读 store；`mesh_exporter.make_light` Headless 带灯；`shot_archiver` manifest 透传 `lightingPreset` |
| ~~P2-4~~ | ~~Blender 角色帧动画~~ | ~~模块 9~~ | **已完成**（T08/T09，2026-09-27）：`import_character_frames.py` 帧序列导入 + 角色播放；`layer_motion.py` 场景图层运动动画 |
| ~~P2-5~~ | ~~抠像边缘羽化~~ | ~~模块 2~~ | **已完成**：`motion_extractor` 调用 `refine_mask_edges` |
| ~~P2-6~~ | ~~模型下载进度条~~ | ~~模块 12~~ | **已完成**（2026-08-16）：`download_progress.py` + tqdm callback 全 loader 透传 |
| ~~P2-7~~ | ~~模型下载断点续传~~ | ~~模块 12~~ | **已完成**（2026-08-16）：`huggingface_hub` 默认 `resume_download=True` + 端点级 retry 指数退避 |

### P3 — 便利性缺口（提升用户体验）

| 优先级 | 缺口 | 影响模块 | 建议方案 |
|:-------:|------|:--------:|----------|
| ~~P3-1~~ | ~~自动化分镜归档 CLI~~ | ~~模块 5~~ | **已完成**：`scripts/archive_shot.py` + `shot_archiver` + API/前端导出 |
| ~~P3-2~~ | ~~首尾帧一致性检查~~ | ~~模块 2~~ | **已完成**：`verify_keyframe_consistency` |
| ~~P3-3~~ | ~~运行时配置磁盘持久化~~ | ~~模块 13~~ | **已完成**（2026-08-16）：`settings_store.py` + `apply_overrides()` 启动钩子 |

---

## 四、技术债务与已知问题

### 模型管理

| 问题 | 影响 | 状态 |
|------|------|------|
| Z-Image-Turbo 首次下载 33GB | 部署门槛高 | 已优化（异步下载 + 状态查询） |
| Qwen3-VL-4B 需 ~8GB VRAM | 单卡部署限制 | 已知 |
| SAM2 vit_l checkpoint ~375MB | 加载时间 | 已知 |
| 模型懒加载机制 | 首次调用慢 | 已解决（lazy_load=True） |
| ~~模型下载进度不可见~~ | ~~用户体验~~ | **已解决**（2026-08-16）：tqdm callback 全 loader 透传，GET /status 返回 progress/current_file/eta |
| ~~模型下载无断点续传~~ | ~~大模型下载易失败~~ | **已解决**（2026-08-16）：端点级指数退避 retry + hf_hub `resume_download=True` |
| ~~设置不持久化~~ | ~~重启后用户偏好丢失~~ | **已解决**（2026-08-16）：`~/.aicss/settings.json` 原子写入 + 启动 `apply_overrides()` |
| model_mode 切换时未级联三子模式 | 需手动逐项设置 | 已解决（2026-08-16）：`ModelModeCascadeObserver` 自动联动，仅在子模式为默认值时触发 |

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
| ~~厚度纹理未用于几何厚度~~ | ~~`mesh_exporter.py`~~ | **已解决**：`make_displaced_plane()` 在 `use_displacement=True` 时用 `thicknessGrayUrl` 做非均匀厚度 |
| ~~PolygonDrawTool 选区未集成导出~~ | ~~`endpoints_mesh.py`~~ | **已解决**：`export_full_scene(regions=...)` → PlaneGeometry billboards |
| ~~strip-stack 导出未实现~~ | ~~`mesh_exporter.py`~~ | **已解决**：`_populate_strip_stack_into_scene` + E2E 通过 |
| ~~Blender Cycles 渲染未验证~~ | - | **部分解决**（T07/T10，2026-09-27）：`verify_cycles.py` 做配置校验 + `render_queue.py` 批量渲染 operator 已就位；真实 GPU 渲染产物比对仍待完整环境实跑 |

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

#### ✅ 阶段一后续闭环 (2026-08-16)

| 子任务 | 状态 | 关键交付物 |
| --- | --- | --- |
| 1.5.1 模型下载进度透传 | ✅ 完成 | `app/services/download_progress.py` + 6 个 loader 接入 tqdm 回调；`download_jobs.py` 加 9 个进度字段；GET /status 返回 `progress`/`current_file`/`speed_bps`/`eta_seconds` |
| 1.5.2 端点级 retry + 断点续传 | ✅ 完成 | `endpoints_models._download_with_retry`（默认 3 次指数退避，可通过 `AICSS_DOWNLOAD_RETRIES` 覆盖）；HF Hub 路径 `resume_download=True`；SAM2 `.part` 落盘 |
| 1.5.3 settings 持久化 | ✅ 完成 | `app/services/settings_store.py`（`save_overrides` / `apply_overrides`，POSIX mode 0600，原子写入）；`lifespan` 启动钩子；`GET/DELETE /api/aicss/settings/store` 暴露给前端 |
| 1.5.4 model_mode 级联 | ✅ 完成 | `settings_observer.ModelModeCascadeObserver`（仅在子模式为默认值时覆盖，保护用户已显式设置的值） |
| 1.5.5 Provider 注册表（新模块 16 已就绪） | ✅ 完成 | `app/providers/{base,openai_compatible,dashscope,cloud_router}.py` + `ProviderRegistry` UI 组件；新增第三方 OpenAI 兼容服务 0 后端代码改动 |

### 阶段二：质量提升（约 2 周）

6. 完善 Blender 材质节点 + 光照配置（模块 7+8）
7. ~~实现精细 Z 轴偏移和厚度纹理（模块 4）~~ → **已完成**（2026-08-22）
8. ~~开发前端网格化分镜表展示（模块 1）~~ → **已完成**

### 阶段三：后期管线（约 2 周）

9. ~~开发后期剪辑管线（模块 11）→ 集成 FFmpeg 视频拼接~~ → **已完成**（T01-T05，2026-09-27）
10. ~~实现 Blender 帧动画和运镜渲染（模块 9+10）~~ → **已完成**（T06-T09，2026-09-27）
11. ~~自动化分镜归档 CLI（模块 5）~~ → **已完成**

### 阶段四：优化打磨（约 1 周）

12. ~~绿幕功能（如需要）~~ → **已完成**
13. ~~抠像边缘羽化~~ → **已完成**
14. ~~首尾帧一致性检查~~ → **已完成**
15. ~~端到端联调测试~~ → **脚本已就位**（`backend/scripts/demo_pipeline.py`，T17，2026-09-27）：纯标准库 urllib，输入剧本文本输出 MP4，链路 parse → shots → characters → scenes → motion → archive → render → compose，每步打点 + 失败可重入。**待在完整依赖环境（ffmpeg/torch/Blender）实跑验证**。

### 阶段五：技术债清理（2026-09-27 进行中）

16. ~~`settings_manager` D 级内容耦合~~ → **已完成**（T15）
17. ~~前端 openapi codegen 类型安全客户端~~ → **已完成**（T16）
18. ~~前端预存 tsc 错误清理~~ → **已完成**（2026-09-27）：16 个错误全部清零，`npx tsc --noEmit` exit 0。关键修复：`ExportScope` 类型单数改复数匹配使用点；`PlaybackState` 改从 `ShotPlaybackControls` 导入；`DEPTH_LAYER_THRESHOLDS` 补 `sky:0`；`PolygonDrawTool` state 类型改 `DepthLayerKey|null`；`SplitControls` 补 `computeOcclusionAwareMask` import；`useScriptStore` 的 snake_case 读取**保留**（service 层薄透传未映射，直接改 camelCase 会取到 undefined 破坏运行时），仅放宽 cast 类型容纳 snake/camel 双形态；`ScriptEditor` 索引加 `as 'wide'|'closeup'|'mood'` 断言；`resolvedProjectId ?? undefined` 处理 null
19. ~~`check:schema` 脚本修复~~ → **已完成**（2026-09-27）：`mkdtempSync(tmpdir())` 改用 `frontend/.schema-check-tmp/` + `git diff` 改用 Node fs + SHA-256 递归比对（不依赖 git/diff）；`node scripts/check-schema.mjs` exit 0，225 文件匹配；codegen 参数与 `gen-api.mjs` 完全对齐
20. ~~`paper-diorama` 等端点字段名兼容性~~ → **已确认无 bug**（2026-09-27 静态分析）：后端 `PaperDioramaResponse`/`PaperLayerResponse`/`PaperStyleResponse` Pydantic 字段为 camelCase 无 alias，handler 显式重写键为 camelCase；薄封装优先读 camelCase（`data.paperStyleUrl ?? data.paper_style_url`）再输出 snake_case；组件读薄封装的 snake_case 返回值。全链路后端 camelCase → 生成客户端 camelCase → 薄封装读 camelCase 输出 snake_case → 组件读 snake_case，每一跳对齐，无 undefined 读取。薄封装的 snake_case 回退分支是死代码（冗余防御，非 bug），未来可清理以减少困惑

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
> **评估范围**：`backend/app` 下 64 个 Python 文件 + 前端 5 个 TypeScript service 文件。下列行号以 2026-09-26 代码为准。

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
| `services/settings_manager.py` | 高 | `_runtime_values` 字典（单一真相源） | 数据耦合 | B |
| `endpoints/*.py` | 高 | 对应服务 | 数据耦合 | B |

**关键发现**：
- 无循环导入（circular import）
- ~~`settings_manager.py` 是唯一 **D 级** 模块，直接 `setattr(settings, key, coerced)` 修改全局单例~~ **已解决**（T15，2026-09-27）：`settings_manager` 改用 `_runtime_values` 字典作为运行时配置唯一真相源，`setattr(settings, ...)` 已移除，评级从 D 降至 B。
- `local_llm.py` 和 `image_generator.py` 为 **C 级**，使用模块级全局变量管理运行时状态（`LLMMode` 上下文变量 + `RLockImageGenerator` 已大幅缓解，`_use_cloud` 回退仍双写）

### 7.3 端口协议（API边界）清晰度

#### 后端 API 端点

| 端点路由 | 请求模型 | 响应模型 | 协议清晰度 |
|---------|:--------:|:--------:|:----------:|
| `POST /api/aicss/v2/scripts/*` (全部) | Pydantic ✅ | Pydantic ✅ | **高** |
| `POST /api/aicss/v2/sequences/*` | Pydantic ✅ | Pydantic ✅ | **高** |
| `GET /api/aicss/v2/meshes/*` | — | Pydantic ✅ | **高** |
| `POST /api/aicss/analyze` | Pydantic ✅ | `AnalyzeResponse` ✅ | **高** |
| `POST /api/aicss/inpaint` | Pydantic ✅ | `InpaintResponse` ✅ | **高** |
| `POST /api/aicss/paper-diorama` | Pydantic ✅ | `PaperDioramaResponse` ✅ | **高** |
| `POST /api/aicss/depth` | Pydantic ✅ | `DepthResponse` ✅ | **高** |
| `POST /api/aicss/segment` | Pydantic ✅ | `SegmentResponse` ✅ | **高** |
| `POST /api/aicss/layers` | Pydantic ✅ | `LayersResponse` ✅ | **高** |
| `GET/POST /api/aicss/settings` | POST 体为 `SettingsUpdate` | `-> dict` ⚠️ | 低 |

**仍不清的边界**：`endpoints_settings.py` 的 GET/POST 直接返回 `dict`，OpenAPI 推不出设置字段。`endpoints.py` 约 1360 行，分析类 POST 已声明 `response_model`。

#### 前端-后端耦合

前端通过 `openapi-typescript-codegen` 生成的类型安全客户端调用后端（T16，2026-09-27 已完成）。`frontend/src/services/generated/` 下 `AicssClient` + 15 个 service 类覆盖全部 v1/v2 端点，6 个手写 service（`scriptService`/`aicssService`/`sequenceService`/`meshExportService`/`settingsService`/`composeService`）已改为薄封装调用生成客户端，保留导出签名以维持调用方契约。

字段映射（camelCase ↔ snake_case）在薄封装层显式处理，后端字段改名会在 `npm run gen:api` 重新生成客户端后于 service 层暴露为类型错误。

> **遗留**：`frontend/openapi.json` 是离线 schema 快照，后端改字段后需手动重跑 `npm run gen:api`（脚本已修布尔 flag bug）；`npm run check:schema` 已修复（2026-09-27：临时目录改 `frontend/.schema-check-tmp/` + Node fs SHA-256 递归比对，exit 0，225 文件匹配）。paper-diorama/layer/style 字段名兼容性已静态确认无 bug（后端 camelCase 无 alias，薄封装优先读 camelCase 输出 snake_case，组件读 snake_case，全链路对齐）。

### 7.4 代码级耦合问题详解

#### 问题 1：~~`settings_manager` 直接修改全局单例（内容耦合）—— D级~~ ✅ 已解决

**位置**：`services/settings_manager.py` 的 `update_settings()`

**状态**（T15，2026-09-27 已解决）：`setattr(settings, key, coerced)` 已移除。`settings_manager` 改用 `_runtime_values` 字典作为运行时配置唯一真相源，`seed_overrides()` 在首次调用时从 `config.settings` 默认值快照初始化。`local_llm` / `image_generator` / `cloud_router` 改读 `settings_manager.get()`；`settings_store` 改用 `seed_overrides()`；`settings_observer` 改用 `set_runtime_value()`。observer 现在与状态写入是同一真相源，不再是「附加」。

#### 问题 2：`local_llm` 模块级全局状态（控制耦合）—— C级 ⚠️

**位置**：`services/local_llm.py` 约第 283-308 行

```python
class LLMMode(str, Enum):
    CLOUD = "cloud"
    LOCAL = "local"

_llm_mode_ctx: ContextVar[LLMMode] = ContextVar("llm_mode", default=None)
_use_cloud: bool = False  # set_use_cloud() 仍同时写这个模块级变量
```

**影响**：`llm_mode_scope()` 可以按调用覆盖模式。未设置上下文时仍回退到 `_use_cloud`。

#### 问题 3：`image_generator` 模块级单例（控制耦合）—— C级 ⚠️

**位置**：`services/image_generator.py` 约第 759 行起；包装器在 `image_generator_interface.py` 的 `RLockImageGenerator`

```python
_img_gen: Optional[LocalImageGenerator] = None
_img_gen_lock = threading.Lock()

def configure_image_generator(model_id: str, dtype_name: str) -> None:
    with _img_gen_lock:
        if _img_gen is not None:
            _img_gen.unload()  # RLockImageGenerator.unload 会先等在途 generate()
        _img_gen = _wrap_singleton(LocalImageGenerator(...))
```

**影响**：单例还在。生成与重配置通过 `RLockImageGenerator._gate` 串行，不再是无锁抢卸。

#### 问题 4：设置接口响应无 Pydantic 模型 —— 中等 ⚠️

**位置**：`endpoints_settings.py` 的 `get_settings` / `post_settings`

这两个处理函数标注为 `-> dict`。`endpoints.py` 的分析类 POST（analyze、depth、segment、layers、inpaint、paper-diorama、paper-layer 等）已经使用 `response_model`。

#### 问题 5：`spatial_utils` 隐式依赖全局配置（间接耦合）—— 轻微 ⚠️

**位置**：`utils/spatial_utils.py` 第 6 行

```python
from ..config import settings  # 仅用 settings.depth_buckets
```

如果配置被热更新，`assign_to_depth_layer()` 的行为会隐式变化。

### 7.5 解耦改进建议

#### 高优先级

| 优先级 | 建议 | 目标 |
|:------:|------|------|
| ~~P0-1~~ | ~~`settings_manager` 去掉 `setattr(settings, ...)`，只经 observer 写状态~~ | **已完成**（T15，2026-09-27）：`_runtime_values` 单一真相源，`setattr` 已移除，D 级耦合消除 |
| ~~P0-2~~ | ~~为 `endpoints.py` 的 v1 分析端点补充 Pydantic 响应模型~~ | **已完成**：analyze / depth / segment / layers / inpaint / paper-* 均有 `response_model`。设置接口仍返回 `dict` |
| ~~P1-1~~ | ~~去掉 `local_llm` 的模块级 `_use_cloud` 回退，只留 `LLMMode` 上下文~~ | **部分完成**：`LLMMode` 与 `llm_mode_scope()` 已在；`set_use_cloud()` 仍双写 `_use_cloud` 作为回退（C 级未升） |
| ~~P1-2~~ | ~~前端集成 `openapi-typescript-codegen` 自动生成类型安全客户端~~ | **已完成**（T16，2026-09-27）：`src/services/generated/` + 6 个 service 薄封装 |

#### 中优先级

| 优先级 | 建议 | 目标 |
|:------:|------|------|
| P2-1 | 为 `CloudRouter` 缓存加 `threading.Lock` | 线程安全 |
| P2-2 | 工具模块（`spatial_utils` 等）参数化配置依赖 | 消除隐式依赖 |
| ~~P2-3~~ | ~~为 `image_generator` 引入 `ImageGeneratorInterface` 抽象~~ | **已完成**：`image_generator_interface.py` 的 `ImageGeneratorInterface` + `RLockImageGenerator` |

---

*本报告主体基于 2026-08-09 / 2026-08-10 代码审查。2026-09-26 按当前仓库改正了与代码不符的条目（Blender 插件与图层导入、Three.js 运镜、视频模型 `wan2.5-i2v-preview`、设置接口 POST、v1 `response_model`、图像生成器锁）。2026-09-27 并入 `EXECUTION_TASKS.md` 的 T01–T17 全部交付物（后期剪辑管线、Blender 运镜/渲染队列/帧动画/图层运动/SSS/光照、settings 解耦、前端 openapi codegen）+ 阶段五技术债清理（16 个预存 tsc 错误清零、`check:schema` 脚本修复、paper-diorama 字段名确认无 bug）。综合完成度约 96%，剩余仅依赖完整运行环境的 E2E 实跑验证。*
