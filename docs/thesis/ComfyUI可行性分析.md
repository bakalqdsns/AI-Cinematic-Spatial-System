# ComfyUI + Dify 双工作流引擎在 AICSS 中的综合应用方案

> **核心结论：Dify（编排层）+ ComfyUI（推理层）+ FastAPI（API网关） 三层架构。项目代码量总压缩率可达 85%-90%，从 5600 行 Python 降至 600-1000 行（含 ComfyUI 工作流 + Dify DSL + 极简 Python 网关）。运营层面获得可视化的全流程编排、版本控制友好的工作流文件、统一监控与日志。**
>
> 适用版本：AICinematicSpatialSystem v2
> 分析日期：2026-07-31

---

## 1. 三层架构总览

### 1.1 各层职责划分

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Dify + ComfyUI + FastAPI 三层                      │
└─────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│  Layer 3: Dify（编排层 / Orchestration）                              │
│  ═══════════════════════════════════════                             │
│  职责: 全业务流程编排、文本处理、循环控制、条件分支                     │
│  优势: 可视化拖拽、LLM专家、知识库、Agent工具调用                       │
│  部署: 自托管 Docker 或 SaaS（dify.ai）                                │
│                                                                       │
│  工作流 DSL (.dify.yml / .dify.json)：                                │
│  ├── 剧本解析工作流 (script_parse_pipeline)                           │
│  ├── 分镜生成工作流 (shot_generation_pipeline)                         │
│  ├── 角色资产生成工作流 (character_asset_pipeline)                     │
│  ├── 场景资产生成工作流 (scene_asset_pipeline)                         │
│  ├── 视频生成工作流 (video_generate_pipeline)                         │
│  └── 端到端制片工作流 (master_production_workflow)                    │
└─────────────┬────────────────────────────────────────────────────────┘
              │ Dify HTTP API (workflows/run)
              ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Layer 2: ComfyUI（推理层 / Inference）                                │
│  ═══════════════════════════════════════                               │
│  职责: 图像/视频AI模型推理、显存管理、节点执行                         │
│  优势: 1000+ 现成模型节点、GPU 调度、可视化调试                        │
│  部署: 本地 Docker 容器（独占显存）                                    │
│                                                                       │
│  工作流 JSON (.json)：                                                │
│  ├── character_three_view.json                                        │
│  ├── scene_keyframes.json                                             │
│  ├── txt2img_basic.json / img2img.json                                │
│  ├── lama_inpaint.json                                                │
│  ├── depth_anything_v2.json                                           │
│  ├── grounding_dino.json                                              │
│  ├── sam2_segment.json                                                │
│  └── wan2.1_i2v.json                                                  │
└─────────────┬────────────────────────────────────────────────────────┘
              │ ComfyUI HTTP API (/prompt + /history)
              ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Layer 1: FastAPI（API网关 / Gateway）                                │
│  ══════════════════════════════════                                   │
│  职责: HTTP API、身份认证、结果持久化、项目管理、3D 导出               │
│  代码: 600-1000 行（极简，主要是路由）                                 │
└──────────────────────────────────────────────────────────────────────┘
```

### 1.2 端到端数据流

```
用户上传剧本 → Frontend
        │
        ▼
┌─────────────────────────────────────────────────────────────────────┐
│ FastAPI: POST /api/aicss/v2/scripts/parse                          │
│   └── 转给 Dify workflow execution                                  │
└─────────────────────────────────────────────────────────────────────┘
        │
        ▼
Dify Script Parse Workflow:
        │
        ┌─Step 1─→ LLM Node (Qwen2.5-7B) ───→ 标准化文本
        │
        ├─Step 2─→ LLM Node (JSON 模式) ────→ 字符/场景 JSON
        │
        ├─Step 3─→ Code Node ───────────────→ 验证+过滤伪角色
        │
        └─Step 4─→ HTTP Request Node ──────→ FastAPI: POST /projects/{id}/script_data
        │
        ▼
Dify Master Workflow:
        │
        ├─Step 1─→ LLM Node ────────────────→ 视觉 prompt
        │
        ├─Step 2─→ HTTP Request to ComfyUI ──→ 角色三视图
        │         POST /prompt {workflow:"character_three_view", params:{...}}
        │         └──── Wait 30s ────→
        │
        ├─Step 3─→ Iteration Node (foreach shot)
        │         └─→ HTTP Request to ComfyUI (scene_keyframes)
        │
        └─Step 4─→ Answer Node ─────────────→ 返回最终 manifest URL
```

---

## 2. 为什么需要两层（而不是单独 ComfyUI）

### 2.1 单独 ComfyUI 的局限

| 项目需求 | ComfyUI 是否擅长 | 说明 |
|---------|----------------|------|
| 图像/视频生成 | ✅ 极致擅长 | 1000+ 节点 |
| 语义分割、检测、修复 | ✅ 擅长 | 节点丰富 |
| **结构化 JSON 输出** | ❌ 不擅长 | `output` 节点只能存图 |
| **条件分支** | ⚠️ 弱 | 只有 `Conditioning` 路径控制 |
| **数组循环（foreach 段落）** | ❌ 没有 | 没有 iteration 节点 |
| **文本预处理 + LLM** | ❌ 弱 | prompt 模板需要手写 |
| **HTTP 调用 LLM（GPT/Claude）** | ❌ 弱 | 没有原生 LLM 节点 |
| **错误重试 + 降级** | ⚠️ 部分 | 节点失败需要外部编排 |
| **多轮对话 Agent** | ❌ 没有 | 不适合 |

### 2.2 单独 Dify 的局限

| 项目需求 | Dify 是否擅长 | 说明 |
|---------|-------------|------|
| 业务流程编排 | ✅ 极致擅长 | LLM + 工具调用 |
| **图像生成节点** | ⚠️ 弱 | 只有 OpenAI DALL-E 等 API |
| **本地模型推理** | ❌ 不擅长 | 需要外部插件 |
| **视频生成** | ❌ 没有 | 需要调用外部服务 |
| **复杂的图像管线** | ❌ 没有 | 必须 HTTP 调用外部 |

### 2.3 互补关系

```
         Dify = 流程编排大脑（决策、循环、文本）
             │
             │  "需要角色三视图"
             ▼
         ComfyUI = 推理四肢（图像、视频 AI）
             │
             │  POST /prompt
             ▼
         FastAPI = API + 持久化（项目存储、3D导出）

类似 "LangChain + Stable Diffusion WebUI" 的成熟分层模式
```

---

## 3. Dify 工作流清单（编排层）

| 工作流名 | 文件 (.dify.yml) | 内部节点 | 替代的 Python 模块 | 行数压缩 |
|---------|----------------|---------|------------------|---------|
| 剧本解析 | `script_parse.yml` | LLM×4 + Code + HTTP | `script_parser.py` (1971行) | 1971→0 |
| 分镜生成 | `shot_generation.yml` | LLM×2 + Code + Iteration | `shot_generator.py` (837行) | 837→0 |
| 角色资产生成 | `character_asset.yml` | LLM + HTTP→ComfyUI + Polling | `character_generator.py` (476行) | 476→0 |
| 场景资产生成 | `scene_asset.yml` | LLM + HTTP→ComfyUI + Polling | `scene_generator.py` (422行) | 422→0 |
| 视频生成 | `video_generation.yml` | HTTP→ComfyUI wan_i2v.json + 下载 | `motion_extractor.py` 部分 | 200→0 |
| 主控生产 | `master_production.yml` | 上述全部的 orchestration | `endpoints_*.py` 部分 | 大量 |
| 3D 导出 | `mesh_export.yml` | Code (Blender CLI 调用) + HTTP | `mesh_exporter.py` 部分 | 100→0 |

### 3.1 工作流示例：剧本解析 (script_parse.yml)

```yaml
# 可在 Dify 界面上拖拽节点生成，或用 LLM 写出
version: 0.6.0
name: script_parse
description: 原始剧本 → 结构化 ScriptData
nodes:
  - id: start
    type: start
    data:
      title: Start
      variables:
        - { name: raw_text, type: paragraph, required: true }
        - { name: language, type: select, options: [chinese, english, japanese] }

  - id: llm_normalize
    type: llm
    data:
      title: Step 1: 标准化
      model: qwen2.5-7b
      prompt_template:
        system: |
          你是一个专业的剧本格式化助手。请将用户输入的原始剧本文本重写为标准格式。
          {{#start.language#}} = {{#start.language#}}
        user: "请将以下剧本文本重写为标准格式：\n\n{{#start.raw_text#}}"
      output:
        - { variable: normalized_text, type: string }

  - id: llm_parse_header
    type: llm
    data:
      title: Step 2a: 提取元信息
      prompt_template:
        system: "你是一个剧本元数据提取助手。返回严格 JSON：{\"title\":\"...\",\"genre\":\"...\",\"logline\":\"...\"}"
        user: "剧本：\n{{#llm_normalize.normalized_text#}}\n提取元信息。"
      output:
        - { variable: header_data, type: object }

  - id: llm_parse_scenes
    type: llm
    data:
      title: Step 2b: 提取场景
      prompt_template:
        system: |
          你是场景识别助手。从剧本中提取场景数组。
          返回 JSON：{"scenes":[{"id":"scene-1","location":"...","time":"Day|Night|...","atmosphere":"...","estimated_shots":3}]}
        user: "剧本：\n{{#llm_normalize.normalized_text#}}"
      output:
        - { variable: scenes_data, type: array[object] }

  - id: code_filter_pseudo
    type: code
    data:
      title: Step 3: 伪角色过滤
      variables:
        - { name: scenes, value_selector: [llm_parse_scenes, scenes_data] }
        - { name: raw_chars, value_selector: [???, characters] }
      code_language: python3
      code: |
        BLACKLIST = {"特写", "中景", "全景", "旁白", "她", "他", ...}
        filtered = [c for c in raw_chars if c.get("name") not in BLACKLIST]
        return {"characters": filtered}
      outputs:
        characters: { type: array[object], children: null }

  - id: http_persist
    type: http-request
    data:
      title: Step 4: 持久化到 FastAPI
      method: POST
      url: "{{#env.AICSS_API_URL#}}/api/aicss/v2/scripts/save"
      headers:
        Authorization: "Bearer {{#env.AICSS_TOKEN#}}"
      body:
        type: json
        data:
          project_id: "{{#env.PROJECT_ID#}}"
          script_data: "{{#code_filter_pseudo.result#}}"

  - id: end
    type: end
    data:
      title: End
      outputs:
        - { variable: script_data, value_selector: [code_filter_pseudo, result] }
        - { variable: project_id, value_selector: [env, PROJECT_ID] }

edges:
  - { source: start, target: llm_normalize }
  - { source: llm_normalize, target: llm_parse_header }
  - { source: llm_normalize, target: llm_parse_scenes }
  - { source: llm_parse_header, target: code_filter_pseudo }
  - { source: code_filter_pseudo, target: http_persist }
  - { source: http_persist, target: end }
```

### 3.2 工作流示例：角色三视图（调用 ComfyUI）

```yaml
name: character_asset
nodes:
  - id: start
    type: start
    data:
      variables:
        - { name: character_id, type: text, required: true }
        - { name: character_name, type: text }
        - { name: gender, type: text }
        - { name: personality, type: text }
        - { name: reference_image_b64, type: paragraph, required: false }

  - id: llm_visual_prompt
    type: llm
    data:
      model: qwen2.5-7b
      prompt_template:
        system: |
          为角色生成 50 词的英文视觉描述提示词。
          格式：逗号分隔的描述词列表。
        user: |
          角色名: {{#start.character_name#}}
          性别: {{#start.gender#}}
          性格: {{#start.personality#}}
      output: [{ variable: visual_prompt, type: string }]

  - id: code_build_payload
    type: code
    data:
      variables:
        - { name: prompt, value_selector: [llm_visual_prompt, visual_prompt] }
        - { name: char_id, value_selector: [start, character_id] }
      code_language: python3
      code: |
        import json
        workflow = json.load(open("/workflows/character_three_view.json"))
        return {
          "workflow_name": "character_three_view",
          "params": {"visual_prompt": prompt, "character_id": char_id},
          "client_id": "aicss-" + str(__import__("uuid").uuid4())[:8],
        }
      outputs:
        comfyui_payload: { type: object, children: null }

  - id: http_submit_comfyui
    type: http-request
    data:
      title: 提交 ComfyUI 工作流
      method: POST
      url: "http://127.0.0.1:8188/prompt"
      body:
        type: json
        data:
          prompt: "{{#code_build_payload.comfyui_payload.workflow#}}"
          client_id: "{{#code_build_payload.comfyui_payload.client_id#}}"

  - id: http_poll_comfyui
    type: http-request
    data:
      title: 轮询 ComfyUI 状态
      method: GET
      url: "http://127.0.0.1:8188/history/{{#http_submit_comfyui.response.prompt_id#}}"
      retry:
        enabled: true
        max_retries: 60
        retry_interval_ms: 5000

  - id: http_download_images
    type: http-request
    data:
      title: 下载三视图
      method: GET
      url: "http://127.0.0.1:8188/view?filename={{#http_poll_comfyui.response.outputs.7.images.0.filename#}}&type=output"
      body:
        type: binary

  - id: http_persist
    type: http-request
    data:
      method: POST
      url: "{{#env.AICSS_API_URL#}}/api/aicss/v2/characters/save"
      body:
        type: multipart
        data:
          character_id: "{{#start.character_id#}}"
          front_b64: "{{#http_download_images.response_body#}}"
          # 类似处理 side / back

  - id: end
    type: end
```

### 3.3 工作流示例：分镜生成（含 Iteration）

```yaml
name: shot_generation
nodes:
  - id: start
    type: start
    data:
      variables:
        - { name: project_id }
        - { name: shots_per_scene, default: 6 }

  - id: llm_generate_shots
    type: llm
    data:
      model: qwen2.5-7b
      prompt_template:
        system: "你是专业分镜师。请生成完整分镜表的 JSON..."
        user: |
          剧本标题：{{#env.script_title#}}
          场景：{{#env.scenes#}}
          角色：{{#env.characters#}}
          段落：{{#env.paragraphs#}}
      output:
        - { variable: shots_json, type: array[object] }

  - id: code_validate_shots
    type: code
    data:
      code_language: python3
      code: |
        # 验证景别/运镜枚举
        SHOT_SIZE_ENUM = {"Extreme Close-up", "Close-up", ...}
        CAMERA_ENUM = {"Dolly In", "Dolly Out", ...}

        validated = []
        for idx, shot in enumerate(shots):
            shot["shot_number"] = idx + 1
            shot["shot_size"] = shot.get("shot_size", "Medium Shot")
            if shot["shot_size"] not in SHOT_SIZE_ENUM:
                shot["shot_size"] = "Medium Shot"
            # ... 同样处理 camera_movement
            validated.append(shot)

        return {"shots": validated}
      outputs: { shots: { type: array[object] } }

  - id: iteration_per_shot
    type: iteration
    data:
      iterator_selector: [code_validate_shots, shots]
      iterator_input_type: array[object]
      output_selector: [answer_node, result]
      start_node_id: iter_start

  - id: http_generate_keyframes
    type: http-request
    data:
      # 每个 shot 都触发一次 ComfyUI 关键帧生成
      method: POST
      url: "http://127.0.0.1:8188/prompt"
      body:
        type: json
        data: '{ "prompt": {...scene_keyframes template...} }'

  - id: end
    type: end
```

---

## 4. FastAPI 端 Python 端角色转变

### 4.1 从"执行者"到"调度者"

```python
# main.py （改造后约 80 行）

from fastapi import FastAPI
from pydantic import BaseModel
import httpx

app = FastAPI()

DIFY_BASE = "http://127.0.0.1:8001/v1"  # Dify API
COMFYUI_BASE = "http://127.0.0.1:8188"
AICSS_TOKEN = "..."

class ScriptParseRequest(BaseModel):
    raw_text: str
    language: str = "chinese"
    project_id: str | None = None

class TriggerRequest(BaseModel):
    project_id: str
    payload: dict

@app.post("/api/aicss/v2/scripts/parse")
async def parse_script(req: ScriptParseRequest):
    """调 Dify 工作流"""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{DIFY_BASE}/workflows/run",
            headers={"Authorization": f"Bearer {DIFY_TOKEN}"},
            json={
                "inputs": {"raw_text": req.raw_text, "language": req.language},
                "response_mode": "blocking",
                "user": req.project_id or "anonymous",
            },
            timeout=300,
        )
        return resp.json()

@app.post("/api/aicss/v2/characters/three-view")
async def generate_three_view(req: TriggerRequest):
    return await _trigger_dify_workflow("character_asset", req.payload)

@app.post("/api/aicss/v2/scenes/keyframes")
async def generate_scene_keyframes(req: TriggerRequest):
    return await _trigger_dify_workflow("scene_asset", req.payload)

@app.post("/api/aicss/v2/scripts/shots/generate")
async def generate_shots(req: TriggerRequest):
    return await _trigger_dify_workflow("shot_generation", req.payload)

@app.post("/api/aicss/v2/videos/generate")
async def generate_video(req: TriggerRequest):
    return await _trigger_dify_workflow("video_generation", req.payload)

async def _trigger_dify_workflow(name: str, inputs: dict):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{DIFY_BASE}/workflows/run",
            headers={"Authorization": f"Bearer {DIFY_TOKEN}"},
            json={"inputs": inputs, "response_mode": "streaming", "user": "aicss"},
            timeout=600,
        )
        return resp.json()

# 3D 导出和持久化还在 Python 端（不涉及 AI）
@app.post("/api/aicss/v2/meshes/export")
async def export_mesh(project_id: str, layer_key: str):
    # 调用 Blender headless CLI
    return await _call_blender_export(project_id, layer_key)
```

### 4.2 极简 Python 端职责清单

```
保留：
  - FastAPI 路由                    (~200 行)
  - 3D mesh 导出 (Blender 调用)      (~300 行)
  - 项目存储 (project_store.py)      (~400 行)
  - WebSocket 进度推送               (~100 行)
  - 健康检查 / 配置                  (~50 行)

总计 FastAPI 端: ~1000 行（从 5600 行压缩）
```

---

## 5. ComfyUI 工作流清单（推理层）

| 工作流名 | 输入参数 | 节点组合 | 替代 Python 模块 |
|---------|--------|---------|----------------|
| `character_three_view.json` | visual_prompt, seed | CheckpointLoader + CLIPTextEncode×3 + KSampler×3 + VAEDecode×3 + Img2Img | character_generator.py (350行) |
| `scene_keyframes.json` | visual_prompt, seed | 类似于上面，但 wide→closeup→mood | scene_generator.py (300行) |
| `txt2img_basic.json` | prompt, seed, size | 标准 CheckpointLoader + KSampler | image_generator.py 部分 |
| `img2img.json` | prompt, image, strength | LoadImage + KSampler (img2img) | image_generator.py 部分 |
| `lama_inpaint.json` | image, mask | LoadImage + LaMaLoader + LaMaInpaint + SaveImage | lama_loader.py + inpaint_utils.py |
| `depth_anything_v2.json` | image | LoadImage + DepthAnythingLoader + Apply | depth_loader.py |
| `grounding_dino.json` | image, text | LoadImage + GroundingDinoLoader + Detection | grounding_dino_loader.py |
| `sam2_segment.json` | image, boxes | LoadImage + SAM2Loader + Sam2Seg | sam2_loader.py |
| `wan2.1_i2v.json` | prompt, start_image, end_image | WanVideoLoader + WanImageToVideo + VHS_VideoCombine | motion_extractor.py 部分 |
| `paper_diorama.json` | depth_map | 复合：depth→thickness→normal→outline | paper_diorama.py |

---

## 6. 端到端实例：用户上传剧本

### 6.1 时序图

```
用户 → Frontend → FastAPI → Dify → ComfyUI → 返回路径
 │        │          │        │        │         │
 │ 1 POST /scripts/parse │        │        │         │
 ├───────→│          │        │        │         │
 │        │ 2 转发到 Dify       │        │         │
 │        ├─────────→│        │        │         │
 │        │          │ 3 LLM节点×3        │         │
 │        │          ├─────→  │        │         │
 │        │          │        │ 4 返回 ScriptData │         │
 │        │          │←─────┤ │        │         │
 │        │ 5 HTTP持久化         │        │         │
 │        │   (可选，存到 project_store) │        │         │
 │        ├──→ (project_store服务)       │        │         │
 │        │          │        │        │         │
 │ 6 用户选择"生成角色三视图"    │        │        │         │
 ├───────→│          │        │        │         │
 │        │ 7 转发到 Dify character_asset  │        │         │
 │        ├─────────→│        │        │         │
 │        │          │ 8 LLM: 生成 visual_prompt  │         │
 │        │          ├─────→  │        │         │
 │        │          │ 9 HTTP→ComfyUI 提交工作流       │         │
 │        │          ├────────────────→│         │
 │        │          │ 10 轮询直到 done  │         │
 │        │          ├────────────────→│         │
 │        │          │ 11 下载三视图    │         │
 │        │          ├────────────────→│         │
 │        │          │ 12 上传到 project_store      │         │
 │        ├──→ (project_store服务)       │        │         │
 │←──────┤ 返回 file URLs  │        │        │         │
 │ 13 前端显示图  │        │        │         │
```

### 6.2 错误处理层级

```
第 1 层: ComfyUI 工作流本身失败
   └── Dify HTTP Request Node 配置 error_handle_mode: continueOnError
       返回部分结果，主工作流继续

第 2 层: Dify 节点失败（LLM 超时）
   └── 配置 retry_on_failure + 默认 fallback 值
       或 if-else 分支：失败时走简化流程

第 3 层: FastAPI 收到异常
   └── 返回 503，前端提示"工作流运行中，请等待"
   └── WebSocket 推送状态：pending → running → done/error
```

---

## 7. 代码量与工作量对比

### 7.1 三层方案 vs 现状代码量

| 模块 | 现状 (Python) | 改造后 Python | 改造后 Dify | 改造后 ComfyUI |
|------|--------------|-------------|------------|---------------|
| 剧本解析 | 1971行 | 0 | ~150 行 DSL | 0 |
| 分镜生成 | 837行 | 0 | ~120 行 DSL | 0 |
| 角色生成 | 476行 | 0（仅API路由） | ~200 行 DSL | ~80 节点 JSON |
| 场景生成 | 422行 | 0（仅API路由） | ~200 行 DSL | ~60 节点 JSON |
| 运动提取（视频部分） | 331行 | 0（仅API路由） | ~150 行 DSL | ~100 节点 JSON |
| 视频Adapter | 422行 | 0 | 0 | ~30 节点 JSON（wan i2v） |
| 图像生成 | 881行 | 0 | 0 | ~30 节点 JSON（txt2img） |
| LaMa修复 | 226行 | 0 | 0 | ~50 节点 JSON |
| 深度/分割/检测 | ~600行 | 0 | 0 | ~150 节点 JSON（3个工作流） |
| GPU并发 | 39行 | 0 | 0 | 0 |
| FastAPI 路由 | ~1500行 | ~800行 | 0 | 0 |
| 项目存储 | 1064行 | 1064行（保留） | 0 | 0 |
| Mesh 3D导出 | ~500行 | 500行（保留 Blender 调用） | 可选 Dify 编排 | 0 |
| **总计** | **~10000行** | **~2400行** | **~820 行 DSL** | **~500 节点 JSON** |

**代码压缩率：76%（10000 → 2400 行 Python）+ DSL/JSON 工作流（功能等价但可视化）**

### 7.2 与单独 ComfyUI 对比

| 项目 | 单独 ComfyUI | ComfyUI + Dify |
|------|------------|---------------|
| 文本 LLM 编排 | ❌ 需要 Python | ✅ Dify 工作流 |
| 条件分支 | ⚠️ 部分支持 | ✅ if-else 节点 |
| 数组循环 | ❌ 手动实现 | ✅ iteration 节点 |
| 重试 + fallback | ⚠️ 节点级 | ✅ 节点级 + 工作流级 |
| Agent/工具调用 | ❌ 没有 | ✅ Agent 节点 |
| 知识库（RAG） | ❌ 没有 | ✅ 原生支持 |
| 多 LLM 协同 | ⚠️ 难 | ✅ 拖拽 |

### 7.3 实施工时估算

| 阶段 | 内容 | 工时 |
|------|-----|-----|
| **Phase 1** | Dify 部署 + 模型部署 + ComfyUI 部署 | 30-40h |
| **Phase 2** | Dify 工作流编排（6个核心工作流） | 100-140h |
| **Phase 3** | ComfyUI 工作流制作（10个工作流） | 80-100h |
| **Phase 4** | Python 端瘦身（删除 → 极简 API 路由） | 40-60h |
| **Phase 5** | 联调 + 错误处理 + 监控 | 50-70h |
| **总计** | — | **300-410h** |

---

## 8. 部署架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            生产部署架构                                  │
└─────────────────────────────────────────────────────────────────────────┘

[Frontend] (React + Vite)
    │ HTTPS
    ▼
[FastAPI Gateway]  ← nginx / Caddy
    │
    ├── Dify Workflows Service (docker)
    │     ├── Dify API: http://dify:8001
    │     ├── PostgreSQL: 剧本/角色/项目元数据
    │     └── Redis: 缓存 + 任务队列
    │
    ├── ComfyUI Inference Cluster (docker)
    │     ├── ComfyUI #1 (主) - GPU 0
    │     │     工作流 JSON / 模型权重
    │     └── ComfyUI #2 (副) - GPU 1 (可选)
    │           用于视频生成（高 VRAM 占用）
    │
    ├── Model Storage (NFS/S3)
    │     ├── /models/checkpoints/    # Z-Image, SDXL
    │     ├── /models/loras/
    │     └── /models/vae/
    │
    ├── Project Storage (file system)
    │     └── /workspace/projects/<id>/
    │           manifest.json + artifacts/
    │
    └── 3D Export Worker
          └── Blender headless CLI
              → 输出 .glb / .fbx 到项目目录
```

---

## 9. 监控与运维

### 9.1 Dify 自带监控

- 工作流运行历史（成功/失败/耗时）
- Token 消耗统计
- LLM 调用延迟
- Agent 工具调用次数

### 9.2 ComfyUI 自带监控

- Queue depth / running jobs
- 单工作流耗时
- 显存占用（nvidia-smi）

### 9.3 FastAPI 加监控（推荐）

```python
# 在 Dify + ComfyUI 之上加一个 observability 层
@app.middleware("http")
async def log_request(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    metrics.observe("api_latency_ms", duration * 1000, 
                     endpoint=request.url.path)
    return response
```

---

## 10. 风险与缓解

| 风险 | 说明 | 缓解方案 |
|------|------|---------|
| Dify 与 ComfyUI 双服务依赖 | 单点失败 | FastAPI 端保留原 Python fallback 路径 |
| 工作流版本控制复杂 | DSL/JSON 文件增多 | 用 git 即可，DSL 是纯文本 |
| Dify 私有化部署成本 | 需要 4-8GB 内存 | 使用 Dify Cloud SaaS 代替 |
| ComfyUI 节点失效 | 插件升级后不兼容 | 工作流 JSON 化后，可视化重新拖拽修复 |
| 调试困难（Dify 黑盒） | LLM 输出不可控 | Dify 提供 Tracing + Iterations 视图 |
| 网络延迟（Dify↔ComfyUI） | localhost 内网 5-15ms | 同主机部署，消除延迟 |
| License | Dify 是 SSE（自用免费），ComfyUI 是 GPL | 内部使用无影响，对外发布要注意 GPL 传染 |

---

## 11. 适用性总结

### 11.1 强烈推荐场景

| 场景 | 推荐理由 |
|------|---------|
| **多模型协同工作流** | Dify + ComfyUI 组合无敌 |
| **算法人员参与迭代** | 可视化拖拽，无需懂 Python |
| **生产级 AI 产品化** | 监控、版本、运维都成熟 |
| **需要 LLM 工具调用（Agent）** | Dify 原生支持 |

### 11.2 不推荐场景

| 场景 | 替代方案 |
|------|---------|
| 单体应用，无 LLM 编排需求 | 单独 ComfyUI 即可 |
| 极度依赖 React/Node 实时 UI | 单独 ComfyUI 更轻 |
| 无 GPU 算力 | 用 Dify + 云 API（DALL-E/Stable API），不部署 ComfyUI |
| 团队不熟悉可视化工作流 | 保留 Python 原状 |

---

## 12. 推荐实施路线

### Phase 1：单独 ComfyUI 试点（2-3周）

```
目标：把 character_generator.py + scene_generator.py 改造为 ComfyUI 调用
收益：立即见效，省 800+ 行 Python
风险：低（保留 fallback）
```

### Phase 2：加入 Dify 编排（3-4周）

```
目标：把 script_parser.py + shot_generator.py 改造为 Dify 编排
收益：LLM 流程可视化，参数调优简单
风险：中（Dify 需要部署 + 学习曲线）
```

### Phase 3：双引擎完全整合（2-3周）

```
目标：Dify 编排 → ComfyUI 推理 → FastAPI 持久化 流水线
收益：可视化全流程、版本控制、监控齐全
风险：低（已在前两阶段验证）
```

---

## 13. 结论

> **Dify + ComfyUI 是当前最成熟的"可视化 AI 工作流"组合方案，可以替代 AICSS 后端 75%-85% 的 AI 调用代码。把"工作流即代码"理念推到极致：算法人员用 Dify 编排业务流程，AI 工程师用 ComfyUI 编排模型推理，Python 后端只负责 API 网关 + 持久化。**
>
> **关键优势：**
> - **可视化**：所有业务流程可见可调
> - **版本可控**：工作流是纯文本/JSON，git 管理友好
> - **复用性**：一个工作流可被多个 API 端点调用
> - **可观测**：内置监控、Tracing、运行历史
> - **容错性**：节点级 + 工作流级 + API 级三层错误处理
>
> **推荐度：★★★★★（如果团队愿意学习 Dify 与 ComfyUI，强烈推荐完整实施）**

---

## 附录 A：Dify HTTP API 速查

```python
# 运行工作流（blocking）
POST http://127.0.0.1:8001/v1/workflows/run
{
  "inputs": {...},
  "response_mode": "blocking",
  "user": "user-id"
}
→ { "workflow_run_id": "...", "data": {...outputs...} }

# 流式
POST http://127.0.0.1:8001/v1/workflows/run
{
  "inputs": {...},
  "response_mode": "streaming"
}
→ SSE: data: {...event: workflow_finished, data: {...}}

# 查询运行状态
GET http://127.0.0.1:8001/v1/workflows/run/{workflow_run_id}
```

## 附录 B：Dify + ComfyUI 集成模式对照表

| 集成模式 | 适用场景 | 优势 | 劣势 |
|---------|---------|-----|------|
| Python 单层 | 简单应用 | 直接、可控 | 复杂流程难维护 |
| ComfyUI 单层 | 纯图像生成 | 视觉化 | 不擅长文本 |
| Dify 单层 | 纯 LLM 应用 | 视觉化 | 不擅长图像 |
| **Dify + ComfyUI 双层** | **LLM + 视觉协同（AICSS 适用）** | **完整可视化** | **需要双服务运维** |

---

*文档生成时间: 2026-07-31*

---

## 1. 项目当前工作负荷分析

### 1.1 当前后端模块代码量统计

| 模块 | 文件 | 主要职责 | 代码行数 |
|------|------|---------|---------|
| 剧本解析 | `script_parser.py` | 两阶段 LLM 调用 + JSON鲁棒提取 + 启发式fallback | 1971 |
| 分镜生成 | `shot_generator.py` | LLM 调用 + 提示词构建 + 12种景别/13种运镜枚举 + fallback | 837 |
| 角色资产 | `character_generator.py` | LLM 提示词 + 三视图生成 + img2img + 重试逻辑 | 476 |
| 场景资产 | `scene_generator.py` | LLM 提示词 + 三镜头生成 + img2img + 重试逻辑 | 422 |
| 运动提取 | `motion_extractor.py` | 视频生成 → ffmpeg抽帧 → SAM2分割 → 管道编排 | 331 |
| 视频Adapter | `video_adapter.py` | DashScope + Local Wan + SVD 三套Provider | 422 |
| 图像生成 | `image_generator.py` | Z-Image + SDXL双管线 + lazy singleton + 自动下载 | 881 |
| LaMa修复 | `lama_loader.py` | 自动下载 + GPU/CPU切换 + Mask预处理 | 226 |
| GPU并发 | `gpu_concurrency.py` | Semaphore 控制并发 | 39 |
| **小计** | **9个核心模块** | **全部 Python 代码** | **~5605行** |

### 1.2 重复出现的横切关注点

```
┌─────────────────────────────────────────────────────────────────────────┐
│                当前代码中反复出现的横切关注点                              │
└─────────────────────────────────────────────────────────────────────────┘

1. 模型 Provider 路由        (cloud ↔ local 双模式)
   ├── image_generator.py:   Z-Image / SDXL 切换
   ├── character_generator.py: cloud/local 路由
   ├── scene_generator.py:   cloud/local 路由
   ├── video_adapter.py:     DashScope / LocalWan / SVD 三选一
   └── vlm_utils.py:         Qwen3-VL 多级 fallback

2. 显存管理 + 加载/卸载
   ├── image_generator.py:   500+ 行的 _load_pipeline / _ensure_pipe / unload
   ├── gpu_concurrency.py:   asyncio.Semaphore(max=1)
   └── lama_loader.py:       ensure_downloaded / device切换

3. 重试 + 降级
   ├── shot_generator.py:    _fallback_shots (147行启发式)
   ├── script_parser.py:     _fallback_script_data (162行)
   ├── character_generator.py: _generate_with_retry / _img2img_with_retry
   └── scene_generator.py:   同样的 retry pattern

4. 提示词拼接 + 英文翻译
   ├── character_generator.py: generate_visual_prompt + LLM 调用
   ├── scene_generator.py:     generate_scene_visual_prompt + LLM 调用
   └── shot_generator.py:      _build_shot_prompt + 三段 prompt 构建

5. Base64 ↔ PIL 转换
   ├── character_generator.py: _generate_via_cloud / _fetch_url
   ├── image_generator.py:     pil_to_base64 / _base64_to_pil
   └── motion_extractor.py:    同样的往返逻辑
```

---

## 2. ComfyUI 工作流化思路

### 2.1 ComfyUI 工作流的本质

ComfyUI 的核心是**节点图工作流**：每个节点是一个模型操作（CheckpointLoader、KSampler、CLIPTextEncode、VAEDecode 等），节点之间通过边传递数据。在 ComfyUI 编辑器里连好线、保存为 `.json` 文件后，可以直接通过 HTTP API 调用：

```
POST http://127.0.0.1:8188/prompt
{
  "prompt": { ... 节点图 ... },
  "client_id": "uuid"
}
→ 返回 { "prompt_id": "..." }

GET  http://127.0.0.1:8188/history/{prompt_id}
→ 返回 outputs 中的图像路径（ComfyUI input/output 目录）
```

**关键洞察：ComfyUI 工作流是一次性的可执行文件。把项目里 Python 端拼出来的复杂调用链翻译成工作流后，可以由 ComfyUI 服务器执行，Python 端只负责"提交 + 轮询 + 存档"。**

### 2.2 可工作流化的模块清单

| 模块 | Python端职责 | ComfyUI 工作流 | 简化程度 |
|------|------------|--------------|---------|
| 角色三视图 | LLM提示词 + 三次图像调用 + 重试 | `character_three_view.json`（含 reference 锚定） | ★★★★ |
| 场景关键帧 | LLM提示词 + 三次图像调用 | `scene_keyframes.json` | ★★★★ |
| 单张图像生成 | provider路由 + 显存管理 | `txt2img_basic.json` / `img2img.json` | ★★★★★ |
| 图生视频 (i2v) | provider路由 + 轮询 | `wan2.1_i2v.json` | ★★★★ |
| 视频抽帧 | ffmpeg subprocess | ComfyUI 内置 VHS_VideoCombine 或 LoadVideo | ★★★ |
| 图像修复 | LaMa加载 + Mask预处理 | `lama_inpaint.json` | ★★★★★ |
| SAM2分割 | 模型加载 + 自动mask | `sam2_segment.json` | ★★★★ |
| Depth-Anything | 模型加载 + 后处理 | `depth_anything_v2.json` | ★★★★★ |
| Grounding DINO | 模型加载 + 文本prompt | `grounding_dino.json` | ★★★★ |
| **剧本解析** | LLM + JSON鲁棒提取 | **不适合**（纯文本任务，ComfyUI 不擅长） | ✗ |
| **分镜表生成** | LLM + 枚举约束 | **不适合**（结构化输出） | ✗ |

---

## 3. 详细改造方案

### 3.1 架构对比

#### 现状：Python 端执行大部分 AI 调用

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       当前架构                                            │
└─────────────────────────────────────────────────────────────────────────┘

FastAPI Backend
   ├── services/
   │   ├── script_parser.py ────→ LLM (Qwen2.5-7B / DashScope)
   │   ├── shot_generator.py ───→ LLM
   │   ├── character_generator.py ─→ LLM + Diffusers + Provider路由
   │   ├── scene_generator.py ──→ LLM + Diffusers + Provider路由
   │   ├── motion_extractor.py ─→ VideoProvider + ffmpeg + SAM2
   │   └── video_adapter.py ────→ DashScope / LocalWan / SVD
   └── models/
       ├── sam2_loader.py ──────→ SAM2 (本地推理)
       ├── depth_loader.py ─────→ Depth-Anything-V2 (本地推理)
       ├── grounding_dino_loader.py → Grounding DINO (本地推理)
       ├── lama_loader.py ──────→ LaMa (本地推理)
       └── qwen3vl_loader.py ───→ Qwen3-VL (本地推理)

   每个模型都要：load → warmup → inference → unload → 显存清理
   ≈ 5600 行 Python 代码
```

#### 改造后：ComfyUI 作为统一 AI 推理后端

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       改造后架构                                          │
└─────────────────────────────────────────────────────────────────────────┘

FastAPI Backend (Python)                              ComfyUI Server
   ├── services/                                          ┌─────────────────┐
   │   ├── script_parser.py (保留)                       │                 │
   │   ├── shot_generator.py (保留)                      │  ComfyUI        │
   │   ├── comfyui_client.py ← 新增 (统一HTTP客户端)     │  ┌───────────┐  │
   │   │   ├── submit_workflow()                        │  │ workflows/│  │
   │   │   ├── poll_history()                           │  │  *.json   │  │
   │   │   ├── upload_input()                           │  └─────┬─────┘  │
   │   │   └── download_output()                        │        │        │
   │   └── workflow_registry.py ← 新增 (工作流索引)      │  ┌─────▼─────┐  │
   │       ├── character_three_view.json                │  │   AI      │  │
   │       ├── scene_keyframes.json                     │  │   Nodes   │  │
   │       ├── lama_inpaint.json                        │  │  (统一    │  │
   │       ├── depth_anything_v2.json                   │  │   显存    │  │
   │       ├── grounding_dino.json                      │  │   管理)   │  │
   │       ├── sam2_segment.json                        │  └───────────┘  │
   │       └── wan2.1_i2v.json                          │                 │
   └── models/                                           └─────────────────┘
       └── (大部分删除，仅保留Qwen3-VL如果需要)       

   Python 端 ≈ 1500 行 (从 5600 行压缩)
   ComfyUI 工作流 ≈ 10-15 个 .json 文件
```

### 3.2 代码量对比

| 组件 | 现状 | 改造后 | 节省 |
|------|-----|-------|------|
| 模型加载器 (`*_loader.py`) | ~600 行 | 0（删除） | 100% |
| 图像生成 (`image_generator.py`) | 881 行 | ~150 行（仅保留 base64转换 + 路由） | 83% |
| Provider 路由 (`video_adapter.py`) | 422 行 | ~80 行（路由到不同工作流） | 81% |
| 角色生成 | 476 行 | ~120 行（调用 `character_three_view.json`） | 75% |
| 场景生成 | 422 行 | ~120 行（调用 `scene_keyframes.json`） | 72% |
| 运动提取 | 331 行 | ~200 行（保留 ffmpeg 抽帧） | 40% |
| **总计 Python** | **~5600** | **~1500** | **73%** |

### 3.3 工作流示例：角色三视图

`workflows/character_three_view.json`（简化示意）：

```json
{
  "1": {
    "class_type": "CheckpointLoaderSimple",
    "inputs": { "ckpt_name": "z-image-turbo-fp8.safetensors" }
  },
  "2": {
    "class_type": "CLIPTextEncode",
    "inputs": {
      "text": "{{visual_prompt}}, character sheet, front view, facing camera, white background",
      "clip": ["1", 1]
    }
  },
  "3": {
    "class_type": "EmptyLatentImage",
    "inputs": { "width": 720, "height": 1280, "batch_size": 1 }
  },
  "4": {
    "class_type": "KSampler",
    "inputs": {
      "model": ["1", 0],
      "positive": ["2", 0],
      "negative": ["5", 0],
      "latent_image": ["3", 0],
      "steps": 9,
      "cfg": 0.0,
      "sampler_name": "euler",
      "scheduler": "simple",
      "denoise": 1.0
    }
  },
  "5": {
    "class_type": "CLIPTextEncode",
    "inputs": { "text": "blurry, low quality, distorted", "clip": ["1", 1] }
  },
  "6": {
    "class_type": "VAEDecode",
    "inputs": { "samples": ["4", 0], "vae": ["1", 2] }
  },
  "7": {
    "class_type": "SaveImage",
    "inputs": { "filename_prefix": "char_front", "images": ["6", 0] }
  },
  "8": {
    "class_type": "Img2ImgReference",
    "inputs": { "image": ["7", 0] }
  },
  "9": {
    "class_type": "CLIPTextEncode",
    "inputs": { "text": "{{visual_prompt}}, side profile view, 90 degree angle", "clip": ["1", 1] }
  },
  "10": {
    "class_type": "KSampler (img2img)",
    "inputs": {
      "model": ["1", 0],
      "positive": ["9", 0],
      "image": ["8", 0],
      "strength": 0.7,
      "steps": 9, "cfg": 0.0
    }
  },
  "11": {
    "class_type": "VAEDecode",
    "inputs": { "samples": ["10", 0], "vae": ["1", 2] }
  },
  "12": {
    "class_type": "SaveImage",
    "inputs": { "filename_prefix": "char_side", "images": ["11", 0] }
  }
}
```

### 3.4 Python 端调用方式

```python
# services/comfyui_client.py (~150 行)
import json, time, requests, uuid
from pathlib import Path
from typing import Optional

class ComfyUIClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8188"):
        self.base_url = base_url
        self.workflows_dir = Path(__file__).parent.parent / "workflows"
    
    def submit_workflow(
        self, 
        workflow_name: str, 
        parameters: dict,
        timeout: int = 300,
    ) -> dict:
        """加载工作流，填入参数，提交到 ComfyUI 队列"""
        workflow = json.loads(
            (self.workflows_dir / f"{workflow_name}.json").read_text()
        )
        # 用 Jinja2 替换占位符
        workflow_str = json.dumps(workflow)
        for key, value in parameters.items():
            workflow_str = workflow_str.replace(f"{{{{{key}}}}}", str(value))
        workflow = json.loads(workflow_str)
        
        client_id = str(uuid.uuid4())
        resp = requests.post(
            f"{self.base_url}/prompt",
            json={"prompt": workflow, "client_id": client_id},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()  # {"prompt_id": "..."}
    
    def wait_for_result(
        self,
        prompt_id: str,
        timeout: int = 300,
        poll_interval: float = 2.0,
    ) -> dict:
        """轮询 /history 端点获取结果"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            resp = requests.get(f"{self.base_url}/history/{prompt_id}")
            data = resp.json()
            if prompt_id in data:
                return data[prompt_id]
            time.sleep(poll_interval)
        raise TimeoutError(f"ComfyUI workflow {prompt_id} timed out")
    
    def download_outputs(
        self,
        result: dict,
        output_dir: Path,
    ) -> list[Path]:
        """从 /view 端点下载所有输出图像"""
        output_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for node_id, node_output in result.get("outputs", {}).items():
            for img_info in node_output.get("images", []):
                params = {
                    "filename": img_info["filename"],
                    "subfolder": img_info.get("subfolder", ""),
                    "type": "output",
                }
                resp = requests.get(
                    f"{self.base_url}/view",
                    params=params,
                    timeout=60,
                )
                resp.raise_for_status()
                out_path = output_dir / img_info["filename"]
                out_path.write_bytes(resp.content)
                paths.append(out_path)
        return paths


# services/character_generator.py 改造后
async def generate_character_three_view(character, visual_prompt):
    """从 ~240 行 Python 压缩到 ~30 行"""
    client = get_comfyui_client()
    
    # 提交工作流
    resp = client.submit_workflow(
        "character_three_view",
        parameters={
            "visual_prompt": visual_prompt,
            "seed": random.randint(0, 2**32),
        },
    )
    
    # 轮询结果
    result = client.wait_for_result(resp["prompt_id"], timeout=180)
    
    # 下载三视图
    paths = client.download_outputs(result, output_dir=...)
    
    return {
        "front": base64.b64encode(paths[0].read_bytes()).decode(),
        "side": base64.b64encode(paths[1].read_bytes()).decode(),
        "back": base64.b64encode(paths[2].read_bytes()).decode(),
    }
```

---

## 4. 工作流文件清单

| 工作流文件名 | 输入参数 | 节点组合 | 替代Python模块 |
|------------|---------|---------|--------------|
| `character_three_view.json` | visual_prompt, seed, size | CheckpointLoader + CLIPTextEncode×3 + KSampler×3 + VAEDecode×3 + Img2Img | character_generator.py (350行) |
| `scene_keyframes.json` | visual_prompt, seed | 类似上面，但 wide→closeup→mood 三次 | scene_generator.py (300行) |
| `txt2img_basic.json` | prompt, seed, size | 标准 CheckpointLoader + KSampler | image_generator.py 部分 |
| `img2img.json` | prompt, image, strength | LoadImage + KSampler | image_generator.py 部分 |
| `lama_inpaint.json` | image, mask | LoadImage + LaMaLoader + LaMaInpaint + SaveImage | lama_loader.py + inpaint_utils.py (200行) |
| `depth_anything_v2.json` | image | LoadImage + DepthAnythingLoader + ApplyDepthAnything | depth_loader.py (100行) |
| `grounding_dino.json` | image, text_prompt | LoadImage + GroundingDinoLoader + Detection | grounding_dino_loader.py (100行) |
| `sam2_segment.json` | image, boxes | LoadImage + SAM2Loader + Sam2Segmentation | sam2_loader.py (200行) |
| `wan2.1_i2v.json` | prompt, start_image, end_image | WanVideoLoader + WanImageToVideo + VHS_VideoCombine | motion_extractor.py video部分 |
| `depth_to_paper_diorama.json` | depth_map | 复合节点：depth→thickness→normal→outline | paper_diorama.py (200行) |
| `meshy_export.json` | scene_data | Blender调用节点（如有）或 Python bridge | mesh_exporter.py 部分 |

---

## 5. 落地实施步骤

### Phase 1：基础设施搭建（1-2周）

```
1. 部署 ComfyUI 服务器（本地 / Docker）
   docker run -d --name comfyui -p 8188:8188 \
     --gpus all \
     -v $PWD/models:/workspace/models \
     -v $PWD/output:/workspace/output \
     yanwk/comfyui-boot:latest

2. 在 ComfyUI 界面中导入所有模型
   ├── z-image-turbo-fp8.safetensors
   ├── sdxl-base-1.0
   ├── depth-anything-v2
   ├── grounding-dino-base
   ├── sam2-vit-l
   ├── lama-big
   ├── wan2.1-i2v
   └── ...

3. 安装必需的 ComfyUI 插件
   ├── ComfyUI-Manager（节点管理）
   ├── ComfyUI-Impact-Pack（SAM2/检测）
   ├── ComfyUI-VideoHelperSuite（视频）
   └── ComfyUI-WanVideoWrapper（Wan2.1）

4. 实现 comfyui_client.py（150行）
```

### Phase 2：工作流模板制作（2-3周）

```
1. 在 ComfyUI 界面中逐个测试并保存工作流
   ├── character_three_view.json  ← 测试一致性
   ├── scene_keyframes.json
   ├── lama_inpaint.json
   ├── depth_anything_v2.json
   ├── grounding_dino.json
   ├── sam2_segment.json
   └── wan2.1_i2v.json

2. 将占位符替换为 {{param_name}} 格式
   例如：workflow 中所有 CLIPTextEncode 的 text 字段使用 {{prompt}}

3. 在测试脚本中验证每个工作流
   client.submit_workflow("character_three_view", {"visual_prompt": "..."})
   client.wait_for_result(prompt_id)
   client.download_outputs(result)
```

### Phase 3：Python 端迁移（2-3周）

```
1. 编写 comfyui_client.py（150行）
2. 重写 character_generator.py（500行 → 100行）
3. 重写 scene_generator.py（420行 → 100行）
4. 重写 image_generator.py（880行 → 100行）
5. 重写 motion_extractor.py 的 video 部分（视频生成）
6. 删除 / 简化 *_loader.py（600行 → 0）
7. 删除 gpu_concurrency.py（39行 → 0，ComfyUI 内部管理）
```

### Phase 4：测试与迁移验证（1-2周）

```
1. 回归测试：所有现有 API 行为不变
2. 性能对比：单张生成时长 / 三视图 / 视频生成
3. 错误处理：ComfyUI 服务挂掉时的 fallback
4. 持久化：manifest.json 格式保持兼容
```

---

## 6. 工作量压缩估算

### 6.1 代码量对比

| 项目 | 现状 | 改造后 | 节省 |
|------|-----|-------|------|
| **Python 端代码** | 5600 行 | 1500 行 | **4100 行 (73%)** |
| **新增配置文件** | 0 | 15 个 `.json` 工作流 | 工作流维护成本低 |
| **新增 ComfyUI 部署** | — | Docker 容器 | 一次性 |

### 6.2 开发时间估算

| 阶段 | 内容 | 估算工时 |
|------|------|---------|
| Phase 1 | ComfyUI 部署 + 客户端封装 | 40-60h |
| Phase 2 | 工作流模板制作 | 60-80h |
| Phase 3 | Python 端迁移 | 80-100h |
| Phase 4 | 测试与回归 | 40-60h |
| **总计** | — | **220-300h** |

对比现状：每增加一个新模型（如加 StableDiffusion3 / 加 CogVideoX）需要修改 ~200-400 行 Python（loader + provider路由 + 重试逻辑 + GPU管理）。**改造后只需要在 ComfyUI 编辑器里加节点，导出 JSON，Python 端几乎零改动。**

### 6.3 长期收益

- **新模型集成**：从 3-5 天 → 2-3 小时（拖拽节点）
- **工作流可视化**：算法研究人员可直接在 ComfyUI 界面调参，无需懂代码
- **GPU 调度统一**：ComfyUI 内部自动队列管理，无需自己写 Semaphore
- **可复现性**：工作流可分享、可版本控制、可视化调试

---

## 7. 风险与限制

### 7.1 必须保留 Python 的部分

| 功能 | 原因 |
|------|------|
| 剧本解析 (`script_parser.py`) | 纯文本 LLM 任务，ComfyUI 不擅长结构化 JSON 输出 |
| 分镜表生成 (`shot_generator.py`) | 强枚举约束（景别/运镜），需要 Python 端验证 |
| 项目存储 (`project_store.py`) | 文件系统操作，与 AI 无关 |
| 3D 导出 (`mesh_exporter.py`) | Blender headless 调用，非图像模型 |
| 前端 (`frontend/`) | UI 层 |
| WebSocket / HTTP API | FastAPI 服务层 |

### 7.2 潜在风险

| 风险 | 缓解方案 |
|------|---------|
| **ComfyUI 服务挂掉** | 保留 `image_generator.py` 中的本地 Diffusers fallback 路径 |
| **工作流文件版本兼容** | 在 Python 端做版本校验，失败时降级到旧的 Python 路径 |
| **WebSocket 长连接 vs 轮询** | 使用 `/history/{prompt_id}` 轮询，无需 WebSocket |
| **ComfyUI 显存与 Diffusers 显存冲突** | ComfyUI 默认独占显存，不要同时启动两个服务 |
| **数据隐私** | ComfyUI 默认本地部署，无需外网，但工作流文件可能暴露模型路径 |
| **工作流调试困难** | ComfyUI 界面提供 `Queue Image` 可视化调试工具 |
| **License** | ComfyUI 是 GPL-3，但通过 HTTP API 调用属于"管道使用"，通常不传染整个项目 |

### 7.3 不建议改造的部分

- **剧本解析**：LLM 直接生成 JSON 即可，ComfyUI 没有增益
- **LLM 调用本身**（qwen-plus、qwen3-vl）：继续用 DashScope / llama.cpp
- **3D 导出 / Blender 集成**：ComfyUI 有 trimesh 节点但远不如 Blender headless 灵活

---

## 8. 结论与建议

### 8.1 最终建议

```
推荐度：★★★★☆（强烈推荐改造，但分阶段实施）
适用模块：约 70% 的 Python AI 调用代码
不适合模块：LLM 文本任务、文件系统、3D 导出、API 服务层
```

### 8.2 改造前后工作流对比

| | 现状 | 改造后 |
|---|-----|-------|
| **修改流程图**：要增加一个新模型 | 编辑 5+ 个 Python 文件，写 loader、provider、fallback、retry、显存清理、API端点（200-400行） | 在 ComfyUI 拖拽节点，导出 JSON，Python端新增 1 个调用函数（~10行） |
| **模型调试**：调参 / 替换 checkpoint | 修改 Python 配置，重启服务 | 在 ComfyUI 界面里实时调参，满意后再保存 JSON |
| **显存管理**：多模型并存 | 写 Semaphore、自己实现 lazy_load / unload | ComfyUI 内部统一管理，无需操心 |
| **可视化**：算法人员调 prompt | 看 Python 代码中的 prompt 字符串 | 在 ComfyUI 界面里直接预览，每次修改立竿见影 |
| **复现性**：别人跑出一样的结果 | 看 Python 版本、依赖、配置 | 直接分享 `.json` 工作流文件，拖进去就能跑 |

### 8.3 实施优先级

```
优先级 1（必须迁移，高频使用）：
  ✅ 角色三视图    ✅ 场景关键帧    ✅ 图像修复 (LaMa)

优先级 2（建议迁移，工作量大）：
  ✅ Depth-Anything-V2  ✅ SAM2 分割  ✅ Grounding DINO

优先级 3（可选迁移）：
  ⚠️ Wan2.1 i2v 视频生成（ComfyUI 有节点，但本地28GB+ VRAM要求高）
  ⚠️ 纸雕纹理生成（paper_diorama.py，可用 ComfyUI 节点组合）

优先级 4（不迁移）：
  ❌ 剧本解析    ❌ 分镜生成    ❌ 项目存储    ❌ 3D 导出
```

### 8.4 一句话总结

> **ComfyUI 不能替代 AICSS 的所有 Python 代码——LLM 文本任务、文件系统、Blender 集成这些"非图像"部分必须保留 Python。** 但对于**图像生成、分割、检测、修复、视频生成**这一大类视觉AI任务，ComfyUI 工作流 + HTTP API 是一个非常成熟的"工作流即代码"方案，可以把后端 70% 的 AI 调用代码从 Python 转为 JSON，**预计节省 4000+ 行代码 + 大幅降低新模型集成成本**。

---

## 附录 A：ComfyUI HTTP API 速查

```python
# 提交工作流
POST http://127.0.0.1:8188/prompt
{
  "prompt": { ...workflow... },
  "client_id": "uuid"
}
→ { "prompt_id": "..." }

# 查询队列
GET http://127.0.0.1:8188/queue
→ { "queue_running": [...], "queue_pending": [...] }

# 查询历史
GET http://127.0.0.1:8188/history/{prompt_id}
→ { "{prompt_id}": { "outputs": { "7": { "images": [...] } } } }

# 上传输入图
POST http://127.0.0.1:8188/upload/image
multipart/form-data: image=@local.png
→ { "name": "uploaded.png", "subfolder": "" }

# 下载输出图
GET http://127.0.0.1:8188/view?filename=xxx.png&subfolder=&type=output
→ binary image data
```

## 附录 B：常用 ComfyUI 节点清单

| 节点名 | 用途 | 替代的Python代码 |
|-------|-----|-----------------|
| `CheckpointLoaderSimple` | 加载 SD/Z-Image 检查点 | `pipe.from_pretrained(...)` |
| `CLIPTextEncode` | 文本 → 条件向量 | `pipe.encode_prompt(...)` |
| `KSampler` / `KSamplerAdvanced` | 采样生成 | `pipe(...)` |
| `VAEDecode` / `VAEEncode` | 图像 ↔ latent | 自动 |
| `LoadImage` | 加载输入图 | `Image.open(...)` |
| `SaveImage` | 保存输出图 | `image.save(...)` |
| `ImageScale` | 缩放 | `image.resize(...)` |
| `ImageCompositeMasked` | Mask合成 | `Image.composite(...)` |
| `LaMaInpaint` (插件) | 图像修复 | `lama_model.predict(...)` |
| `GroundingDino` (插件) | 目标检测 | `dino_model.predict(...)` |
| `SAM2Segmentation` (插件) | 分割 | `sam2_model.predict(...)` |
| `WanVideoSampler` (插件) | Wan2.1 i2v | `WanImageToVideoPipeline(...)` |
| `VHS_VideoCombine` | 视频合成 | ffmpeg 调用 |

---

# 附录 C：Blender 插件的完整实现方案

> **核心结论：将 Blender 从"headless subprocess 黑盒"升级为"常驻 HTTP 服务 + bpy 插件"，可以消除冷启动开销、支持状态保持、实现双向实时通信，并与 Dify 工作流无缝对接。**

---

## C.1 现状痛点与升级目标

### 现状（subprocess 模式）

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    现状：每次调用都冷启动 Blender                          │
└─────────────────────────────────────────────────────────────────────────┘

FastAPI / Dify
   │
   │  subprocess.run(["blender", "--background", "--python", "/tmp/export.py"])
   │
   ▼
┌──────────────────────────────────────────────┐
│            Blender 进程（每次新建）             │
│  ┌─────────────────────────────────────────┐ │
│  │ 启动 5-15s  │ 加载 bpy/cycles/材质     │ │
│  │ 清空场景     │ 创建 mesh                 │ │
│  │ 导出 GLB     │ 退出                     │ │
│  └─────────────────────────────────────────┘ │
└──────────────────────────────────────────────┘
   │ 文件落地
   ▼
project_store_mesh

痛点：
- 每次冷启动 5-15s（不可接受的小请求）
- 进程结束 = 场景销毁 = 无状态
- 数据通过 JSON 嵌入 Python 脚本（易踩 f-string 坑）
- 无实时查询能力（必须等导出完成后才能看到结果）
- 多任务排队（同一文件并发导出）相互阻塞
```

### 升级目标（HTTP Server 模式）

```
┌─────────────────────────────────────────────────────────────────────────┐
│                 升级目标：常驻 HTTP 服务 + bpy 插件                       │
└─────────────────────────────────────────────────────────────────────────┘

FastAPI / Dify
   │
   │  POST http://127.0.0.1:8889/aicss/export
   │  { "scene_data": {...}, "output_format": "glb" }
   │
   ▼
┌──────────────────────────────────────────────────────────────┐
│              Blender 进程（常驻）                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  AICinematicSpatialSystem 插件                         │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐    │  │
│  │  │ HTTP Server │ │ Scene Pool │ │ Material DB │    │  │
│  │  │ (aiohttp)   │ │ (持久化)    │ │ (LRU缓存)   │    │  │
│  │  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘    │  │
│  │         └────────────────┴────────────────┘            │  │
│  │                       │                                │  │
│  │                       ▼                                │  │
│  │              bpy ops (直接 API)                        │  │
│  │              场景构建 + GLB/FBX 导出                    │  │
│  └───────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
   │
   │  HTTP Response { "mesh_id": "...", "file_path": "...", "stats": {...} }
   ▼
FastAPI / Dify / project_store_mesh

优势：
- 启动开销 0（常驻进程）
- 场景可保留、复用、迭代修改
- 实时查询（GET /scenes/{id}/info）
- 材质缓存（同一纹理不重复加载）
- 双向通信（WebSocket 进度推送）
- 并发安全（aiohttp + 队列）
```

---

## C.2 Blender 插件完整实现

### C.2.1 目录结构

```
blender_aicss/
├── __init__.py                       # Blender 插件入口
├── operators/
│   ├── __init__.py
│   ├── aicss_export.py              # 导出操作
│   └── aicss_import.py              # 导入操作
├── server/
│   ├── __init__.py
│   ├── http_server.py               # aiohttp HTTP 服务
│   ├── routes.py                    # 路由
│   └── websocket.py                 # 进度推送
├── core/
│   ├── __init__.py
│   ├── scene_builder.py             # 场景构建器
│   ├── material_factory.py          # 材质工厂
│   ├── mesh_cache.py                # mesh 缓存
│   └── job_queue.py                 # 任务队列
├── presets/
│   ├── paper_diorama.blend          # 模板场景
│   └── materials.blend              # 材质库
├── preferences.py                   # 插件配置
└── ui.py                            # Blender 面板 UI
```

### C.2.2 插件入口 `__init__.py`

```python
# blender_aicss/__init__.py
bl_info = {
    "name": "AICinematicSpatialSystem",
    "author": "刘淇",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > AICSS",
    "description": "AICSS 3D 资产生成插件：纸雕风格 mesh 导出 + HTTP 服务",
    "category": "Import-Export",
}

import bpy
from . import preferences, ui, operators, server

_classes = (
    preferences.AICSSPreferences,
    ui.AICSS_PT_Panel,
    operators.aicss_operators.AICSS_OT_StartServer,
    operators.aicss_operators.AICSS_OT_StopServer,
    operators.aicss_operators.AICSS_OT_QuickExport,
    operators.aicss_operators.AICSS_OT_ClearCache,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    preferences.register()
    ui.register()
    operators.register()


def unregister():
    ui.unregister()
    operators.unregister()
    preferences.unregister()
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
```

### C.2.3 插件配置 `preferences.py`

```python
# blender_aicss/preferences.py
import bpy
from bpy.types import AddonPreferences
from bpy.props import (
    StringProperty,
    IntProperty,
    BoolProperty,
    EnumProperty,
)


class AICSSPreferences(AddonPreferences):
    bl_idname = __package__  # "blender_aicss"

    # HTTP 服务端口
    server_host: StringProperty(
        name="HTTP Host",
        default="127.0.0.1",
        description="AICSS HTTP 服务监听地址",
    )
    server_port: IntProperty(
        name="HTTP Port",
        default=8889,
        min=1024, max=65535,
        description="AICSS HTTP 服务监听端口",
    )

    # 行为配置
    auto_start_server: BoolProperty(
        name="启动时自动开启服务",
        default=True,
    )
    enable_websocket: BoolProperty(
        name="启用 WebSocket 进度推送",
        default=True,
    )

    # 输出配置
    default_format: EnumProperty(
        name="默认导出格式",
        items=[
            ("glb", "GLB", "glTF 2.0 Binary（推荐）"),
            ("fbx", "FBX", "Autodesk FBX"),
            ("obj", "OBJ", "Wavefront OBJ"),
        ],
        default="glb",
    )

    cache_size_mb: IntProperty(
        name="材质缓存（MB）",
        default=2048,
        min=128, max=16384,
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="AICSS 服务配置")
        layout.prop(self, "server_host")
        layout.prop(self, "server_port")
        layout.prop(self, "auto_start_server")
        layout.prop(self, "enable_websocket")
        layout.separator()
        layout.label(text="导出配置")
        layout.prop(self, "default_format")
        layout.prop(self, "cache_size_mb")


_server_instance = None


def get_server():
    """获取当前 HTTP 服务单例。"""
    global _server_instance
    if _server_instance is None:
        prefs = bpy.context.preferences.addons[__package__].preferences
        from .server.http_server import AICSSHttpServer
        _server_instance = AICSSHttpServer(
            host=prefs.server_host,
            port=prefs.server_port,
            enable_websocket=prefs.enable_websocket,
        )
    return _server_instance


def register():
    pass


def unregister():
    global _server_instance
    if _server_instance is not None:
        _server_instance.stop()
        _server_instance = None
```

### C.2.4 核心场景构建器 `core/scene_builder.py`

```python
# blender_aicss/core/scene_builder.py
"""
场景构建器 - 直接调用 bpy API 而非生成 Python 脚本。

优势：
- 避免 f-string 大括号问题
- 可以访问当前 bpy 上下文（材质库、用户设置）
- 支持增量更新（不需要重建）
"""
import bpy
import bmesh
from typing import Optional


class SceneBuilder:
    """构建 Paper Diorama 风格 3D 场景。"""

    def __init__(self):
        self.collection = None

    def clear_scene(self, keep_collections: Optional[list[str]] = None):
        """清空场景，可选保留指定 collection。"""
        keep = set(keep_collections or [])
        for obj in list(bpy.data.objects):
            if obj.name not in keep:
                bpy.data.objects.remove(obj, do_unlink=True)
        # 清理孤立 data blocks
        for coll in list(bpy.data.collections):
            if coll.name not in keep and len(coll.objects) == 0:
                bpy.data.collections.remove(coll)
        for block in list(bpy.data.meshes):
            if block.users == 0:
                bpy.data.meshes.remove(block)

    def new_collection(self, name: str) -> bpy.types.Collection:
        """创建或获取 collection。"""
        if name in bpy.data.collections:
            return bpy.data.collections[name]
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
        return coll

    def build_layer(self, layer_data: dict) -> bpy.types.Object:
        """构建单个深度层 mesh。"""
        layer_key = layer_data["layer_key"]
        name = f"Layer_{layer_key}"

        w = layer_data.get("width", 20.0)
        h = layer_data.get("height", 15.0)
        d = layer_data.get("thickness", 0.1)
        z_pos = layer_data.get("position_z", 0.0)
        bevel_w = layer_data.get("bevel_width", 0.005)

        # 1. 创建 mesh
        mesh = bpy.data.meshes.new(name)
        bm = bmesh.new()
        hw, hh, hd = w / 2, h / 2, d / 2
        verts = [
            bm.verts.new((-hw, -hh, -hd)), bm.verts.new((hw, -hh, -hd)),
            bm.verts.new((hw, hh, -hd)), bm.verts.new((-hw, hh, -hd)),
            bm.verts.new((-hw, -hh, hd)), bm.verts.new((hw, -hh, hd)),
            bm.verts.new((hw, hh, hd)), bm.verts.new((-hw, hh, hd)),
        ]
        face_verts = [
            [3, 2, 1, 0], [4, 5, 6, 7],
            [0, 1, 5, 4], [2, 3, 7, 6],
            [0, 4, 7, 3], [1, 2, 6, 5],
        ]
        for fv in face_verts:
            try:
                bm.faces.new([verts[i] for i in fv])
            except ValueError:
                pass
        bm.to_mesh(mesh)
        bm.free()

        # 2. 创建 Object
        obj = bpy.data.objects.new(name, mesh)
        obj.location = (0, 0, z_pos)
        bpy.context.scene.collection.objects.link(obj)

        # 3. 应用材质
        from .material_factory import MaterialFactory
        mat = MaterialFactory.create_paper_material(
            f"Mat_{name}",
            diffuse_path=layer_data.get("diffuse_texture"),
            normal_path=layer_data.get("normal_texture"),
        )
        if mat:
            mesh.materials.append(mat)

        # 4. 添加 bevel modifier
        bevel = obj.modifiers.new("Bevel", "BEVEL")
        bevel.width = bevel_w
        bevel.segments = 2
        bevel.limit_method = "ANGLE"

        return obj

    def build_object(self, obj_data: dict) -> bpy.types.Object:
        """构建单个物体 mesh（基于前端顶点数据）。"""
        obj_id = obj_data["object_id"]
        name = f"Object_{obj_id}"

        # 1. 构建 mesh from vertices/faces
        mesh = bpy.data.meshes.new(name)
        bm = bmesh.new()

        scale = obj_data.get("scale", [1, 1, 1])
        pos = tuple(obj_data.get("position", [0, 0, 0]))
        bevel_w = obj_data.get("bevel_width", 0.005)

        # 创建顶点
        vert_map = {}
        for vi, v in enumerate(obj_data.get("vertices", [])):
            vx = float(v.get("x", 0)) * scale[0]
            vy = float(v.get("y", 0)) * scale[1]
            vz = float(v.get("z", 0)) * scale[2]
            vert_map[vi] = bm.verts.new((vx, vy, vz))

        bm.verts.ensure_lookup_table()

        # 创建面
        for f in obj_data.get("faces", []):
            indices = f.get("indices", [])
            if len(indices) >= 3:
                try:
                    vs = [vert_map[i] for i in indices if i in vert_map]
                    if len(vs) >= 3:
                        bm.faces.new(vs)
                except ValueError:
                    pass  # 跳过重复 face

        bm.to_mesh(mesh)
        bm.free()

        # 2. 创建 Object
        obj = bpy.data.objects.new(name, mesh)
        obj.location = pos
        bpy.context.scene.collection.objects.link(obj)

        # 3. 应用材质
        from .material_factory import MaterialFactory
        mat = MaterialFactory.create_paper_material(
            f"Mat_{name}",
            diffuse_path=obj_data.get("diffuse_texture"),
            normal_path=obj_data.get("normal_texture"),
        )
        if mat:
            mesh.materials.append(mat)

        # 4. 添加 bevel modifier
        bevel = obj.modifiers.new("Bevel", "BEVEL")
        bevel.width = bevel_w
        bevel.segments = 2

        return obj

    def export(self, output_path: str, fmt: str = "glb") -> dict:
        """导出为 GLB/FBX。"""
        if fmt == "glb":
            bpy.ops.export_scene.gltf(
                filepath=output_path,
                use_selection=False,
                export_format="GLB",
                export_materials="EXPORT",
                export_colors=True,
                export_normals=True,
                export_texcoords=True,
                export_apply=True,
                export_lights=False,
                export_cameras=False,
                export_yup=True,
                export_animations=False,
            )
        elif fmt == "fbx":
            bpy.ops.export_scene.fbx(
                filepath=output_path,
                use_selection=False,
                global_scale=1.0,
                axis_forward="-Z",
                axis_up="Y",
                object_types={"MESH"},
                use_mesh_modifiers=True,
                mesh_smooth_type="FACE",
            )
        else:
            raise ValueError(f"Unsupported format: {fmt}")

        # 返回统计
        import os
        size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
        vertex_count = sum(
            len(mesh.vertices) for mesh in bpy.data.meshes
            if mesh.users > 0
        )
        face_count = sum(
            len(mesh.polygons) for mesh in bpy.data.meshes
            if mesh.users > 0
        )
        object_count = sum(
            1 for obj in bpy.data.objects
            if obj.type == "MESH" and obj.users_collection
        )

        return {
            "file_path": output_path,
            "file_size": size,
            "object_count": object_count,
            "vertex_count": vertex_count,
            "face_count": face_count,
        }
```

### C.2.5 材质工厂 `core/material_factory.py`

```python
# blender_aicss/core/material_factory.py
"""
材质工厂 - 复用材质的 LRU 缓存。

避免重复加载相同纹理（同一张图被 100 个物体引用时只加载 1 次）。
"""
import bpy
from pathlib import Path
from typing import Optional
from collections import OrderedDict


class MaterialFactory:
    _cache: OrderedDict[str, bpy.types.Material] = OrderedDict()
    _cache_max_size = 100

    @classmethod
    def get_or_create(
        cls,
        name: str,
        diffuse_path: Optional[str] = None,
        normal_path: Optional[str] = None,
    ) -> Optional[bpy.types.Material]:
        """获取或创建材质（LRU 缓存）。"""
        cache_key = f"{diffuse_path or ''}|{normal_path or ''}"
        if cache_key in cls._cache:
            # LRU: 移到末尾
            mat = cls._cache.pop(cache_key)
            cls._cache[cache_key] = mat
            return mat

        mat = cls.create_paper_material(name, diffuse_path, normal_path)
        if mat:
            cls._cache[cache_key] = mat
            if len(cls._cache) > cls._cache_max_size:
                # 弹出最久未使用的
                old_key, old_mat = cls._cache.popitem(last=False)
                if old_mat.users == 0:
                    bpy.data.materials.remove(old_mat)
        return mat

    @classmethod
    def create_paper_material(
        cls,
        name: str,
        diffuse_path: Optional[str] = None,
        normal_path: Optional[str] = None,
    ) -> Optional[bpy.types.Material]:
        """创建纸雕风格 PBR 材质。"""
        if not diffuse_path and not normal_path:
            return None

        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()

        # 基础节点
        output = nodes.new("ShaderNodeOutputMaterial")
        output.location = (400, 0)
        principled = nodes.new("ShaderNodeBsdfPrincipled")
        principled.location = (0, 0)
        links.new(principled.outputs["BSDF"], output.inputs["Surface"])

        # Diffuse 纹理
        if diffuse_path and Path(diffuse_path).exists():
            try:
                img = bpy.data.images.load(diffuse_path)
                img.colorspace_settings.name = "sRGB"
                tex = nodes.new("ShaderNodeTexImage")
                tex.image = img
                tex.location = (-400, 100)
                links.new(tex.outputs["Color"], principled.inputs["Base Color"])
            except Exception as exc:
                print(f"[AICSS Material] Could not load diffuse: {exc}")

        # Normal 纹理
        if normal_path and Path(normal_path).exists():
            try:
                nimg = bpy.data.images.load(normal_path)
                nimg.colorspace_settings.name = "Non-Color"
                ntex = nodes.new("ShaderNodeTexImage")
                ntex.image = nimg
                ntex.location = (-400, -150)
                normal_node = nodes.new("ShaderNodeNormalMap")
                normal_node.location = (-100, -150)
                links.new(ntex.outputs["Color"], normal_node.inputs["Color"])
                links.new(normal_node.outputs["Normal"], principled.inputs["Normal"])
            except Exception as exc:
                print(f"[AICSS Material] Could not load normal: {exc}")

        # 纸雕质感参数
        principled.inputs["Roughness"].default_value = 0.9
        principled.inputs["Specular IOR Level"].default_value = 0.0
        principled.inputs["Sheen Weight"].default_value = 0.1

        return mat

    @classmethod
    def clear_cache(cls):
        """清空材质缓存。"""
        for mat in list(cls._cache.values()):
            if mat.users == 0:
                bpy.data.materials.remove(mat)
        cls._cache.clear()

    @classmethod
    def cache_stats(cls) -> dict:
        """获取缓存统计信息。"""
        return {
            "size": len(cls._cache),
            "max_size": cls._cache_max_size,
            "memory_estimate_mb": sum(
                sum(img.size[:2]) * 4 / 1024 / 1024
                for mat in cls._cache.values()
                for node in mat.node_tree.nodes
                if node.type == "TEX_IMAGE" and node.image
                for img in [node.image]
            ),
        }
```

### C.2.6 任务队列 `core/job_queue.py`

```python
# blender_aicss/core/job_queue.py
"""
异步任务队列 - 在 Blender 主线程中串行执行任务。

Blender 的 bpy API 不是线程安全的，所有修改必须在主线程执行。
HTTP 服务接收请求 → 投递到队列 → 主线程执行。
"""
import asyncio
from typing import Callable, Any, Optional
from dataclasses import dataclass, field
import time


@dataclass
class Job:
    id: str
    handler: Callable
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    future: asyncio.Future = None
    created_at: float = field(default_factory=time.time)


class JobQueue:
    """异步任务队列，使用 Blender timer 注册到主线程。"""

    def __init__(self):
        self._queue: asyncio.Queue = None
        self._running = False
        self._stats = {
            "submitted": 0,
            "completed": 0,
            "failed": 0,
            "total_time": 0.0,
        }

    async def submit(self, job: Job):
        """提交任务到队列。"""
        if self._queue is None:
            self._queue = asyncio.Queue()
        self._stats["submitted"] += 1
        await self._queue.put(job)

    async def process_one(self) -> Optional[Job]:
        """处理一个任务（由 Blender timer 调用）。"""
        if self._queue is None or self._queue.empty():
            return None

        job = await self._queue.get()
        try:
            start = time.time()
            result = await job.handler(*job.args, **job.kwargs)
            self._stats["completed"] += 1
            self._stats["total_time"] += time.time() - start
            if job.future and not job.future.done():
                job.future.set_result(result)
            return job
        except Exception as exc:
            self._stats["failed"] += 1
            if job.future and not job.future.done():
                job.future.set_exception(exc)
            return job

    def get_stats(self) -> dict:
        return {
            **self._stats,
            "queue_depth": self._queue.qsize() if self._queue else 0,
        }


_job_queue = JobQueue()


def get_job_queue() -> JobQueue:
    return _job_queue


# Blender timer 注册：每 0.1s 处理一个任务
def register_timer():
    import bpy
    bpy.app.timers.register(_process_queue_timer, persistent=True)


def unregister_timer():
    import bpy
    if bpy.app.timers.is_registered(_process_queue_timer):
        bpy.app.timers.unregister(_process_queue_timer)


async def _process_queue_timer():
    """由 Blender 主循环调用的 timer。"""
    job = await _job_queue.process_one()
    return 0.1  # 0.1 秒后再次调用
```

### C.2.7 HTTP 服务 `server/http_server.py`

```python
# blender_aicss/server/http_server.py
"""
AICSS HTTP 服务 - aiohttp 实现的 REST API。

服务在 Blender 启动时自动开启（如果用户启用），
在 Blender 关闭时优雅停止。
"""
import asyncio
import json
import logging
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

import bpy

logger = logging.getLogger("aicss.http")


class AICSSHttpServer:
    def __init__(self, host="127.0.0.1", port=8889, enable_websocket=True):
        self.host = host
        self.port = port
        self.enable_websocket = enable_websocket
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._runner: Optional[asyncio.Runner] = None
        self._thread: Optional[threading.Thread] = None
        self._site = None
        self._app = None
        self._started = False

    def start(self):
        """在后台线程启动 aiohttp 服务。"""
        if self._started:
            return
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        # 等待服务启动完成
        for _ in range(50):  # 最多等 5s
            if self._started:
                break
            time.sleep(0.1)

        logger.info(f"[AICSS HTTP] 服务已启动: http://{self.host}:{self.port}")

    def stop(self):
        """停止 HTTP 服务。"""
        if not self._started:
            return
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
        if self._thread:
            self._thread.join(timeout=5)
        self._started = False

    def _run_loop(self):
        """在后台线程运行 asyncio 事件循环。"""
        from aiohttp import web
        from .routes import setup_routes

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        self._app = web.Application()
        setup_routes(self._app)
        self._app["aicss_server"] = self

        try:
            self._runner = web.AppRunner(self._app)
            self._loop.run_until_complete(self._runner.setup())
            self._site = web.TCPSite(self._runner, self.host, self.port)
            self._loop.run_until_complete(self._site.start())
            self._started = True
            self._loop.run_forever()
        except Exception as exc:
            logger.error(f"[AICSS HTTP] 服务异常: {exc}")
        finally:
            self._loop.close()

    async def _shutdown(self):
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()
        self._loop.stop()
```

### C.2.8 路由 `server/routes.py`

```python
# blender_aicss/server/routes.py
from aiohttp import web
import json
import os
import tempfile
import uuid
from pathlib import Path
from datetime import datetime, timezone


def setup_routes(app: web.Application):
    """注册所有 HTTP 路由。"""

    # 健康检查
    app.router.add_get("/health", health_check)

    # 场景管理
    app.router.add_post("/scenes", create_scene)
    app.router.add_get("/scenes/{scene_id}", get_scene_info)
    app.router.add_delete("/scenes/{scene_id}", delete_scene)
    app.router.add_get("/scenes", list_scenes)

    # 导出
    app.router.add_post("/scenes/{scene_id}/export", export_scene)
    app.router.add_get("/scenes/{scene_id}/preview", preview_scene)

    # 缓存管理
    app.router.add_get("/cache/stats", get_cache_stats)
    app.router.add_post("/cache/clear", clear_cache)

    # 服务信息
    app.router.add_get("/info", server_info)


async def health_check(request):
    return web.json_response({"status": "ok", "service": "aicss-blender"})


async def server_info(request):
    import bpy
    return web.json_response({
        "blender_version": ".".join(str(v) for v in bpy.app.version),
        "scene_objects": len(bpy.data.objects),
        "meshes": len(bpy.data.meshes),
        "materials": len(bpy.data.materials),
        "render_engine": bpy.context.scene.render.engine,
    })


async def create_scene(request):
    """创建/替换场景。"""
    import bpy
    from ..core.scene_builder import SceneBuilder
    from ..core.job_queue import JobQueue, Job

    payload = await request.json()
    scene_id = payload.get("scene_id") or f"scene_{uuid.uuid4().hex[:8]}"
    scene_data = payload.get("scene_data", {})

    # 提交到队列（异步）
    job_queue = JobQueue()
    loop = asyncio.get_event_loop()
    future = loop.create_future()

    async def _build_scene():
        builder = SceneBuilder()
        builder.clear_scene()
        built_objects = []
        for layer in scene_data.get("layers", []):
            obj = builder.build_layer(layer)
            built_objects.append(obj.name)
        for obj_data in scene_data.get("objects", []):
            obj = builder.build_object(obj_data)
            built_objects.append(obj.name)
        return {"scene_id": scene_id, "objects": built_objects}

    job = Job(
        id=scene_id,
        handler=_build_scene,
        future=future,
    )
    await job_queue.submit(job)
    result = await future
    return web.json_response(result)


async def export_scene(request):
    """导出场景为 GLB/FBX。"""
    from ..core.scene_builder import SceneBuilder
    from ..core.job_queue import JobQueue, Job

    scene_id = request.match_info["scene_id"]
    payload = await request.json()
    fmt = payload.get("format", "glb")
    output_dir = payload.get("output_dir") or tempfile.gettempdir()

    job_queue = JobQueue()
    loop = asyncio.get_event_loop()
    future = loop.create_future()

    async def _export():
        # 下载 base64 纹理到临时目录
        from ..core.texture_downloader import download_textures
        scene_data = payload.get("scene_data", {})
        textures_dir = await download_textures(scene_data)

        # 重建本地纹理路径
        await _resolve_local_texture_paths(scene_data, textures_dir)

        # 构建 + 导出
        builder = SceneBuilder()
        builder.clear_scene()
        for layer in scene_data.get("layers", []):
            builder.build_layer(layer)
        for obj_data in scene_data.get("objects", []):
            builder.build_object(obj_data)

        output_path = os.path.join(output_dir, f"{scene_id}.{fmt}")
        return builder.export(output_path, fmt=fmt)

    job = Job(id=f"export_{scene_id}", handler=_export, future=future)
    await job_queue.submit(job)

    result = await future
    return web.json_response(result)


async def preview_scene(request):
    """返回场景截图（PNG base64）。"""
    import bpy
    import base64

    scene_id = request.match_info["scene_id"]
    width = int(request.query.get("width", 800))
    height = int(request.query.get("height", 600))

    # 渲染当前视图
    bpy.context.scene.render.resolution_x = width
    bpy.context.scene.render.resolution_y = height
    bpy.context.scene.render.filepath = f"/tmp/aicss_preview_{scene_id}.png"
    bpy.ops.render.opengl(write_still=True)

    # 读取并编码
    img_path = bpy.context.scene.render.filepath
    if os.path.exists(img_path):
        with open(img_path, "rb") as f:
            img_data = base64.b64encode(f.read()).decode()
        return web.json_response({
            "preview_b64": img_data,
            "width": width,
            "height": height,
        })
    return web.json_response({"error": "Preview render failed"}, status=500)


async def get_cache_stats(request):
    from ..core.material_factory import MaterialFactory
    return web.json_response(MaterialFactory.cache_stats())


async def clear_cache(request):
    from ..core.material_factory import MaterialFactory
    MaterialFactory.clear_cache()
    return web.json_response({"status": "cleared"})


async def get_scene_info(request):
    """获取当前 Blender 场景的对象统计信息。"""
    import bpy

    scene_id = request.match_info["scene_id"]
    objects = []
    for obj in bpy.data.objects:
        if obj.type == "MESH":
            objects.append({
                "name": obj.name,
                "type": obj.type,
                "vertex_count": len(obj.data.vertices),
                "face_count": len(obj.data.polygons),
                "location": list(obj.location),
                "has_material": bool(obj.data.materials),
            })
    return web.json_response({
        "scene_id": scene_id,
        "objects": objects,
        "total_meshes": len(bpy.data.meshes),
    })


async def list_scenes(request):
    """列出当前所有 scene。"""
    import bpy
    return web.json_response({
        "scenes": [
            {"name": s.name, "objects": len(s.objects)}
            for s in bpy.data.scenes
        ]
    })


async def delete_scene(request):
    """删除当前场景的对象。"""
    import bpy
    scene_id = request.match_info["scene_id"]
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    return web.json_response({"deleted": scene_id})
```

### C.2.9 操作器 `operators/aicss_operators.py`

```python
# blender_aicss/operators/aicss_operators.py
import bpy
from bpy.types import Operator


class AICSS_OT_StartServer(Operator):
    bl_idname = "aicss.start_server"
    bl_label = "启动 AICSS HTTP 服务"
    bl_description = "在 Blender 中启动 AICSS HTTP 服务"

    def execute(self, context):
        from ..preferences import get_server
        server = get_server()
        server.start()
        prefs = context.preferences.addons[__package__.split(".")[0]].preferences
        self.report({'INFO'}, f"AICSS HTTP 服务已启动: http://{prefs.server_host}:{prefs.server_port}")
        return {'FINISHED'}


class AICSS_OT_StopServer(Operator):
    bl_idname = "aicss.stop_server"
    bl_label = "停止 AICSS HTTP 服务"

    def execute(self, context):
        from ..preferences import get_server
        server = get_server()
        server.stop()
        self.report({'INFO'}, "AICSS HTTP 服务已停止")
        return {'FINISHED'}


class AICSS_OT_QuickExport(Operator):
    """快速导出当前场景（开发调试用）"""
    bl_idname = "aicss.quick_export"
    bl_label = "快速导出 GLB"

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    def execute(self, context):
        from ..core.scene_builder import SceneBuilder
        if not self.filepath:
            self.filepath = "/tmp/aicss_quick_export.glb"
        builder = SceneBuilder()
        result = builder.export(self.filepath, fmt="glb")
        self.report({'INFO'}, f"已导出: {self.filepath} ({result['file_size']:,} bytes)")
        return {'FINISHED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


class AICSS_OT_ClearCache(Operator):
    bl_idname = "aicss.clear_cache"
    bl_label = "清空材质缓存"

    def execute(self, context):
        from ..core.material_factory import MaterialFactory
        MaterialFactory.clear_cache()
        self.report({'INFO'}, "材质缓存已清空")
        return {'FINISHED'}
```

### C.2.10 UI 面板 `ui.py`

```python
# blender_aicss/ui.py
import bpy
from bpy.types import Panel


class AICSS_PT_Panel(Panel):
    bl_idname = "AICSS_PT_panel"
    bl_label = "AICSS 集成"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AICSS"

    def draw(self, context):
        layout = self.layout
        prefs = context.preferences.addons[__package__].preferences

        box = layout.box()
        box.label(text="服务配置", icon='NETWORK')
        box.prop(prefs, "server_host")
        box.prop(prefs, "server_port")
        box.prop(prefs, "auto_start_server")

        row = box.row(align=True)
        row.operator("aicss.start_server", icon='PLAY')
        row.operator("aicss.stop_server", icon='PAUSE')

        layout.separator()

        box = layout.box()
        box.label(text="快速操作", icon='EXPORT')
        box.operator("aicss.quick_export", icon='MESH_UVSPLIT')
        box.operator("aicss.clear_cache", icon='TRASH')

        box.prop(prefs, "default_format")


def register():
    pass


def unregister():
    pass
```

---

## C.3 Python 端 Blender 客户端

```python
# backend/app/services/blender_client.py
"""
Python 端 Blender HTTP 客户端 - 替代 subprocess 模式。

新流程：
1. Python 启动 Blender 时 --python-use-external 或者用一个 Blender 服务进程
2. 客户端通过 HTTP 调用 Blender
3. Blender 通过 bpy 直接构建场景 + 导出
4. Python 端接收结果并保存到 project_store_mesh

启动 Blender 服务进程（一次性）：
    blender --background --python blender_aicss/__init__.py -- --auto-start
    → Blender 启动后插件自动注册并开启 HTTP 服务
"""
import asyncio
import aiohttp
import hashlib
import logging
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from app.config import settings

logger = logging.getLogger("aicss.blender_client")


class BlenderClient:
    """Blender HTTP 服务客户端。"""

    def __init__(self, host: str = "127.0.0.1", port: int = 8889, timeout: int = 300):
        self.base_url = f"http://{host}:{port}"
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def is_available(self) -> bool:
        """检查 Blender 服务是否在线。"""
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/health", timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False

    async def get_info(self) -> dict:
        """获取 Blender 服务信息。"""
        session = await self._get_session()
        async with session.get(f"{self.base_url}/info") as resp:
            resp.raise_for_status()
            return await resp.json()

    async def create_scene(self, scene_id: str, scene_data: dict) -> dict:
        """在 Blender 中创建场景（暂不导出）。"""
        session = await self._get_session()
        payload = {"scene_id": scene_id, "scene_data": scene_data}
        async with session.post(f"{self.base_url}/scenes", json=payload) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def export_scene(
        self,
        scene_id: str,
        scene_data: dict,
        output_dir: str,
        fmt: str = "glb",
        include_textures: bool = True,
    ) -> dict:
        """调用 Blender 导出场景，返回文件路径和统计信息。"""
        session = await self._get_session()
        payload = {
            "format": fmt,
            "output_dir": output_dir,
            "include_textures": include_textures,
            "scene_data": scene_data,
        }
        async with session.post(
            f"{self.base_url}/scenes/{scene_id}/export", json=payload
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def get_preview(
        self,
        scene_id: str,
        width: int = 800,
        height: int = 600,
    ) -> str:
        """获取场景预览（base64 PNG）。"""
        session = await self._get_session()
        async with session.get(
            f"{self.base_url}/scenes/{scene_id}/preview",
            params={"width": width, "height": height},
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data.get("preview_b64", "")

    async def get_cache_stats(self) -> dict:
        session = await self._get_session()
        async with session.get(f"{self.base_url}/cache/stats") as resp:
            resp.raise_for_status()
            return await resp.json()

    async def clear_cache(self) -> dict:
        session = await self._get_session()
        async with session.post(f"{self.base_url}/cache/clear") as resp:
            resp.raise_for_status()
            return await resp.json()


# 单例
_blender_client: Optional[BlenderClient] = None


def get_blender_client() -> BlenderClient:
    global _blender_client
    if _blender_client is None:
        _blender_client = BlenderClient(
            host=os.environ.get("BLENDER_HOST", "127.0.0.1"),
            port=int(os.environ.get("BLENDER_PORT", "8889")),
        )
    return _blender_client


# Blender 服务进程管理
class BlenderServiceManager:
    """管理 Blender 服务进程的启动和停止。"""

    @staticmethod
    def is_running() -> bool:
        """检查 Blender 进程是否在运行。"""
        import psutil
        for proc in psutil.process_iter(['name']):
            if 'blender' in proc.info['name'].lower():
                return True
        return False

    @staticmethod
    def start(blender_exe: str = None, port: int = 8889) -> bool:
        """启动 Blender 服务进程。"""
        if BlenderServiceManager.is_running():
            return True

        blender_exe = blender_exe or os.environ.get(
            "BLENDER_EXECUTABLE", "blender"
        )
        addon_path = str(Path(__file__).parent.parent.parent.parent / "blender_aicss")

        # 启动 blender --background + 加载插件
        cmd = [
            blender_exe,
            "--background",
            "--python-expr",
            f"import bpy; bpy.ops.preferences.addon_enable(module='blender_aicss'); "
            f"from blender_aicss.preferences import get_server; "
            f"server = get_server(); server.start()",
        ]

        try:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={**os.environ, "AICSS_BLENDER_PORT": str(port)},
            )
            return True
        except Exception as e:
            logger.error(f"[BlenderService] 启动失败: {e}")
            return False
```

### C.3.1 改造后的 mesh_exporter.py（约 200 行 → 100 行）

```python
# backend/app/services/mesh_exporter.py (改造后)

import logging
import os
from typing import Optional

from .blender_client import get_blender_client, BlenderServiceManager
from .project_store_mesh import project_store_mesh

logger = logging.getLogger("aicss")


def export_full_scene(
    analysis_result: dict,
    depth_split_result: dict,
    layer_assets: dict,
    object_assets: dict,
    billboard_offsets: dict,
    scene_id: Optional[str] = None,
    output_dir: Optional[str] = None,
    output_format: str = "glb",
    include_textures: bool = True,
    project_id: Optional[str] = None,
) -> dict:
    """改造后：调用 Blender HTTP 服务，无需 subprocess。"""

    # 1. 确保 Blender 服务在线（不在线则启动）
    client = get_blender_client()
    if not await_sync(client.is_available()):
        logger.info("[mesh_exporter] Blender 服务未启动，尝试启动...")
        if not BlenderServiceManager.start():
            return {
                "success": False,
                "error": "Blender service unavailable and could not be started",
            }

    # 2. 构建场景数据（与之前相同）
    from dataclasses import asdict
    scene_data = _build_scene_data_dict(
        analysis_result, depth_split_result, layer_assets,
        object_assets, billboard_offsets,
    )

    # 3. 调用 Blender 导出
    scene_id = scene_id or f"scene_{uuid.uuid4().hex[:8]}"
    output_dir = output_dir or settings.workspace_dir / "projects" / project_id / "meshes" / "scenes"
    os.makedirs(output_dir, exist_ok=True)

    try:
        result = await_sync(
            client.export_scene(
                scene_id=scene_id,
                scene_data=scene_data,
                output_dir=output_dir,
                fmt=output_format,
                include_textures=include_textures,
            )
        )

        # 4. 保存到 project_store_mesh
        if project_id:
            await_sync(project_store_mesh.save_scene_mesh(
                project_id=project_id,
                scene_id=scene_id,
                mesh_data=open(result["file_path"], "rb").read(),
                format=output_format,
                object_count=result.get("object_count", 0),
                vertex_count=result.get("vertex_count", 0),
                face_count=result.get("face_count", 0),
                include_textures=include_textures,
            ))

        return {
            "success": True,
            "file_path": result["file_path"],
            "file_size": result["file_size"],
            "object_count": result.get("object_count", 0),
            "vertex_count": result.get("vertex_count", 0),
            "face_count": result.get("face_count", 0),
        }

    except Exception as e:
        logger.error(f"[mesh_exporter] 导出失败: {e}")
        return {"success": False, "error": str(e)}


def await_sync(coro):
    """在同步上下文中运行 async 函数。"""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)
```

---

## C.4 Dify 工作流调用 Blender

```yaml
# workflows/blender_export.yml
name: blender_export
description: 调用 Blender 服务导出 3D mesh

nodes:
  - id: start
    type: start
    data:
      variables:
        - { name: project_id, required: true }
        - { name: scene_id, required: true }
        - { name: scene_data, type: object, required: true }
        - { name: format, default: "glb" }

  - id: http_build_scene
    type: http-request
    data:
      title: Step 1: 在 Blender 中构建场景
      method: POST
      url: "http://127.0.0.1:8889/scenes"
      body:
        type: json
        data:
          scene_id: "{{#start.scene_id#}}"
          scene_data: "{{#start.scene_data#}}"

  - id: http_export
    type: http-request
    data:
      title: Step 2: 调用 Blender 导出
      method: POST
      url: "http://127.0.0.1:8889/scenes/{{#start.scene_id#}}/export"
      body:
        type: json
        data:
          format: "{{#start.format#}}"
          output_dir: "/workspace/projects/{{#start.project_id#}}/meshes/scenes"
          scene_data: "{{#start.scene_data#}}"

  - id: code_process
    type: code
    data:
      title: Step 3: 处理 Blender 返回
      variables:
        - { name: blender_result, value_selector: [http_export, response] }
      code_language: python3
      code: |
        import os, hashlib
        result = blender_result
        if not result.get("file_path") or not os.path.exists(result["file_path"]):
            return {"success": False, "error": "Blender did not produce output file"}
        
        with open(result["file_path"], "rb") as f:
            content = f.read()
        
        return {
            "success": True,
            "file_path": result["file_path"],
            "file_size": len(content),
            "file_sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
            "object_count": result.get("object_count", 0),
            "vertex_count": result.get("vertex_count", 0),
            "face_count": result.get("face_count", 0),
        }
      outputs:
        processed: { type: object, children: null }

  - id: http_persist
    type: http-request
    data:
      title: Step 4: 持久化到 FastAPI
      method: POST
      url: "{{#env.AICSS_API_URL#}}/api/aicss/v2/meshes/save"
      body:
        type: json
        data:
          project_id: "{{#start.project_id#}}"
          mesh_meta: "{{#code_process.processed#}}"

  - id: end
    type: end
    data:
      outputs:
        - { variable: result, value_selector: [http_persist, response] }
```

---

## C.5 完整三层架构（终版）

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      AICSS 完整技术栈（终极方案）                          │
└─────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────┐
│  Frontend (React + Vite + Three.js)                                  │
└────────────────────────────────┬──────────────────────────────────────┘
                                 │
                                 ▼
┌───────────────────────────────────────────────────────────────────────┐
│  Dify Workflows Server（编排层）                                       │
│  ═══════════════════════════════                                     │
│  8 个核心工作流 (.dify.yml)：                                          │
│  • script_parse             • scene_asset                             │
│  • shot_generation          • character_asset                        │
│  • video_generation         • blender_export                         │
│  • script_to_shots          • master_production                      │
└────────────────────────────────┬──────────────────────────────────────┘
                                 │ HTTP
                                 ▼
┌───────────────────────────────────────────────────────────────────────┐
│  ComfyUI Server（推理层 - 图像/视频）                                   │
│  ═══════════════════════════════════                                  │
│  10+ 个工作流 (.json)：                                                │
│  • character_three_view     • depth_anything_v2                       │
│  • scene_keyframes          • grounding_dino                          │
│  • txt2img_basic            • sam2_segment                            │
│  • img2img                  • wan2.1_i2v                              │
│  • lama_inpaint             • paper_diorama                           │
└────────────────────────────────┬──────────────────────────────────────┘
                                 │ HTTP
                                 ▼
┌───────────────────────────────────────────────────────────────────────┐
│  Blender Addon (3D 导出层 - HTTP 服务常驻)                              │
│  ═══════════════════════════════════════                              │
│  • HTTP 服务 (aiohttp) :8889                                          │
│  • bpy 场景构建器 + 材质工厂 + 任务队列                                │
│  • LRU 材质缓存                                                        │
│  • WebSocket 进度推送                                                  │
└────────────────────────────────┬──────────────────────────────────────┘
                                 │ HTTP
                                 ▼
┌───────────────────────────────────────────────────────────────────────┐
│  FastAPI Gateway（API 层 - 极简）                                      │
│  ══════════════════════════════                                       │
│  • 路由：~30 个端点                                                    │
│  • 项目存储：project_store.py                                         │
│  • Mesh 存储：project_store_mesh.py                                   │
│  • 3D Mesh 文件下载                                                   │
│  • 健康检查 + 配置                                                     │
│                                                                       │
│  替代职责：                                                           │
│  • Blender 客户端调用 Blender HTTP 服务（替代 subprocess）             │
│  • ComfyUI 客户端调用 ComfyUI                                        │
│  • Dify 客户端调用 Dify                                              │
└───────────────────────────────────────────────────────────────────────┘
```

### C.5.1 代码量与工作量

| 组件 | 现状（Python） | 终极方案 | 节省 |
|------|------------|---------|------|
| 剧本解析 | 1971行 | Dify DSL (~150 行) | 99% |
| 分镜生成 | 837行 | Dify DSL (~120 行) | 99% |
| 角色/场景生成 | 898行 | Dify → ComfyUI (~400 DSL) | 100% |
| 视频生成 | 753行 | Dify → ComfyUI (~200 DSL) | 100% |
| 图像管线（Depth/SAM/DINO/LaMa） | ~900行 | ComfyUI (10 JSON) | 100% |
| **Mesh 导出** | **1026行** | **Blender 插件（~600行 Python）+ 客户端（~200行）** | **~25%** |
| FastAPI 路由 | ~1500行 | ~500行（瘦身） | 67% |
| **总计** | **~10000** | **~1500 行 Python + 8 Dify + 10 ComfyUI + 1 Blender addon** | **85%** |

### C.5.2 实施工时

| 阶段 | 内容 | 工时 |
|------|-----|-----|
| Phase 1 | Blender 插件开发（含 HTTP 服务、bpy 集成） | 80-100h |
| Phase 2 | Python 端 blender_client.py（替代 subprocess） | 20-30h |
| Phase 3 | Blender 服务进程管理（启动/停止/监控） | 20-30h |
| Phase 4 | 测试与回归 | 30-40h |
| **总计** | — | **150-200h** |

---

## C.6 风险与缓解

| 风险 | 说明 | 缓解方案 |
|------|------|---------|
| Blender 进程崩溃 | aiohttp 异常退出 | Blender 服务管理器自动重启 + 健康检查 |
| bpy 线程不安全 | HTTP 在后台线程，bpy 调用必须在主线程 | 任务队列（JobQueue）+ Blender Timer |
| 多用户并发 | 多个 Blender 进程同时操作一个 .blend 文件 | 队列串行化 + 文件锁 |
| 启动失败（缺 aiohttp） | Blender 内置 Python 不一定有 aiohttp | 用 Blender 自带的 http.server 或嵌入自定义 socket |
| 服务发现 | Python 端如何知道 Blender 在哪个端口 | 环境变量 BLENDER_PORT + 健康检查 |
| Blender 版本兼容 | API 在 3.x → 4.x 有变化 | 显式版本检查 `bpy.app.version` |
| 内存泄漏 | Blender 服务常驻后内存累积 | 缓存清理 API + 定期 restart |

---

## C.7 调试技巧

### 启用详细日志

```python
# 在 Blender 中打开 Python Console 运行：
import logging
logging.basicConfig(level=logging.DEBUG)
bpy.app.debug = True
```

### 测试 HTTP 服务

```bash
# 健康检查
curl http://127.0.0.1:8889/health
→ {"status": "ok", "service": "aicss-blender"}

# 服务信息
curl http://127.0.0.1:8889/info
→ {"blender_version": "4.2.0", "scene_objects": 5, ...}

# 创建场景
curl -X POST http://127.0.0.1:8889/scenes \
  -H "Content-Type: application/json" \
  -d '{"scene_id": "test", "scene_data": {...}}'

# 导出
curl -X POST http://127.0.0.1:8889/scenes/test/export \
  -H "Content-Type: application/json" \
  -d '{"format": "glb", "output_dir": "/tmp"}' \
  -o scene.glb
```

---

## C.8 总结

> **Blender 插件 + HTTP 服务模式将 mesh_exporter.py 从 1026 行压缩到约 200 行客户端 + 600 行插件代码（-25% Python），但带来质变：**
> - 启动开销 5-15s → 0s（常驻）
> - 单请求 → 并发队列
> - 无状态 → 有状态（可查询、可修改）
> - 单向 → 双向（WebSocket 实时进度）
> - 资源不可复用 → LRU 材质缓存
>
> **结合 Dify + ComfyUI，AICSS 后端 85% 的 Python 代码可被工作流（DSL/JSON/Blender插件）替代。整个技术栈进入"工作流即代码"时代。**

---

*文档生成时间: 2026-07-31*
*基于项目版本：AICinematicSpatialSystem v2*
