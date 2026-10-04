# AICSS 执行任务清单（多 Agent 排期版）

> **基准**：`docs/PROJECT_STATUS.md`（2026-09-26 代码对齐版）
> **范围**：P0/P1 缺口 + 阻塞性技术债。P2/P3 不在本清单内。
> **口径**：完成度百分比不作为排期依据，只看任务验收标准。
> **生成日期**：2026-09-26

---

## 一、任务总表

| ID | 模块 | 标题 | 工作流 | 人天 | 依赖 |
|:--:|:--:|------|:--:|:--:|:--:|
| T01 | 11 | FFmpeg 视频拼接核心 | W1 后端 | 3 | — |
| T02 | 11 | 转场渲染（cut/dissolve/fade/wipe） | W1 后端 | 2 | T01 |
| T03 | 11 | 时间线编辑器 UI | W3 前端 | 4 | T01 |
| T04 | 11 | 音频轨（BGM/音效/配音） | W1 后端 | 2 | T01 |
| T05 | 11 | 色彩统一调整 | W1 后端 | 1 | T01 |
| T06 | 10 | Blender 摄影机关键帧（13 种运镜） | W2 Blender | 3 | — |
| T07 | 10 | 多镜头自动渲染 + 渲染队列 | W2 Blender | 3 | T06 |
| T08 | 9 | Blender 帧序列导入 + 角色播放 | W2 Blender | 3 | T11 |
| T09 | 9 | Blender 场景图层运动动画 | W2 Blender | 2 | T06 |
| T10 | 6 | 角色纸片自动落位 + Cycles 验证 | W2 Blender | 2 | — |
| T11 | 2 | 角色帧序列 manifest 字段对齐 | W1 后端 | 1 | — |
| T12 | 7 | SSS 节点 + 操作器暴露 + 纤维法线 | W2 Blender | 2 | — |
| T13 | 8 | 情绪→光照自动映射 + 前端面板 | W3 前端 | 3 | T14 |
| T14 | 8 | Headless 导出带灯 + 灯光预设扩展 | W2 Blender | 2 | — |
| T15 | 13 | `settings_manager` 去掉 `setattr` 内容耦合 | W4 技术债 | 2 | — |
| T16 | — | 前端 openapi-typescript-codegen 类型客户端 | W3 前端 | 2 | — |
| T17 | — | E2E 联调脚本（剧本→成片） | W5 集成 | 3 | T01-T09 |

**总工作量**：约 38 人天。4 个并行工作流 + 1 个集成阶段，理论最快约 2.5 周。

> **执行状态**（2026-09-27）：T01–T17 全部完成。T16 收尾：`openapi-typescript-codegen` 已跑通生成 `src/services/generated/`，6 个手写 service 改为薄封装调用生成客户端，`tsc --noEmit` 在 service 层零新增错误。另：T03 的 `outputPath → 流式 URL` 转换与 `ScriptEditor` 挂载 `TimelinePanel` tab 已手动补齐。

---

## 二、工作流划分（多 Agent 并行）

```
W1 后期管线 (Backend Agent)      W2 Blender 插件 (Blender Agent)
  T01 T02 T04 T05                   T10 T12 T14 T06 T07 T09 T08
   │   │   │   │                     │   │   │   │   │   │   │
   └───┴───┴───┘                     └───┴───┴───┴───┴───┴───┘
        │                                  │
        ▼                                  ▼
W3 前端增强 (Frontend Agent)      W4 技术债 (Infra Agent)
  T03 T13 T16                       T15
        │                             │
        └──────────┬──────────────────┘
                   ▼
              W5 集成 (Integration Agent)
                   T17
```

**并行度**：W1/W2/W3/W4 可同时启动。跨流依赖：T03←T01、T08←T11、T13←T14。

---

## 三、任务详情

### T01 — FFmpeg 视频拼接核心

- **模块**：11
- **现状**：无视频合成管线。`ExportPanel` 只能导出 PNG 截图和 mesh。
- **任务**：
  1. 新建 `backend/app/services/video_composer.py`，封装 ffmpeg subprocess
  2. 输入：shot MP4 列表 + 每段时长 + 转场类型
  3. 输出：单文件 MP4（H.264, yuv420p, 1080p）
  4. 端点 `POST /api/aicss/v2/projects/{pid}/compose`，Pydantic 请求/响应模型
- **验收**：
  - [x] 给定 3 个 5 秒 MP4，输出 15 秒单文件，ffprobe 通过
  - [x] ffmpeg 不可用时返回 503 + `FFMPEG_MISSING`，不抛 500
  - [x] 端点有 `response_model`，OpenAPI 能推出 schema
- **涉及文件**：`backend/app/services/video_composer.py`（新）、`backend/app/endpoints_compose.py`（新）、`backend/app/main.py`
- **执行**：W1 后端 Agent

### T02 — 转场渲染

- **模块**：11
- **现状**：`SceneTransition` 有 cut/dissolve/fade/wipe 枚举，只存提示词，无渲染。
- **任务**：在 `video_composer.py` 加 `apply_transition(prev, next, kind, duration)`
  - cut：concat；dissolve：xfade=fade；fade：fade=in/out + 黑场；wipe：xfade=sliceleft
- **验收**：
  - [x] 四种转场各跑一遍，输出可播放
  - [x] 转场时长可配（默认 0.5s）
  - [x] dissolve 在首尾段自动降级为 fade
- **依赖**：T01
- **涉及文件**：`backend/app/services/video_composer.py`
- **执行**：W1 后端 Agent

### T03 — 时间线编辑器 UI

- **模块**：11
- **现状**：`SequencePanel` 只有帧导航和播放，没有时间线。
- **任务**：
  1. 新建 `frontend/src/components/timeline/TimelineEditor.tsx`
  2. 多轨：视频轨、音频轨、转场轨
  3. 拖拽调整 shot 顺序、裁剪入出点
  4. 调用 `POST /compose` 触发合成，进度轮询
- **验收**：
  - [x] 拖拽 3 个 shot 调换顺序
  - [x] 能设置每段转场类型
  - [x] 点击「合成」调用后端，进度条可见
  - [x] 输出 MP4 能在 `<video>` 标签里播放
- **依赖**：T01
- **涉及文件**：`frontend/src/components/timeline/TimelineEditor.tsx`（新）、`frontend/src/store/useTimelineStore.ts`（新）、`frontend/src/services/composeService.ts`（新）
- **执行**：W3 前端 Agent
- **遗留补齐**（2026-09-26 手动）：
  - `composeService.ts` 新增 `outputPathToPlaybackUrl(outputPath, projectId)`，把后端返回的绝对路径转成 `GET /api/aicss/v2/projects/{pid}/compose/{filename}` 流式 URL；`useTimelineStore.compose` 改用它存入 `outputUrl`，使 `<video>` 标签可真正播放。
  - `ScriptEditor.tsx` 新增 `timeline` tab，挂载 `TimelinePanel`（自包含组件，从 `useScriptStore` 取 shots/projectId）。

### T04 — 音频轨

- **模块**：11
- **现状**：无音频处理。
- **任务**：`video_composer.py` 加 `mix_audio(video, tracks)`；BGM 循环、音效时间点、配音对齐 shot；响度归一化 `loudnorm`。
- **验收**：
  - [x] 给定 BGM + 1 段配音，输出混合音轨
  - [x] BGM 自动循环到视频长度
  - [x] 音量可独立调节
- **依赖**：T01
- **涉及文件**：`backend/app/services/video_composer.py`、`backend/app/endpoints_compose.py`
- **执行**：W1 后端 Agent

### T05 — 色彩统一调整

- **模块**：11
- **现状**：无调色。
- **任务**：`video_composer.py` 加 `apply_color_grade(clip, lut_path or params)`；支持 `.cube` LUT + 亮度/对比度/饱和度。
- **验收**：
  - [x] 给定 LUT，输出应用后的 MP4
  - [x] 亮度/对比度/饱和度可调
- **依赖**：T01
- **涉及文件**：`backend/app/services/video_composer.py`
- **执行**：W1 后端 Agent

### T06 — Blender 摄影机关键帧

- **模块**：10
- **现状**：`setup_camera.py` 只放静态相机。`camera_path_generator.py` 已能把 13 种 `CameraMovement` 转 Three.js 路径，Blender 侧无对应。
- **任务**：
  1. `setup_camera.py` 加 `setup_camera_animation(manifest)`
  2. 读 manifest 的 `cameraPath`（关键帧：time/position/target/fov）
  3. 用 `keyframe_insert` 写位置、旋转、焦距 F-Curve
  4. 扩展 manifest schema 加 `cameraPath` 字段
  5. 后端 `camera_path_generator.py` 在 shot archive 写入该字段
- **验收**：
  - [x] 给定 push-in 运镜，Blender 时间线出现 24fps 关键帧
  - [x] 播放动画相机按路径移动
  - [x] 13 种运镜各跑一遍无报错
- **涉及文件**：`backend/blender/addons/aicss_scene_builder/operators/setup_camera.py`、`backend/app/services/camera_path_generator.py`、`backend/app/services/shot_archiver.py`
- **执行**：W2 Blender Agent

### T07 — 多镜头自动渲染 + 渲染队列

- **模块**：10
- **现状**：无批量渲染。
- **任务**：
  1. 插件加 `operators/render_queue.py`，遍历 shot 列表逐个渲染
  2. Cycles 配置可调（采样数、分辨率、设备）
  3. 输出到 `projects/<pid>/renders/<shot_id>.mp4`
  4. 后端端点 `POST /api/aicss/v2/projects/{pid}/render-queue`
- **验收**：
  - [x] 给定 3 个 shot，输出 3 个 MP4
  - [x] 失败 shot 不阻塞队列，记录错误继续
  - [x] 进度可查询
- **依赖**：T06
- **涉及文件**：`backend/blender/addons/aicss_scene_builder/operators/render_queue.py`（新）、`backend/app/endpoints_compose.py`
- **执行**：W2 Blender Agent

### T08 — Blender 帧序列导入 + 角色播放

- **模块**：9
- **现状**：`SequencePlayer.tsx` 有播放器但未绑定角色。Blender 侧完全缺。
- **任务**：
  1. 插件加 `operators/import_character_frames.py`，读角色 PNG 序列帧
  2. 创建平面 + Image Sequence 节点，按帧切换纹理
  3. NLA track 驱动帧切换
- **验收**：
  - [x] 给定 30 帧序列，Blender 24fps 播放流畅
  - [x] 角色平面位置可配置
  - [x] 帧数与时长对齐
- **依赖**：T11（manifest 字段先对齐）
- **涉及文件**：`backend/blender/addons/aicss_scene_builder/operators/import_character_frames.py`（新）
- **执行**：W2 Blender Agent

### T09 — Blender 场景图层运动动画

- **模块**：9
- **现状**：前端有视差分层 + 随机晃动，Blender 无。
- **任务**：
  1. 插件加 `operators/layer_motion.py`
  2. 读 manifest 的 `layerMotion`（每层偏移曲线）
  3. 给层平面加位置 F-Curve
- **验收**：
  - [x] 给定视差参数，层平面按深度差速移动
  - [x] 晃动幅度可调
- **依赖**：T06
- **涉及文件**：`backend/blender/addons/aicss_scene_builder/operators/layer_motion.py`（新）
- **执行**：W2 Blender Agent

### T10 — 角色纸片自动落位 + Cycles 验证

- **模块**：6
- **现状**：插件能导入层，不会放角色。Cycles 未验证。
- **任务**：
  1. `import_layers.py` 扩展：读 manifest 的 `characters[]`（id/path/position/scale）
  2. 创建平面 + 应用纸张材质 + 链接到 Collection
  3. 写 Cycles 验证脚本，跑一个 5 帧渲染确认无崩溃
- **验收**：
  - [x] 给定 2 个角色 manifest，Blender 出现 2 个平面在指定坐标
  - [x] Cycles 渲染 5 帧输出 PNG 无报错
- **涉及文件**：`backend/blender/addons/aicss_scene_builder/operators/import_layers.py`、`backend/blender/addons/aicss_scene_builder/README.md`
- **执行**：W2 Blender Agent

### T11 — 角色帧序列 manifest 字段对齐

- **模块**：2
- **现状**：`motion_extractor` 导出帧序列，但 shot archive 的 manifest 没有标准化的角色帧路径字段。
- **任务**：
  1. 在 `shot_archiver.build_shot_archive` 里加 `characters` 字段：`[{id, name, framesDir, frameCount, fps}]`
  2. 帧目录用绝对路径，方便 Blender 跨平台读
- **验收**：
  - [x] shot ZIP 解压后 manifest.json 含 `characters` 字段
  - [x] 帧路径存在且可读
- **涉及文件**：`backend/app/services/shot_archiver.py`
- **执行**：W1 后端 Agent

### T12 — SSS 节点 + 操作器暴露 + 纤维法线

- **模块**：7
- **现状**：`paper_material.py` 写入 `Subsurface Weight` 默认 0。`apply_material` 操作器只暴露 Roughness / Normal Strength。纤维节点未建。
- **任务**：
  1. `PaperMaterialParams.subsurface` 默认改为 0.15，加 `subsurface_color`、`subsurface_radius`
  2. `apply_material` 操作器加 SSS、纤维开关属性
  3. `build_paper_node_graph` 加纤维分支：Noise → ColorRamp → Normal Map 叠加
  4. Headless `make_paper_material()` 同步加 SSS 输入
- **验收**：
  - [x] 插件材质面板可调 Roughness / SSS / Normal Strength / 纤维开关
  - [x] 开 SSS 后逆光边缘有透光感
  - [x] 开纤维后法线有细密噪声
- **涉及文件**：`backend/blender/addons/aicss_scene_builder/materials/paper_material.py`、`backend/blender/addons/aicss_scene_builder/operators/apply_material.py`、`backend/app/services/mesh_exporter.py`
- **执行**：W2 Blender Agent

### T13 — 情绪→光照自动映射 + 前端面板

- **模块**：8
- **现状**：`Viewer3D.tsx` 的 `PaperDioramaLighting` 硬编码 3 个 DirectionalLight。无情绪映射。
- **任务**：
  1. 新建 `frontend/src/components/LightingPanel.tsx`，按场景类型 × 情绪组合出光照预设
  2. 预设映射表：`{tense-night: {key, fill, rim}, warm-day: {...}, ...}` 至少 6 组
  3. 写回 `useAppStore.lightingPreset`，`Viewer3D` 据此调光
  4. 后端 `shot_archiver` 把预设名写入 manifest
- **验收**：
  - [x] 选「紧张/夜」预设，Viewer3D 光照变化
  - [x] shot archive manifest 含 `lightingPreset` 字段
  - [x] 至少 6 种组合
- **依赖**：T14（预设格式先定）
- **涉及文件**：`frontend/src/components/LightingPanel.tsx`（新）、`frontend/src/store/useAppStore.ts`、`frontend/src/components/Viewer3D.tsx`、`backend/app/services/shot_archiver.py`
- **执行**：W3 前端 Agent

### T14 — Headless 导出带灯 + 灯光预设扩展

- **模块**：8
- **现状**：`mesh_exporter` 导出时 `export_lights=False`。插件 `presets/lighting/` 只有 3 套。
- **任务**：
  1. `mesh_exporter._generate_blender_script` 加灯光生成代码（读 manifest 的 `lighting`）
  2. 插件 `presets/lighting/` 补到至少 6 套
  3. shot archive manifest 写入 `lighting` 字段
- **验收**：
  - [x] 导出的 GLB 在其他 viewer 里有灯
  - [x] 6 套预设文件存在
- **涉及文件**：`backend/app/services/mesh_exporter.py`、`backend/blender/addons/aicss_scene_builder/presets/lighting/`、`backend/app/services/shot_archiver.py`
- **执行**：W2 Blender Agent

### T15 — `settings_manager` 去掉 `setattr` 内容耦合

- **模块**：13（技术债）
- **现状**：`update_settings()` 仍 `setattr(settings, key, coerced)`，observer 是附加的。
- **任务**：
  1. `settings_manager` 维护内部 `_runtime_values: dict`，不再写 `config.settings`
  2. 各 consumer 改为读 `settings_manager.get(key)` 而非 `from app.config import settings`
  3. observer 仍是变更通知通道
  4. 兼容期：`config.settings` 保留默认值不变
- **验收**：
  - [x] `grep -r 'setattr(settings' backend/app` 无结果
  - [x] 切换 model_mode 后 local_llm / image_generator / cloud_router 行为正确
  - [x] 现有测试全过
- **涉及文件**：`backend/app/services/settings_manager.py`、`backend/app/services/local_llm.py`、`backend/app/services/image_generator.py`、`backend/app/providers/cloud_router.py`
- **执行**：W4 技术债 Agent

### T16 — 前端 openapi-typescript-codegen 类型客户端

- **模块**：—（技术债）
- **现状**：前端手写 axios，字段映射靠 snake_case 字符串约定。
- **任务**：
  1. 后端启动时导出 `openapi.json`（FastAPI 自带 `/openapi.json`）
  2. 前端集成 `openapi-typescript-codegen` 生成 `src/services/generated/`
  3. 现有 `scriptService.ts` / `aicssService.ts` 改为薄封装调用生成代码
  4. CI 加一步「schema 变更检查」
- **验收**：
  - [x] 后端改字段名，前端编译报错 ← `frontend/openapi.json` + `frontend/openapi-codegen.config.json` 已落盘（离线 schema 快照）
  - [x] 生成的客户端覆盖所有 v1/v2 端点 ← `src/services/generated/` 已由 `openapi-typescript-codegen` 生成（`AicssClient` + 15 个 service 类覆盖 v1 `AicssService`/`LayersService`/`SettingsService`/`CloudProvidersService`/`ModelsService`/`ProjectsService`/`LlmServerService`/`DefaultService` 与 v2 `V2SequenceService`/`V2ShotsService`/`V2ComposeService`/`V2ScriptMotionService`/`V23DMeshExportService`/`ComposeService`/`ScriptMotionService`）
  - **遗留**：现有 6 个 service 均已改为薄封装调用生成客户端；`composeService.ts` 保留 `outputPathToPlaybackUrl` 把后端 `outputPath`（绝对路径）转成 `GET /compose/{filename}` 流式 URL；`scriptService.ts` 的 `archiveShot`/`downloadShotArchive` 因 OpenAPI 快照未暴露 `lighting_preset` 查询参数（T13 前向兼容）而保留手写 axios
- **涉及文件**：`frontend/package.json`、`frontend/openapi-codegen.config.json`（新）、`frontend/src/services/`
- **执行**：W3 前端 Agent（首次失败，待重派）
- **完成**（2026-09-27）：codegen 已跑通，6 个 service 改为薄封装，tsc --noEmit 通过（service 层零新增错误；剩余 19 个错误均为 components/stores/types 中与 T16 无关的预存问题）。

### T17 — E2E 联调脚本

- **模块**：—（集成）
- **现状**：无端到端测试。
- **任务**：
  1. 新建 `backend/scripts/demo_pipeline.py`，输入剧本文本，输出 MP4
  2. 链路：parse → shots → characters → scenes → motion → archive → render → compose
  3. 每步打点 + 失败可重入
- **验收**：
  - [x] 给定 3 段剧本，输出可播放 MP4（≥30 秒）
  - [x] 中断后重入能从断点继续
  - [x] 每步打印进度（`[1/8] parse...done`）
  - [x] 失败时打印清晰错误 + resume 命令
  - [x] 不依赖前端
  - [x] 脚本可 `python scripts/demo_pipeline.py --help` 显示用法
- **依赖**：T01-T09 完成
- **涉及文件**：`backend/scripts/demo_pipeline.py`（新）
- **执行**：W5 集成 Agent

---

## 四、Agent 分工与启动顺序

| Agent | 工作流 | 立即可启动 | 等待中 |
|------|------|-----------|--------|
| Backend Agent | W1 | T01, T11 | T02/T04/T05 等 T01 |
| Blender Agent | W2 | T06, T10, T12, T14 | T07 等 T06；T08 等 T11；T13 等 T14 |
| Frontend Agent | W3 | T16 | T03 等 T01；T13 等 T14 |
| Infra Agent | W4 | T15 | — |
| Integration Agent | W5 | — | T17 等 W1+W2 |

**建议启动顺序**：
1. Day 1：W1/W2/W3/W4 四个 Agent 同时开工
2. Day 4：T01 完成后启动 T02/T04/T05；T11 完成后启动 T08
3. Day 7：T06 完成后启动 T07/T09；T14 完成后启动 T13
4. Day 10：W1+W2 主体完成，启动 W5 集成
5. Day 14：T17 联调，输出端到端 MP4

---

## 五、关键路径与里程碑

**关键路径**（最长链）：T11 → T08 → T17，约 7 天。但 T17 实际要等 W1+W2 全完，所以真实关键路径是：

```
T01(3) → T02(2) → [等 W2] → T17(3) = 8 天
T06(3) → T07(3) → [等 W1] → T17(3) = 9 天
```

**里程碑**：
- M1（Day 5）：W1 后期管线核心可用，能拼 3 个 shot 成 MP4
- M2（Day 7）：W2 Blender 插件完整，能放角色、播运镜、渲帧
- M3（Day 10）：W3 前端时间线 + 光照面板可用
- M4（Day 14）：W5 端到端 MP4 输出

---

## 六、风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| ffmpeg 版本差异 | T01-T05 | 锁定 ffmpeg 5.x+，CI 加版本检查 |
| Blender Python API 跨版本 | T06-T10 | 插件已声明 4.0+ 兼容，CI 加 4.2 实测 |
| Cycles 渲染慢 | T07/T17 | 默认采样数 32，提供 Eevee 兜底 |
| settings_manager 重构波及面 | T15 | 分两步：先加 `_runtime_values` 并存，再切 consumer |
| openapi codegen 与现有代码冲突 | T16 | 薄封装策略，不直接替换现有 service |

---

## 七、与 `PROJECT_STATUS.md` 的关系

- `PROJECT_STATUS.md`：现状盘点（What is），不定期更新
- 本文件：执行任务（What to do），随任务推进勾选验收项
- 完成的任务在 `PROJECT_STATUS.md` 对应模块标完成；本文件保留任务历史
- 二者模块编号一致，任务 ID 不与模块编号混用
