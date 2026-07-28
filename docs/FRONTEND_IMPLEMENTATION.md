# 前端实现与需求匹配评估报告

> **评估日期**：2026-07-27
>
> **前端技术栈**：React 19 + TypeScript + Vite + TailwindCSS + Zustand + Three.js + @react-three/fiber + Axios

---

## 目录

1. [组件总览](#1-组件总览)
2. [Store 架构](#2-store-架构)
3. [服务层 API 映射](#3-服务层-api-映射)
4. [类型定义与后端对照](#4-类型定义与后端对照)
5. [模块匹配度总表](#5-模块匹配度总表)
6. [缺口与待办事项](#6-缺口与待办事项)

---

## 1. 组件总览

### 1.1 组件清单

| 组件 | 文件路径 | 功能描述 | 代码行数 |
|------|----------|----------|----------|
| `App` | `src/App.tsx` | 主布局：三种模式切换（Single/Sequence/Script） | 665 |
| `ScriptEditor` | `src/components/ScriptEditor.tsx` | 剧本编辑器（5 标签页） | 967 |
| `Viewer3D` | `src/components/Viewer3D.tsx` | Three.js 3D 纸雕查看器 | 532 |
| `SplitControls` | `src/components/SplitControls.tsx` | 图像拆分与补全控制面板 | 979 |
| `ExportPanel` | `src/components/ExportPanel.tsx` | PNG/GLB/FBX 导出 | 370 |
| `SettingsPanel` | `src/components/SettingsPanel.tsx` | 运行时设置面板 | 322 |
| `DioramaSettingsPanel` | `src/components/DioramaSettingsPanel.tsx` | 纸雕参数控制 | 369 |
| `ImageCanvas` | `src/components/ImageCanvas.tsx` | 2D 画布（物体标注 + 手绘选区） | 239 |
| `DepthSplitPanel` | `src/components/DepthSplitPanel.tsx` | 深度分层预览（2×2 网格） | 146 |
| `LayerSelector` | `src/components/LayerSelector.tsx` | 15 色块层级分配 | 120 |
| `InpaintPreviewDialog` | `src/components/InpaintPreviewDialog.tsx` | 修复结果对比对话框 | 75 |
| `PolygonDrawTool` | `src/components/PolygonDrawTool.tsx` | 自由多边形绘制 | 291 |
| `SequencePanel` | `src/components/sequence/SequencePanel.tsx` | 帧序列分析面板 | 271 |
| `SequencePlayer` | `src/components/sequence/SequencePlayer.tsx` | 帧播放控制器 | 104 |

### 1.2 组件与模块对应关系

```
App.tsx (Single Mode)
├── ImageCanvas.tsx          ──► 模块 3 (场景分层) + 模块 4 (遮挡补全)
├── LayerSelector.tsx         ──► 模块 3 (对象分层)
├── SplitControls.tsx         ──► 模块 3 + 模块 4 + 模块 7
│   ├── DepthSplitPanel.tsx  ──► 模块 3 (分层预览)
│   └── InpaintPreviewDialog  ──► 模块 4 (补全预览)
├── PolygonDrawTool.tsx       ──► 模块 4 (手动选区)
├── Viewer3D.tsx              ──► 模块 6 (3D预览) + 模块 7 + 模块 8
├── DioramaSettingsPanel.tsx  ──► 模块 7 (材质参数)
└── ExportPanel.tsx           ──► 模块 6 (Blender导出)

App.tsx (Script Mode)
└── ScriptEditor.tsx
    ├── ScriptTab             ──► 模块 1 (剧本解析)
    ├── StoryboardTab         ──► 模块 1 (分镜预览)
    ├── CharactersTab          ──► 模块 2 (角色资产生成)
    ├── MotionTab             ──► 模块 2 + 模块 9 (动作视频)
    └── ScenesTab             ──► 模块 1 + 模块 9 (场景关键帧)

App.tsx (Sequence Mode)
├── SequencePanel.tsx         ──► 模块 11 (帧序列分析)
└── SequencePlayer.tsx       ──► 模块 11 (播放控制)
```

---

## 2. Store 架构

### 2.1 四大 Store

| Store | 文件路径 | 职责范围 | 行数 |
|-------|---------|---------|------|
| `useAppStore` | `src/store/useAppStore.ts` | Single Image Editor 状态 | 767 |
| `useScriptStore` | `src/store/useScriptStore.ts` | 剧本解析与镜头生成 | 684 |
| `useSettingsStore` | `src/store/useSettingsStore.ts` | 运行时配置 | 133 |
| `useSequenceStore` | `src/store/useSequenceStore.ts` | 帧序列分析 | 203 |

### 2.2 useAppStore — 核心数据结构

```
图像数据
├── originalImageUrl / originalImageBase64   # 原始图片
├── croppedImageUrl / cropParams           # 裁剪结果
└── currentImageUrl / currentImageBase64   # 当前显示（含 strip 操作）

分析结果
├── analysisResult: AicssResult             # 深度图 + 物体 + 场景图
├── isAnalyzing / analysisError

层级分配（15 色块）
├── assignments: objectId → colorIndex      # 物体到颜色层
├── selectedLayerIndex                      # 当前选中层
└── regions: LayerRegion[]                  # 手绘多边形区域

Strip 流水线（逐层剥离）
├── stripStack: StripStep[]                 # 已完成步骤历史
├── isStripping / stripError
└── pushStripStep() / undoLastStripStep() / resetStripStack()

Billboard 资源
├── billboardAssets: Record<id, BillboardAsset>   # 单物体 RGBA
├── depthLayerBillboardAssets                       # 按深度层 RGBA
└── billboardOffsets                                 # 3D 偏移

深度分层
├── depthSplitResult: DepthSplitResult      # 四层 RGBA
├── depthSplitThresholds                   # 阈值配置
└── selectedDepthLayer: DepthLayerKey      # 前景/中景/背景/天空

Paper Diorama
├── dioramaParams: PaperDioramaParams       # 厚度/描边/视差参数
├── depthLayerDioramaAssets / objectDioramaAssets
├── dioramaMode: 'billboard' | 'paper'    # 渲染模式
└── outlineEnabled / parallaxEnabled / parallaxIntensity

撤销/重做
├── past[] / future[]                       # 双栈结构
└── undo() / redo() / pushHistory()

绘制模式
├── drawMode: 'idle' | 'drawing'          # 绘制状态
└── drawPoints: PolygonPoint[]              # 实时顶点
```

**关键设计亮点**：
- 双栈撤销/重做（`past` + `future`）
- Strip 流水线状态机（逐层剥离 inpaint + billboard 提取）
- localStorage 持久化 DashScope API Key
- 键盘快捷键全局监听（Ctrl+Z/Y, Enter, Esc, Backspace）

### 2.3 useScriptStore — 剧本解析状态

```
输入
├── rawScript / language

解析结果
├── parsedScript: ScriptData
├── normalizedScript: string
└── extractedCharacters: Character[]

分镜数据
├── shots: Shot[]
├── sceneTransitions: SceneTransition[]
└── characterActionSequences

角色与动作
├── characterAssets: Record<charId, CharacterAsset>   # 三视图 + 变体
├── motionSequences: Record<key, MotionSequence>    # key = ${shotId}_${charId}
└── sceneAssets: Record<sceneId, SceneAsset>

UI 状态
├── activeTab: 'script' | 'storyboard' | 'characters' | 'motion'
├── selectedShotId / selectedCharacterId / selectedSceneId
├── isParsing / isGeneratingShots
├── isGeneratingCharacter: Record<charId, boolean>
├── isGeneratingMotion: Record<key, boolean>
└── isGeneratingSceneAsset: Record<sceneId, boolean>
```

**Character-first Pipeline**：

```
parseScript()
    │
    ├─► extractCharacters()         # 并行获取角色列表
    │
    ├─► /api/aicss/v2/scripts/parse
    │
    └─► pollAutoThreeView()         # 自动批量生成角色三视图（每 4s 轮询）
            │
            └─► pollAutoSceneAsset()  # 自动批量生成场景关键帧
```

### 2.4 Store 组件使用分布

| 组件 | Store | 用途 |
|------|-------|------|
| `App` | `useAppStore` | 读取图像/分析结果/模式切换 |
| `ImageCanvas` | `useAppStore` | 绘制状态/物体标注 |
| `Viewer3D` | `useAppStore` | billboard/纸雕参数 |
| `SplitControls` | `useAppStore` | strip 流水线/层级分配 |
| `DepthSplitPanel` | `useAppStore` | 分层结果预览 |
| `DioramaSettingsPanel` | `useAppStore` | 纸雕参数读写 |
| `ExportPanel` | `useAppStore` | 导出进度 |
| `PolygonDrawTool` | `useAppStore` | 绘制状态 |
| `LayerSelector` | `useAppStore` | 层级分配 |
| `ScriptEditor` | `useScriptStore` | 剧本/分镜/角色/动作状态 |
| `SettingsPanel` | `useSettingsStore` | 运行时配置 |
| `SequencePanel` | `useSequenceStore` | 序列数据/播放控制 |
| `SequencePlayer` | `useSequenceStore` | 帧导航/播放 |

---

## 3. 服务层 API 映射

### 3.1 aicssService.ts（共 209 行）

| 函数 | 端点 | 对应模块 |
|------|------|---------|
| `analyzeImage` | `POST /api/aicss/analyze` | 模块 3+4 |
| `generateBillboard` | `POST /api/aicss/billboard` | 模块 4 |
| `generateMultiface` | `POST /api/aicss/multiface` | 模块 4 |
| `inpaintImage` | `POST /api/aicss/inpaint` | 模块 4 |
| `applyPaperStyle` | `POST /api/aicss/paper-style` | 模块 7（已废弃） |
| `generatePaperDiorama` | `POST /api/aicss/paper-diorama` | 模块 7 |
| `generatePaperLayer` | `POST /api/aicss/paper-layer` | 模块 7 |
| `extractRegionBillboard` | 内部调用 `generateBillboard` | 模块 4 |
| `checkHealth` | `GET /health` | 健康检查 |
| `checkModelsHealth` | `GET /health/models` | 模型可用性 |

### 3.2 scriptService.ts（共 484 行）

| 函数 | 端点 | 对应模块 |
|------|------|---------|
| `parseScript` | `POST /api/aicss/v2/scripts/parse` | 模块 1 |
| `extractCharacters` | `POST /api/aicss/v2/scripts/characters/extract` | 模块 2 |
| `generateShots` | `POST /api/aicss/v2/scripts/shots` | 模块 1 |
| `getScenePrompts` | `POST /api/aicss/v2/scripts/scene-prompts` | 模块 1 |
| `generateThreeView` | `POST /api/aicss/v2/scripts/characters/generate-three-view` | 模块 2 |
| `generateVariation` | `POST /api/aicss/v2/scripts/characters/generate-variation` | 模块 2 |
| `generateMotion` | `POST /api/aicss/v2/scripts/motion/generate` | 模块 2+9 |
| `segmentFrames` | `POST /api/aicss/v2/scripts/motion/segment` | 模块 2+9 |
| `generateVisualPrompt` | `POST /api/aicss/v2/scripts/visual-prompt` | 模块 1 |
| `getBatchStatus` | `GET /api/aicss/v2/scripts/characters/batch-status` | 模块 2 |
| `getSceneBatchStatus` | `GET /api/aicss/v2/scripts/scenes/batch-status` | 模块 9 |
| `generateSceneAsset` | `POST /api/aicss/v2/scripts/scenes/generate-asset` | 模块 9 |

### 3.3 meshExportService.ts（共 189 行）

| 函数 | 端点 | 对应模块 |
|------|------|---------|
| `checkBlenderAvailable` | `GET /api/aicss/v2/meshes/check` | 模块 6 |
| `exportMeshObjects` | `POST /api/aicss/v2/meshes/export-objects` | 模块 6 |
| `exportMeshLayers` | `POST /api/aicss/v2/meshes/export-layers` | 模块 6 |
| `exportMeshScene` | `POST /api/aicss/v2/meshes/export-scene` | 模块 6 |
| `listMeshExports` | `GET /api/aicss/v2/meshes/list` | 模块 6 |
| `getMeshInfo` | `GET /api/aicss/v2/meshes/{id}/info` | 模块 6 |
| `deleteMeshExport` | `DELETE /api/aicss/v2/meshes/{id}` | 模块 6 |
| `downloadMeshFile` | `GET /api/aicss/v2/meshes/{id}/download` | 模块 6 |

### 3.4 sequenceService.ts（共 119 行）

| 函数 | 端点 | 对应模块 |
|------|------|---------|
| `analyzeSequence` | `POST /api/aicss/v2/sequences` | 模块 11 |
| `analyzeFromScript` | `POST /api/aicss/v2/sequences/from-script` | 模块 11 |
| `getSequence` | `GET /api/aicss/v2/sequences/{id}` | 模块 11 |
| `getSceneLinks` | `GET /api/aicss/v2/sequences/{id}/scene-links` | 模块 11 |
| `getCrossFrameObject` | `GET /api/aicss/v2/sequences/{id}/objects/{globalId}` | 模块 11 |
| `createSequenceWebSocket` | `WS /api/aicss/v2/ws/sequences/{id}` | 模块 11（实时进度） |

---

## 4. 类型定义与后端对照

### 4.1 类型文件清单

| 文件 | 行数 | 核心类型 |
|------|------|----------|
| `types/index.ts` | 465 | AicssResult, DetectedObject, LayerRegion, DepthSplitResult, PaperDioramaParams |
| `types/script.ts` | 376 | ScriptData, Shot, Character, MotionSequence, SceneTransition |
| `types/sequence.ts` | 189 | SequenceResult, FrameResult, CrossFrameObject, SceneLink |

### 4.2 后端对照

| 前端类型 | 后端文件 | 后端 dataclass / Model | 一致性 |
|---------|---------|----------------------|--------|
| `ScriptData` | `script_parser.py` | `ScriptData` | ✅ |
| `Character` | `script_parser.py` | `Character` | ✅ |
| `Scene` | `script_parser.py` | `Scene` | ✅ |
| `StoryParagraph` | `script_parser.py` | `StoryParagraph` | ✅ |
| `Shot` | `shot_generator.py` | `Shot` | ✅ (需 camelCase↔snake_case 转换) |
| `CameraMovement` | `shot_generator.py` | `CameraMovement` 枚举 | ✅ |
| `ShotSize` | `shot_generator.py` | `ShotSize` 枚举 | ✅ |
| `SceneTransition` | `shot_generator.py` | `SceneTransition` | ✅ |
| `CharacterActionSequence` | `shot_generator.py` | `CharacterActionSequence` | ✅ |
| `MotionSequence` | `motion_extractor.py` | `MotionSequence` | ✅ |
| `DepthLayerKey` | `spatial_utils.py` | `Literal["foreground","midground","background","sky"]` | ✅ |
| `SequenceResult` | `endpoints_sequence.py` | `SequenceResult` (Pydantic) | ✅ |
| `FrameResult` | `endpoints_sequence.py` | `FrameResult` (Pydantic) | ✅ |
| `CrossFrameObject` | `endpoints_sequence.py` | `CrossFrameObject` (Pydantic) | ✅ |
| `SceneLink` | `endpoints_sequence.py` | `SceneLink` (Pydantic) | ✅ |
| `ObjectAppearanceDetail.layer` | `endpoints_sequence.py` | `Optional[DepthLayerKey]` | ⚠️ 前端为必需，后端为可选 |

### 4.3 序列化辅助函数

| 函数 | 文件 | 功能 |
|------|------|------|
| `serializeScriptData()` | `types/script.ts` | ScriptData camelCase → snake_case |
| `deserializeScriptData()` | `types/script.ts` | snake_case → ScriptData camelCase |
| `serializeShots()` | `types/script.ts` | Shot[] camelCase → snake_case |
| `deserializeShots()` | `types/script.ts` | Shot[] snake_case → camelCase |

---

## 5. 模块匹配度总表

### 5.1 匹配度矩阵

| # | 模块 | 前端覆盖度 | 主要组件 | 状态 | 缺口 |
|---|------|:----------:|---------|------|------|
| 1 | 自动化剧本拆解 | 95% | ScriptEditor (5 Tab) | ✅ | 网格化分镜表展示组件 |
| 2 | 人物资产生成与动作提取 | 85% | ScriptEditor CharactersTab + MotionTab | ✅ | Motion 后续动画绑定 |
| 3 | 场景分层分割 | 95% | SplitControls + ImageCanvas + depthSplit.ts | ✅ | 无明显缺口 |
| 4 | 遮挡区域补全与三维面片导出 | 90% | SplitControls + ExportPanel + inpaintMask.ts | ⚠️ | 剥离流水线 undo 未覆盖 billboard |
| 5 | 文件整合与分镜归档 | 50% | db.ts (IndexedDB) | ⚠️ | 无完整项目保存/加载 |
| 6 | Blender 场景自动搭建 | 40% | ExportPanel + meshExportService.ts | ⚠️ | 仅导出，无 Blender 自动化脚本 |
| 7 | 纸张材质统一应用 | 95% | DioramaSettingsPanel + Viewer3D | ✅ | 无明显缺口 |
| 8 | 环境与光照自动配置 | 25% | Viewer3D (硬编码光源) | ❌ | 无光照预设 UI，无 HDRI 支持 |
| 9 | 场景运动与角色动画 | 60% | ScriptEditor MotionTab + SequencePlayer | ⚠️ | Blender 角色帧动画缺失 |
| 10 | 镜头运镜与渲染输出 | 35% | Viewer3D (OrbitControls) | ❌ | 无相机路径 UI，无视频渲染 |
| 11 | 后期剪辑与成片 | 45% | SequencePanel + SequencePlayer | ⚠️ | 无剪辑时间线，无视频导出 |

### 5.2 功能覆盖率分析

```
前端已实现的核心功能：
├── 剧本解析全链路（输入 → 解析 → 分镜 → 角色 → 动作）
├── 图像分析全链路（深度估计 → 物体检测 → 场景分层 → 纸雕化）
├── 3D 预览（Billboard + Paper Diorama 双模式）
├── Strip 流水线（逐层剥离 inpaint + billboard）
├── 手动多边形选区 + 深度采样
├── GLB/FBX/PNG 导出
├── IndexedDB 会话恢复
├── WebSocket 实时进度（序列分析）
└── 三种编辑模式（Single / Sequence / Script）

前端未实现或缺失的功能：
├── Blender Python 脚本自动生成
├── 相机路径编辑器（关键帧/贝塞尔曲线）
├── 视频渲染输出
├── 完整视频剪辑时间线
├── 角色骨骼绑定与 Blender 帧动画
├── 光照预设选择器 + HDRI
├── 完整项目保存/加载（含分镜表 + 角色资产）
└── 一键端到端执行（剧本 → 成片）
```

---

## 6. 缺口与待办事项

### 6.1 P0 — 阻塞性缺口

#### P0-1: Blender 自动化脚本

**缺口描述**：前端仅实现了 mesh 文件的导出调用，无 Blender 独立插件或 Python 脚本自动生成功能。

**相关文件**：
- `services/meshExportService.ts` — 仅调用后端导出端点
- `components/ExportPanel.tsx` — 仅触发 GLB/FBX 下载

**待实现**：
1. Blender 场景自动搭建 Python 脚本（自动放置 billboard 到坐标 + 构建层级关系）
2. Blender 材质节点自动配置（Normal Map + SSS + 纸张纤维）
3. Blender 光照自动配置脚本

#### P0-2: 镜头运镜系统

**缺口描述**：Viewer3D 仅支持手动 OrbitControls 旋转，无相机路径定义和自动运镜播放。

**相关文件**：
- `components/Viewer3D.tsx` — OrbitControls 手动控制
- `types/script.ts` — CameraMovement 枚举已定义但未使用

**待实现**：
1. 相机路径编辑器 UI（关键帧 + 贝塞尔曲线）
2. 相机路径动画预览播放
3. 运镜数据 → Three.js 相机路径转换

#### P0-3: 视频渲染输出

**缺口描述**：ExportPanel 仅支持 PNG 截图和 mesh 下载，无最终成片渲染输出。

**待实现**：
1. Three.js 场景逐帧渲染（canvas → PNG 序列）
2. ffmpeg 视频合成（帧序列 → MP4）
3. 运镜数据驱动渲染队列

### 6.2 P1 — 核心功能缺口

#### P1-1: 完整视频剪辑时间线

**缺口描述**：SequencePanel 仅有帧导航和播放控制，无剪辑时间线 UI。

**相关文件**：
- `components/sequence/SequencePanel.tsx` — 271 行
- `store/useSequenceStore.ts` — 203 行

**待实现**：
1. 时间线编辑器 UI（剪切/拼接/转场）
2. 镜头运镜关键帧编辑
3. 音频轨（BGM / 音效）UI

#### P1-2: 角色骨骼绑定与帧动画

**缺口描述**：Motion Tab 可以触发视频生成，但 SAM2 分割帧后无角色骨骼绑定和 Blender 动画生成。

**待实现**：
1. 角色骨骼自动绑定流程
2. Blender 帧序列导入
3. Blender 角色播放动画导出

#### P1-3: 光照预设与 HDRI

**缺口描述**：Viewer3D 中硬编码了三种光源，无光照预设选择器，无 HDRI 环境贴图支持。

**待实现**：
1. 光照预设选择器（日间/黄昏/夜间/阴天等）
2. HDRI 环境贴图加载和显示
3. 实时光照参数调节面板

### 6.3 P2 — 质量增强缺口

#### P2-1: Strip 流水线 Undo 覆盖范围

**缺口描述**：undo 历史仅覆盖 inpaint 图像，未覆盖 billboard 生成结果。

**相关文件**：
- `store/useAppStore.ts` — `pushStripStep()` / `undoLastStripStep()`
- `components/SplitControls.tsx` — `handleUndo()`

**待修复**：`pushStripStep()` 应同时保存 inpaint 图像和 billboard 生成结果。

#### P2-2: 完整项目保存/加载

**缺口描述**：IndexedDB 仅存储会话数据（裁剪图），无完整项目保存（含分镜表、角色资产等）。

**相关文件**：
- `utils/db.ts` — `saveSession()` / `loadSession()`

**待实现**：
1. 完整项目 JSON 导出（含 ScriptData + Shots + CharacterAssets）
2. 项目恢复时自动重新生成资产

#### P2-3: ObjectAppearanceDetail.layer 类型不一致

**缺口描述**：前端 `ObjectAppearanceDetail.layer` 定义为必需字段，后端为可选。

**相关文件**：
- `types/sequence.ts` — `ObjectAppearanceDetail` 接口
- `backend/app/endpoints_sequence.py` — `ObjectAppearanceDetail` Pydantic 模型

**建议**：前端改为可选 `layer?: DepthLayerKey`

### 6.4 P3 — 便利性缺口

#### P3-1: 一键端到端执行

**缺口描述**：用户需手动触发每个步骤（解析 → 分镜 → 角色 → 动作 → 导出）。

**待实现**：一键自动化执行完整端到端流程（剧本 → 分镜 → 资产 → 动画 → 成片）。

#### P3-2: 分镜卡片导出

**缺口描述**：无将分镜表导出为 PDF/JSON 的功能。

**待实现**：StoryboardTab 添加"导出分镜本"功能。

---

## 附录 A：目录结构

```
frontend/src/
├── App.tsx                               # 主布局
├── components/
│   ├── ScriptEditor.tsx                  # 剧本编辑器（5 Tab）
│   ├── Viewer3D.tsx                      # Three.js 3D 查看器
│   ├── SplitControls.tsx                  # 拆分与补全控制
│   ├── ExportPanel.tsx                    # 导出面板
│   ├── SettingsPanel.tsx                  # 设置面板
│   ├── DioramaSettingsPanel.tsx           # 纸雕参数面板
│   ├── ImageCanvas.tsx                    # 2D 画布
│   ├── DepthSplitPanel.tsx               # 深度分层预览
│   ├── LayerSelector.tsx                  # 层级选择器
│   ├── InpaintPreviewDialog.tsx          # 修复预览
│   ├── PolygonDrawTool.tsx               # 多边形绘制
│   └── sequence/
│       ├── SequencePanel.tsx             # 帧序列分析
│       └── SequencePlayer.tsx            # 帧播放器
├── services/
│   ├── aicssService.ts                   # 图像分析 API
│   ├── scriptService.ts                  # 剧本 API
│   ├── meshExportService.ts              # 3D 导出 API
│   ├── sequenceService.ts                # 序列 API
│   └── settingsService.ts                # 设置 API
├── store/
│   ├── useAppStore.ts                    # 全局状态（767 行）
│   ├── useScriptStore.ts                 # 剧本状态（684 行）
│   ├── useSettingsStore.ts               # 设置状态
│   └── useSequenceStore.ts               # 序列状态
├── types/
│   ├── index.ts                          # 共享类型（465 行）
│   ├── script.ts                         # 剧本类型（376 行）
│   └── sequence.ts                       # 序列类型（189 行）
└── utils/
    ├── depthSplit.ts                      # 深度分层算法
    ├── depthUtils.ts                      # 深度图处理工具
    ├── inpaintMask.ts                     # 修复遮罩计算
    ├── db.ts                              # IndexedDB 持久化
    └── resolution.ts                       # 分辨率计算
```

## 附录 B：前端 vs 后端功能覆盖对照

| 功能 | 前端实现 | 后端实现 | 覆盖情况 |
|------|---------|---------|---------|
| 剧本两段式解析 | ScriptEditor + useScriptStore | script_parser.py | ✅ 完整 |
| 分镜表生成 | StoryboardTab | shot_generator.py | ✅ 完整 |
| 角色三视图生成 | CharactersTab + pollAutoThreeView | character_generator.py + auto_three_view.py | ✅ 完整 |
| 动作视频生成 | MotionTab | motion_extractor.py | ✅ 完整 |
| 深度估计 | ImageCanvas 显示 | depth_loader.py | ✅ 完整 |
| 物体检测 | ImageCanvas 标注 | grounding_dino_loader.py | ✅ 完整 |
| SAM2 分割 | ImageCanvas 标注 | sam2_loader.py | ✅ 完整 |
| 深度分层 | DepthSplitPanel 2x2 网格 | spatial_utils.py | ✅ 完整 |
| 纸雕纹理生成 | DioramaSettingsPanel | paper_diorama.py | ✅ 完整 |
| 3D 预览 | Viewer3D (Billboard + Paper) | — | ✅ 完整 |
| Blender 导出 | ExportPanel | mesh_exporter.py | ⚠️ 仅下载调用 |
| 帧序列分析 | SequencePanel | endpoints_sequence.py | ✅ 完整 |
| WebSocket 进度 | sequenceService.ts | endpoints_sequence.py | ✅ 完整 |
| 场景关键帧生成 | ScenesTab | scene_generator.py | ✅ 完整 |
| 遮罩绘制 | PolygonDrawTool | — | ✅ 完整 |
| Strip 流水线 | SplitControls | endpoints.py | ✅ 完整 |
| 会话恢复 | db.ts (IndexedDB) | — | ⚠️ 仅裁剪图 |

---

*本报告基于 2026-07-27 代码库状态生成。*
