# AICSS Frontend

AICSS 前端是基于 React 的界面层，负责图像导入、2D 掩码查看、图层分配、Billboard 生成、可选的局部重绘预览，以及 Three.js 3D 场景浏览。

---

## 职责

前端主要负责：

- 导入图像并统一到 1920×1080 工作分辨率
- 从用户处收集 DashScope API Key
- 调用后端分析与生成接口
- 在 2D 中展示 polygon 或矩形掩码叠加层
- 将检测对象分配到颜色图层
- 生成用于 3D 预览的 Billboard 贴图
- 从 IndexedDB 恢复最近一次持久化会话

---

## 技术栈

- React 19
- TypeScript 6
- Vite 8
- Tailwind CSS v4
- Zustand 5
- Axios
- Three.js + `@react-three/fiber` + `@react-three/drei`
- IndexedDB

---

## 项目结构

```text
frontend/
├── src/
│   ├── App.tsx                      根布局与顶层流程
│   ├── main.tsx                     React 启动入口
│   ├── index.css                    全局样式
│   ├── components/
│   │   ├── ImageCanvas.tsx          2D 叠加层视图
│   │   ├── LayerSelector.tsx        图层颜色面板
│   │   ├── SplitControls.tsx        Billboard 生成与 inpaint 操作
│   │   ├── InpaintPreviewDialog.tsx 重绘结果预览弹窗
│   │   └── Viewer3D.tsx             Three.js 场景视图
│   ├── services/
│   │   └── aicssService.ts          后端 API 客户端
│   ├── store/
│   │   └── useAppStore.ts           全局 Zustand 状态仓库
│   ├── types/
│   │   └── index.ts                 共享类型与图层颜色定义
│   └── utils/
│       ├── db.ts                    IndexedDB 会话持久化
│       └── resolution.ts            当前未接入主流程的分辨率辅助逻辑
├── .env.example
├── package.json
└── README.md
```

---

## 本地开发

### 前置要求
- Node.js 18+
- npm 9+
- 一个可访问的后端服务，默认地址为 `http://localhost:8000`

### 安装与启动

```bash
cd frontend
copy .env.example .env
npm install
npm run dev
```

其他常用命令：

```bash
npm run build
npm run preview
```

默认开发地址：
- `http://localhost:5173`

---

## 环境变量

当前前端代码真正使用的环境变量只有一个：

| 变量 | 默认值 | 作用 |
|---|---|---|
| `VITE_AICSS_BACKEND` | `http://localhost:8000` | 后端基础地址 |

示例 `.env`：

```env
VITE_AICSS_BACKEND=http://localhost:8000
```

注意：`.env.example` 中虽然保留了注释形式的 DashScope key 示例，但当前运行中的前端并不会从 Vite 环境变量读取该 key，而是通过顶部工具栏输入并随请求体发送。

---

## 运行时工作流

### 1. 图像导入

`App.tsx` 会读取用户选择的图像文件，并先渲染到固定的 `1920×1080` 目标画布后再写入 Zustand。

这意味着：
- 后续分析请求统一基于归一化后的图像
- 对于不同比例的原图，可能引入黑边填充
- 虽然状态中保留了 crop 相关字段，但当前 UI 尚未提供完整手动裁剪流程

### 2. Analyze 流程

顶部工具栏会调用 `aicssService.ts` 中的 `analyzeImage(...)`。

当前请求结构如下：

```json
{
  "imageUrl": "data:image/png;base64,...",
  "shotId": "shot_001",
  "apiKey": "your_dashscope_key"
}
```

关键说明：
- API key 由用户在顶部工具栏手动输入
- 当前后端实现依赖该 key 执行 `analyze`
- 响应中可能附带 `vlmDetectedClasses` 与 `vlmDetectedScene`

### 3. 2D 掩码叠加层

`ImageCanvas.tsx` 会根据对象数据渲染：
- 当 `obj.polygon.length >= 3` 时使用 polygon
- 否则回退为矩形框

用户可以点击对象，并把它分配到 15 个颜色图层之一。

### 4. Billboard 生成

`SplitControls.tsx` 会遍历所有已分配对象，并逐个调用 `POST /api/aicss/billboard`。

生成结果保存在：
- `useAppStore.ts` 中的 `billboardAssets`

### 5. 3D 预览

`Viewer3D.tsx` 会把生成好的 Billboard 贴图转成 Three.js 纹理平面。

位置计算主要基于：
- X/Y 来自对象 bounding box 中心
- Z 来自对象深度值

### 6. Inpaint 流程

前端包含局部重绘预览弹窗，并通过 `aicssService.ts` 调用后端 `POST /api/aicss/inpaint`。

这个流程会使用：
- 裁剪后的对象图像
- 反向遮罩
- 文本提示词
- 同一份由用户输入的 DashScope API key

---

## API 客户端

前端 API 层位于 `src/services/aicssService.ts`。

当前已实现的方法：

| 函数 | 对应端点 |
|---|---|
| `analyzeImage` | `POST /api/aicss/analyze` |
| `generateBillboard` | `POST /api/aicss/billboard` |
| `generateMultiface` | `POST /api/aicss/multiface` |
| `inpaintImage` | `POST /api/aicss/inpaint` |
| `checkHealth` | `GET /health` |

Axios 客户端使用：
- 来自 `VITE_AICSS_BACKEND` 的 base URL
- `120000` ms 超时

---

## 状态管理

全局状态位于 `src/store/useAppStore.ts`。

主要状态分组包括：
- 图像来源与尺寸
- 分析结果与加载/错误状态
- 对象到图层的分配关系
- 当前选中对象与当前选中图层
- Billboard 资产 URL
- Inpaint 预览状态
- API key 状态
- 撤销/重做历史
- crop 与 billboard offset 预留状态

实现层面的关键说明：
- `dashscopeApiKey` 保存在 Zustand store 中
- crop 相关字段仍在，但尚未形成完整用户工作流
- `billboardOffsets` 与 `setBillboardOffset` 虽然存在，但当前代码还没有完整暴露对应的编辑交互

---

## 会话持久化

IndexedDB 持久化逻辑位于 `src/utils/db.ts`。

代码中已具备的能力：
- 保存会话
- 更新会话
- 加载会话
- 列出会话
- 删除会话

当前 UI 的实际行为：
- 应用加载时，会尝试恢复最近一次保存的会话
- 当前界面没有提供完整的会话列表或显式会话管理面板
- 当前恢复逻辑主要围绕最近一次会话，而不是完整的工作区恢复体验

---

## 组件总览

### `App.tsx`
- 顶部工具栏
- 图像导入
- Analyze 触发
- 左右分屏布局
- 最近会话恢复

### `ImageCanvas.tsx`
- 渲染 2D 掩码叠加层
- 支持对象选择
- 支持 polygon 与矩形显示

### `LayerSelector.tsx`
- 15 色图层面板
- 用于分配与清理图层

### `SplitControls.tsx`
- Split Image 操作
- 进度与错误展示
- inpaint 相关操作

### `InpaintPreviewDialog.tsx`
- 在替换前预览 inpaint 结果

### `Viewer3D.tsx`
- 在 3D 中渲染 billboard 平面
- 支持 director / camera 两种查看模式

---

## 当前限制与风险

- crop 工作流目前更像“状态预留”，尚未完整成型
- billboard offset 状态存在，但没有完整可视化编辑 UI
- 会话持久化虽然存在，但没有完整会话管理界面
- 顶部工具栏输入 key 的方式在开发中可用，但不适合作为生产级密钥管理方案
- 旧版前端文档曾遗漏 `InpaintPreviewDialog.tsx` 与 IndexedDB 行为说明
- `src/utils/resolution.ts` 当前仍存在，但看起来未接入主流程

---

## 前后端联调检查清单

调试前端问题前，建议先确认：

1. 后端是否运行在预期地址
2. `VITE_AICSS_BACKEND` 是否与后端 origin 一致
3. 是否提供了有效的 DashScope API key
4. 后端 `/health` 是否正常返回
5. 浏览器 Console 与 Network 面板中的请求体是否符合预期

---

## 本文档暂未覆盖的内容

本文主要聚焦代码结构理解与本地开发，不包含：

- 生产部署方式
- 自动化测试体系
- UI 设计系统规范
- 性能分析工作流

---

## 相关文档

- 仓库总览：`../README.md`
- 后端服务说明：`../backend/README.md`
- 前端状态类型：`src/types/index.ts`
- 前端状态仓库：`src/store/useAppStore.ts`
- 前端 API 客户端：`src/services/aicssService.ts`
