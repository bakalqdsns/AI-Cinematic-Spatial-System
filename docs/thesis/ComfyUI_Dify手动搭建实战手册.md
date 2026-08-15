# ComfyUI + Dify 手动搭建实战手册（含知识库与完整提示词）

> **目标：在 WSL2 Ubuntu 里手动一步步搭建 ComfyUI 与 Dify，给出可复制粘贴的精确命令、每个工作流的完整提示词（system + user）、以及知识库（RAG）的接入与最佳实践。**
>
> 适用版本：AICinematicSpatialSystem v2
> 文档日期：2026-08-01
> 预计搭建时间：ComfyUI 1-2h（不含模型下载）、Dify 30-45min、知识库 30min

---

## 0. 准备清单

```bash
# 在 WSL Ubuntu 内确认环境
cd ~/projects
mkdir -p aicss-tools/{comfyui,dify,models,workflows,knowledge_base}
cd aicss-tools

# 确认 GPU
nvidia-smi
# → RTX 4060 Ti 16GB

# 确认 Docker 与 Python
docker --version     # 29.x
python3 --version    # 3.11+
```

下文所有路径基于 `~/projects/aicss-tools/`，如需换路径请同步替换。

---

# 第一部分：ComfyUI 手动搭建

## 1.1 安装 ComfyUI

```bash
# 1. 克隆仓库（最新版）
cd ~/projects/aicss-tools/comfyui
git clone https://github.com/comfyanonymous/ComfyUI.git .
git checkout master   # 或指定稳定版 tag，如 v0.3.39

# 2. 创建虚拟环境（推荐用 conda 或 venv 都行）
python3 -m venv venv
source venv/bin/activate

# 3. 安装 PyTorch（CUDA 12.4，针对 RTX 4060 Ti）
pip install --upgrade pip
pip install torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cu124

# 4. 安装 ComfyUI 依赖
pip install -r requirements.txt

# 5. 验证
python -c "import torch; print(torch.cuda.is_available(), torch.version.cuda)"
# → True 12.4
```

### 验证 ComfyUI 启动

```bash
python main.py --listen 0.0.0.0 --port 8188 --disable-auto-launch
```

浏览器访问 `http://localhost:8188`（在 Windows 浏览器输入 `http://127.0.0.1:8188`，WSL2 会自动转发）。

按 `Ctrl+C` 停止，下面继续装模型和插件。

## 1.2 安装必备自定义节点

```bash
cd ~/projects/aicss-tools/comfyui/custom_nodes

# 管理器（GUI 安装其他节点用）
git clone https://github.com/ltdrdata/ComfyUI-Manager.git

# 视频工具（视频合成、预览、合并）
git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git

# Impact Pack（检测/分割/修复增强）
git clone https://github.com/ltdrdata/ComfyUI-Impact-Pack.git

# Wan2.1 视频模型封装
git clone https://github.com/city96/ComfyUI-WanVideoWrapper.git

# 实用节点合集
git clone https://github.com/cubiq/ComfyUI_essentials.git

# 安装每个节点的 Python 依赖
cd ~/projects/aicss-tools/comfyui
for d in custom_nodes/*/; do
    if [ -f "$d/requirements.txt" ]; then
        echo "==> Installing for $d"
        pip install -r "$d/requirements.txt" 2>&1 | tail -3
    fi
done

# Impact Pack 需要额外下载模型（约 2GB，首次启动自动）
# WanVideo 需要额外依赖
pip install ftfy einops timm sentencepiece
```

### 模型放置规范

```
~/projects/aicss-tools/comfyui/models/
├── checkpoints/             # 主模型
│   ├── z_image_turbo_fp8.safetensors
│   └── sdxl_base_1.0.safetensors
├── diffusion_models/        # 视频/特殊模型
│   └── wan2.1_i2v_14b.safetensors
├── vae/
│   └── sdxl_vae.safetensors
├── loras/
│   └── paper_style_xl.safetensors
├── clip/                    # 文本编码器
│   └── clip_l_sdxl.safetensors
├── controlnet/
├── ipadapter/
├── ultralytics/             # bbox/seg 模型（Impact Pack 用）
│   └── bbox/
│       └── sam2.1_hiera_base_plus.pt
├── sam2/                    # SAM2 模型
│   └── sam2.1_hiera_large.pt
├── depthanything/           # 深度估计
│   └── depth_anything_v2_vitl.pth
├── grounding-dino/          # 目标检测
│   └── groundingdino_swit_ogc.pth
└── lama/                    # 修复模型（需手动下载）
```

## 1.3 手动下载模型（用 hf-mirror 镜像）

```bash
cd ~/projects/aicss-tools/comfyui
mkdir -p models/{checkpoints,vae,loras,clip,controlnet,ipadapter,ultralytics/bbox,sam2,depthanything,grounding-dino}

export HF_ENDPOINT=https://hf-mirror.com

# Z-Image-Turbo（首选图像模型，约 5GB fp8）
huggingface-cli download Tongyi-MAI/Z-Image-Turbo \
    --local-dir models/checkpoints/ \
    --include "z_image_turbo_fp8.safetensors" \
    --resume-download

# SDXL Base 1.0（备用）
huggingface-cli download stabilityai/stable-diffusion-xl-base-1.0 \
    --local-dir models/checkpoints/ \
    --include "sd_xl_base_1.0.safetensors" \
    --resume-download

# SDXL VAE
huggingface-cli download madebyollin/sdxl-vae-fp16-fix \
    --local-dir models/vae/ \
    --resume-download

# Depth-Anything-V2-Large
huggingface-cli download depth-anything/Depth-Anything-V2-Large-hf \
    --local-dir models/depthanything/ \
    --resume-download

# SAM2.1 Hiera Large（约 900MB）
huggingface-cli download facebook/sam2.1-hiera-large \
    --local-dir models/sam2/ \
    --include "sam2.1_hiera_large.pt" \
    --resume-download

# Grounding-DINO Base
huggingface-cli download IDEA-Research/grounding-dino-base \
    --local-dir models/grounding-dino/ \
    --include "pytorch_model.bin" "*.json" "*.txt" \
    --resume-download

# LaMa 修复（可选，单独 repo）
pip install simple-lama-inpainting
# 会在 ~/.cache/torch/hub/checkpoints/ 自动下载 big-lama.pt
```

### Wan2.1 视频模型（可选，14GB+）

```bash
# 下载 Wan2.1-I2V-14B-480P（约 28GB fp16，fp8 约 14GB）
# 注意：需要高端显卡（建议 24GB+ 显存），4060Ti 16GB 可能 OOM
huggingface-cli download Wan-AI/Wan2.1-I2V-14B-480P \
    --local-dir models/diffusion_models/ \
    --include "diffusion_pytorch_model*.safetensors" \
    --resume-download

# 或 Wan2.1-I2V-1.3B（轻量版，约 2.5GB，推荐 4060Ti 使用）
huggingface-cli download Wan-AI/Wan2.1-I2V-1.3B-480P \
    --local-dir models/diffusion_models/ \
    --include "diffusion_pytorch_model*.safetensors" \
    --resume-download
```

## 1.4 启动 ComfyUI（正式）

```bash
cd ~/projects/aicss-tools/comfyui
source venv/bin/activate

# 启动参数说明：
# --listen 0.0.0.0       允许局域网/Win 访问
# --port 8188            端口
# --disable-auto-launch  不自动打开浏览器
# --preview-method auto  预览方式（auto/local）
# --fp8_e4m3fn-unet     Z-Image 推荐 fp8 精度（省显存）
# --force-fp16           SDXL 用 fp16
# --lowvram              显存 < 12GB 时开启
# --gpu-only             完全用 GPU（禁用 CPU fallback）

python main.py \
    --listen 0.0.0.0 \
    --port 8188 \
    --disable-auto-launch \
    --preview-method auto

# 后台启动（推荐）
nohup python main.py \
    --listen 0.0.0.0 \
    --port 8188 \
    --disable-auto-launch \
    --preview-method auto \
    > /tmp/comfyui.log 2>&1 &

echo "ComfyUI PID: $!"
tail -f /tmp/comfyui.log
```

**验证**：浏览器访问 `http://127.0.0.1:8188` 应看到 ComfyUI 界面。

## 1.5 核心 ComfyUI 工作流（手动制作 + 完整提示词）

### 工作流 1：`txt2img_basic.json`（基础文生图）

**用途**：单张图像生成，角色概念图、场景灵感图。

**手动拖拽节点步骤**：

1. 双击空白处搜索 `Load Checkpoint` → 选 `z_image_turbo_fp8.safetensors`
2. 双击搜索 `CLIP Text Encode (Prompt)` → 添加 2 个（一个 positive，一个 negative）
3. 双击搜索 `Empty Latent Image` → 设 width=1024, height=1024, batch_size=1
4. 双击搜索 `KSampler` → 设 steps=20, cfg=1.0（Z-Image-Turbo 蒸馏模型 cfg=1）, sampler=euler_ancestral, scheduler=simple, denoise=1.0
5. 双击搜索 `VAE Decode`
6. 双击搜索 `Save Image` → 设 prefix="aicss_txt2img"

**完整节点 JSON（可保存为 `txt2img_basic.json`）**：

```json
{
  "3": {
    "class_type": "KSampler",
    "inputs": {
      "model": ["1", 0],
      "positive": ["6", 0],
      "negative": ["7", 0],
      "latent_image": ["5", 0],
      "seed": 42,
      "steps": 20,
      "cfg": 1.0,
      "sampler_name": "euler_ancestral",
      "scheduler": "simple",
      "denoise": 1.0
    }
  },
  "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "z_image_turbo_fp8.safetensors"}},
  "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
  "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "（见下方提示词）", "clip": ["1", 1]}},
  "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "low quality, blurry, distorted", "clip": ["1", 1]}},
  "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["1", 2]}},
  "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "aicss_txt2img", "images": ["8", 0]}}
}
```

**配套提示词模板**（写入节点的 `text` 字段）：

```
positive prompt (中文场景 → 翻译为英文 prompt):

【角色概念图】
{aesthetic}, {gender} character, {age}, {ethnicity}, 
{body_type}, {hair_color} hair, {hair_style}, {eye_color} eyes,
wearing {clothing_top}, {clothing_bottom}, {accessories},
{facial_expression} expression,
standing pose, full body shot, centered,
background: {background_style},
lighting: {lighting_type},
paper craft style, layered paper art, hand-cut paper silhouette,
flat colors with subtle gradients, white paper edges visible,
by {artist_reference}, highly detailed, 8k,

参考:
- cinematic still, concept art
- delicate paper layering, slight 3D depth
- white or off-white background with subtle texture
```

```
negative prompt (通用):
low quality, worst quality, blurry, distorted, disfigured,
extra limbs, extra fingers, mutated hands,
bad anatomy, bad proportions, cropped, out of frame,
text, watermark, signature, username,
jpeg artifacts, pixelated, grainy,
3d render, photorealistic, photo,
cluttered background, multiple characters,
```

### 工作流 2：`character_three_view.json`（角色三视图）

**用途**：生成同一角色的 front / side / back 三视图。

**结构**：
- 1 个 CheckpointLoader（Z-Image-Turbo）
- 3 个 CLIPTextEncode（每个角度不同 prompt）
- 3 个 KSampler（独立 seed）
- 3 个 VAEDecode + 3 个 SaveImage
- 用 IPAdapter（可选）保证角色一致性

**关键提示词（front / side / back 分别写）**：

```
【FRONT 正面】
character turnaround front view, face directly facing camera,
eyes visible, full face features visible,
{full character description},
neutral standing pose, T-pose or relaxed standing,
front lighting, flat lighting, orthographic perspective,
paper craft style, hand-cut paper,
white background, full body, head to toe visible,

【SIDE 侧面】
character turnaround side view, profile view from left,
face in profile, only one eye visible,
{full character description},
neutral standing pose, arms at sides,
side lighting, orthographic perspective,
paper craft style, hand-cut paper,
white background, full body, head to toe visible,

【BACK 背面】
character turnaround back view, character facing away from camera,
back of head, back of body visible, no face features shown,
{full character description},
neutral standing pose, arms at sides,
back lighting, orthographic perspective,
paper craft style, hand-cut paper,
white background, full body, head to toe visible,
```

**批量生成的 Python 提交脚本**（Dify 调用时使用）：

```python
# backend/app/services/comfyui_client.py
import json
import requests
import time
from pathlib import Path

class ComfyUIClient:
    def __init__(self, base_url: str = "http://localhost:8188"):
        self.base_url = base_url

    def submit_workflow(self, workflow_json: dict, client_id: str) -> str:
        """提交工作流，返回 prompt_id。"""
        resp = requests.post(
            f"{self.base_url}/prompt",
            json={"prompt": workflow_json, "client_id": client_id},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["prompt_id"]

    def wait_for_result(self, prompt_id: str, timeout: int = 600) -> dict:
        """轮询直到工作流完成。"""
        start = time.time()
        while time.time() - start < timeout:
            hist = requests.get(
                f"{self.base_url}/history/{prompt_id}", timeout=10
            ).json()
            if prompt_id in hist:
                return hist[prompt_id]
            time.sleep(2)
        raise TimeoutError(f"Workflow {prompt_id} timed out after {timeout}s")

    def build_character_three_view(
        self,
        visual_prompt: str,
        seed: int = 42,
    ) -> dict:
        """动态构建三视图工作流（每张共享 visual_prompt）。"""
        # 读取工作流模板
        template = json.load(open("workflows/character_three_view.json"))

        # 替换 prompt 和 seed
        template["6"]["inputs"]["text"] = (
            f"character turnaround front view, {visual_prompt}, "
            "paper craft style, white background"
        )
        template["7"]["inputs"]["text"] = (
            f"character turnaround side view, {visual_prompt}, "
            "paper craft style, white background"
        )
        template["8"]["inputs"]["text"] = (
            f"character turnaround back view, {visual_prompt}, "
            "paper craft style, white background"
        )
        template["10"]["inputs"]["seed"] = seed
        template["11"]["inputs"]["seed"] = seed + 1
        template["12"]["inputs"]["seed"] = seed + 2
        return template
```

### 工作流 3：`depth_anything_v2.json`（深度估计）

**用途**：从 RGB 图像生成深度图，用于 2.5D 视差。

**节点结构**：
- `LoadImage` → 输入图像
- `DepthAnything_V2` 节点（custom node）
- `VAEEncode`（可选，把深度图存为 latent）
- `SaveImage` → 输出深度图

**完整 JSON**：

```json
{
  "1": {"class_type": "LoadImage", "inputs": {"image": "input.png"}},
  "2": {
    "class_type": "DepthAnything_V2",
    "inputs": {
      "image": ["1", 0],
      "model": "depth_anything_v2_vitl.pth",
      "normalization": "standard"
    }
  },
  "3": {"class_type": "SaveImage", "inputs": {"filename_prefix": "depth", "images": ["2", 0]}}
}
```

**前端调用**：

```bash
# 提交
curl -X POST http://localhost:8188/prompt \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": <上面JSON>,
    "client_id": "test-client"
  }'
```

### 工作流 4：`lama_inpaint.json`（图像修复）

**用途**：用 LaMa 修复蒙版区域（物体移除、水印擦除）。

**节点结构**：
- `LoadImage`（主图像）
- `LoadImage`（mask，单通道）
- `LaMaInpaint` 节点

**完整 JSON**：

```json
{
  "1": {"class_type": "LoadImage", "inputs": {"image": "scene_with_occlusion.png"}},
  "2": {"class_type": "LoadImage", "inputs": {"image": "mask.png"}},
  "3": {
    "class_type": "LaMaInpaint",
    "inputs": {
      "image": ["1", 0],
      "mask": ["2", 0]
    }
  },
  "4": {"class_type": "SaveImage", "inputs": {"filename_prefix": "inpainted", "images": ["3", 0]}}
}
```

### 工作流 5：`wan2.1_i2v.json`（图生视频）

**用途**：从关键帧生成 5 秒短镜头。

**节点结构**（WanVideoWrapper）：

```json
{
  "1": {"class_type": "WanVideoLoader", "inputs": {"model": "wan2.1_i2v_14b_fp8.safetensors"}},
  "2": {"class_type": "LoadImage", "inputs": {"image": "keyframe.png"}},
  "3": {
    "class_type": "WanVideoSampler",
    "inputs": {
      "model": ["1", 0],
      "positive": ["4", 0],
      "negative": ["5", 0],
      "latent": ["6", 0],
      "steps": 30,
      "cfg": 5.0,
      "sampler": "uni_pc"
    }
  },
  "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "（见下方）", "clip": ["1", 1]}},
  "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "（见下方）", "clip": ["1", 1]}},
  "6": {
    "class_type": "WanVideoImageToVideo",
    "inputs": {
      "image": ["2", 0],
      "num_frames": 81,
      "fps": 16,
      "resolution": "480p"
    }
  },
  "7": {
    "class_type": "VHS_VideoCombine",
    "inputs": {
      "frames": ["3", 0],
      "frame_rate": 16,
      "format": "video/h264-mp4",
      "save_output": true,
      "filename_prefix": "aicss_video"
    }
  }
}
```

**配套提示词**：

```
positive:
cinematic shot, smooth camera movement, {camera_motion} slowly,
{subject} in {location}, {atmosphere}, {time_of_day},
{motion_description}, 16fps, coherent motion, sharp focus,
film grain, cinematic color grading, anamorphic lens,

negative:
blurry, jittery, fast motion, distorted, flickering,
frame artifacts, low quality, worst quality,
morphing, melting, extra limbs, ugly,
```

---

# 第二部分：Dify 手动搭建

## 2.1 安装 Dify（Docker 方式，最简单）

Dify 必须用 Docker（依赖 PostgreSQL、Redis 等），不能纯手动装。

```bash
cd ~/projects/aicss-tools/dify

# 1. 克隆
git clone https://github.com/langgenius/dify.git .
# 或指定版本
# git clone --branch 1.4.0 https://github.com/langgenius/dify.git .

# 2. 进入 docker 目录
cd docker

# 3. 复制环境配置
cp .env.example .env

# 4. 编辑 .env（关键项）
nano .env
```

**关键配置项**（`.env`）：

```bash
# 镜像版本
COMPOSE_PROFILES=
DIFY_VERSION=1.4.0

# 镜像仓库镜像（国内）
DOCKER_REGISTRY=docker.mirrors.ustc.edu.cn

# 暴露端口
EXPOSE_NGINX_PORT=3000
EXPOSE_NGINX_SSL_PORT=443

# 超级管理员（首次启动会用到）
INIT_EMAIL=admin@aicss.local
INIT_PASSWORD=AICSS@dify2026
INIT_NAME=刘淇

# 数据库密码
DB_PASSWORD=dify123

# Secret Key（生产环境必须改）
SECRET_KEY=dify-aicss-secret-change-me-in-production-please

# 持久化路径
APP_API_URL=http://localhost:8001
CONSOLE_API_URL=http://localhost:8001
APP_WEB_URL=http://localhost:3000

# LLM 提供商（这里以 DashScope 为例）
# Dify 会自动检测你在 Web UI 添加的 Provider
```

### 启动 Dify

```bash
cd ~/projects/aicss-tools/dify/docker

# 首次启动
docker compose up -d

# 查看状态
docker compose ps
# 应该看到 api / worker / web / db / redis / nginx 等

# 等待初始化完成（首次约 2-3 分钟）
docker compose logs -f api | grep "Application startup complete"

# 健康检查
curl http://localhost:3000
# 应返回 HTML
```

**Web UI 访问**：Windows 浏览器打开 `http://127.0.0.1:3000`，用上面配置的账号登录。

## 2.2 配置 LLM Provider

进入 Dify Web UI → `设置` → `模型供应商`：

### 方式 A：阿里云 DashScope（推荐，国内快）

1. 点击 `通义千问` 卡片 → `添加模型`
2. 填入你的 DashScope API Key（[dashscope.aliyun.com](https://dashscope.aliyun.com) 申请）
3. 模型选择：
   - `qwen-max` （最强）
   - `qwen-plus` （性价比）
   - `qwen-turbo` （最快）
4. 保存

### 方式 B：本地 Ollama（免费/隐私）

如果已装了 Ollama（`~/projects/aicss-tools/ollama` 容器）：

1. 点击 `Ollama` 卡片 → 填入：
   - API endpoint：`http://aicss-ollama:11434`（容器内）或 `http://host.docker.internal:11434`（host 网络）
   - 模型：先在 Ollama 拉取模型
     ```bash
     ollama pull qwen2.5:7b
     ollama pull llama3.2:3b
     ```
   - 然后在 Dify 添加 `qwen2.5:7b`

### 方式 C：OpenAI 兼容 API（通用）

如果用第三方代理（如 OpenRouter / Crazyrouter / 自建）：
1. 选择 `OpenAI-API-compatible`
2. 填入 base_url 和 api_key

### 验证 LLM

进入 Dify Web UI → `工作室` → `创建应用` → `聊天助手`：
- 选刚才加的 qwen 模型
- 输入"你好"
- 看是否正常回复

## 2.3 配置 ComfyUI 作为外部工具

Dify 的 `工具` 节点可以直接调用 HTTP API，把 ComfyUI 接入：

1. 进入 `工作室` → `工具` → `创建自定义工具`
2. 选择 `OpenAPI/Swagger` 或 `HTTP 协议`
3. 配置（用向导更直观）：

**ComfyUI 提交任务工具**：

```yaml
工具名称: comfyui_submit
工具描述: 提交 ComfyUI 工作流并返回 prompt_id
鉴权方式: 无
请求方法: POST
请求 URL: http://host.docker.internal:8188/prompt
请求头:
  Content-Type: application/json
请求体 (JSON):
{
  "prompt": {{workflow_json}},
  "client_id": "{{client_id}}"
}
响应体解析:
  - prompt_id: $.prompt_id
```

> ⚠️ 注意：Dify 容器访问宿主 ComfyUI 用 `http://host.docker.internal:8188`，Linux 上需要 Docker Desktop 或加 `--add-host=host.docker.internal:host-gateway`。

**ComfyUI 轮询工具**：

```yaml
工具名称: comfyui_poll
请求方法: GET
请求 URL: http://host.docker.internal:8188/history/{{prompt_id}}
响应体解析:
  - status: 存在与否
  - outputs: $.outputs
```

**ComfyUI 下载文件工具**（用 HTTP 请求节点而非工具）：

直接在 Workflow 节点里用 `HTTP 请求` 节点：
- URL: `http://host.docker.internal:8188/view?filename={{filename}}&type=output`
- 响应类型：binary

## 2.4 Dify 知识库（RAG）接入

知识库 = 让 LLM 能引用你上传的文档，提升剧本/分镜质量。

### 2.4.1 上传文档

进入 `知识库` → `创建知识库` → 命名（如 "AICSS剧本知识库"）：

**支持的文件格式**：
- 文本：`txt`, `md`, `pdf`, `docx`, `pptx`, `xlsx`, `epub`
- 网页：URL 抓取
- Notion 同步（可选）

**典型上传文件清单**（建议）：

```
docs/knowledge_base/
├── 剧本格式规范.md            # 内部剧本写作标准
├── 分镜设计原则.pdf           # 摄影/分镜参考
├── 角色设计模板.pdf           # 角色一致性参考
├── 视觉风格指南.md            # AICSS 项目的视觉风格
├── 经典剧本范例.txt           # 5-10 部优秀剧本节选
├── 中国/欧美/日韩文化背景.md  # 文化参考
├── 场景设计词典.txt           # 100+ 场景描述模板
└── 已完成项目剧本/            # 历史项目的剧本（提供示例）
    ├── 项目A_校园剧本.md
    └── 项目B_奇幻剧本.md
```

### 2.4.2 配置检索模式

知识库创建时，**关键配置**：

| 配置项 | 推荐值 | 说明 |
|--------|--------|------|
| 索引模式 | `高质量` | Embedding + 关键词混合检索 |
| Embedding 模型 | `text-embedding-v3` (DashScope) 或 `bge-large-zh-v1.5` (本地) | 中文选 v3，英文选 OpenAI ada-002 |
| 分段最大长度 | 800 tokens | 中文剧本建议 500-1000 |
| 分段重叠 | 50 tokens | 避免边界切断语义 |
| 检索方式 | `混合检索` | 向量 + 全文 |
| Top K | 5-10 | 太多会超 token |
| Score 阈值 | 0.5 | 太低引入噪声 |

### 2.4.3 在工作流中使用知识库

工作流里添加 `知识检索` 节点：

```yaml
- id: knowledge_retrieval
  type: knowledge-retrieval
  data:
    title: 检索剧本规范
    knowledge_base_id: "aicss-script-style-kb"
    query: "{{#start.raw_text#}}"
    retrieval_config:
      top_k: 5
      score_threshold: 0.5
      reranking_enable: true
      reranking_model: "gte-rerank"
```

### 2.4.4 知识库效果提升的关键提示词模板

在工作流的 LLM 节点 system prompt 里加入：

```
你是 AICSS 剧本解析专家。请严格遵守以下规则：

## 输出风格
- 严格 JSON 格式输出，不含任何额外说明文字
- 所有字段必须填写，无值时填 null 或 []
- ID 必须符合正则 `^[a-z][a-z0-9-]*$`

## 检索上下文
以下是来自知识库的参考文档（可能相关）：
{{#knowledge_retrieval.result#}}

如果参考文档中有相关规范/模板/范例，优先遵循。
不要提及"知识库"或"参考文档"等元信息，仿佛这些就是你的专业知识。
```

---

## 2.5 Dify 完整工作流（含知识库）

### 工作流：`script_parse_with_kb.yml`

```yaml
version: 0.6.0
name: script_parse_with_kb
description: 原始剧本 → 标准化 → 结构化 JSON（含知识库增强）
nodes:

  - id: start
    type: start
    data:
      title: Start
      variables:
        - { name: raw_text, type: paragraph, required: true }
        - { name: language, type: select, options: [chinese, english, japanese] }

  - id: kb_retrieval
    type: knowledge-retrieval
    data:
      title: 检索剧本规范知识库
      knowledge_base_id: "aicss-script-style-kb"
      query: "{{#start.raw_text#}}"
      retrieval_config:
        top_k: 5
        score_threshold: 0.5
        reranking_enable: true
        reranking_model: "gte-rerank"

  - id: llm_normalize
    type: llm
    data:
      title: Step 1: 标准化剧本
      model: qwen-max
      prompt_template:
        system: |
          你是专业剧本编辑。请将用户输入的原始剧本重写为标准格式。

          ## 标准剧本格式要求
          1. 场景标记：`[场景 N - 地点 - 时间/氛围]`
          2. 角色台词：`角色名：`台词内容``
          3. 旁白/动作：直接描述，无前缀
          4. 每行不超过 100 字
          5. 段落之间空一行

          ## 参考（来自知识库）
          {{#kb_retrieval.result#}}

        user: |
          请将以下剧本重写为标准格式：

          {{#start.raw_text#}}
      output:
        - { variable: normalized_text, type: string }

  - id: llm_extract_metadata
    type: llm
    data:
      title: Step 2: 提取元数据
      model: qwen-max
      prompt_template:
        system: |
          你是剧本元数据提取专家。请从剧本中提取以下信息并返回严格 JSON：

          ```json
          {
            "title": "剧本标题",
            "genre": "类型（剧情/喜剧/科幻/奇幻/恐怖/爱情/动作）",
            "logline": "一句话故事概要（不超过 50 字）",
            "themes": ["主题1", "主题2"],
            "target_audience": "目标观众",
            "estimated_duration_minutes": 90,
            "tone": "整体基调（轻松/严肃/紧张/温馨等）"
          }
          ```

          不要添加 JSON 外的任何文字。
        user: "剧本：\n{{#llm_normalize.normalized_text#}}"
      output:
        - { variable: metadata, type: object }

  - id: llm_extract_characters
    type: llm
    data:
      title: Step 3a: 提取角色
      model: qwen-max
      prompt_template:
        system: |
          你是剧本角色提取专家。请从剧本中识别所有**真正出场的角色**，
          并以 JSON 数组返回。

          ## 严格区分
          - ✅ 真实角色：有名字、有台词或动作
          - ❌ 伪角色：景别描述（如"特写"、"中景"）、旁白指示、群体名词（如"学生们"）

          ## 伪角色黑名单（必须排除）
          特写, 中景, 全景, 远景, 近景, 大特写, 中特写, 俯拍, 仰拍
          旁白, 她, 他, 他们, 她们, 学生们, 观众们
          镜头, 画面, 场景, 字幕

          ## 输出格式
          ```json
          [
            {
              "id": "lin-zhixia",
              "name": "林知夏",
              "gender": "female",
              "role_type": "主角/配角/反派/群众",
              "first_appearance_scene": "scene-1",
              "estimated_screen_time_ratio": 0.4,
              "personality_traits": ["内向", "坚韧", "敏感"],
              "visual_signature": "标志性视觉特征（黑长直、左撇子、戴眼镜）"
            }
          ]
          ```

          ID 格式：`^[a-z][a-z0-9-]*$`，用角色英文拼音或简短英文名。
        user: "剧本：\n{{#llm_normalize.normalized_text#}}"
      output:
        - { variable: characters, type: array[object] }

  - id: llm_extract_scenes
    type: llm
    data:
      title: Step 3b: 提取场景
      model: qwen-max
      prompt_template:
        system: |
          你是剧本场景提取专家。请从剧本中提取所有场景信息，并以 JSON 数组返回。

          ## 输出格式
          ```json
          [
            {
              "id": "scene-1",
              "location": "高中教室",
              "time_of_day": "Morning|Day|Afternoon|Evening|Night|Dawn",
              "atmosphere": "紧张/温馨/压抑/欢快/神秘等",
              "weather": "晴/雨/雪/阴等",
              "season": "春/夏/秋/冬",
              "estimated_duration_seconds": 120,
              "characters_present": ["lin-zhixia", "zhang-san"],
              "key_actions": ["老师提问", "学生讨论", "林知夏沉默"],
              "emotional_arc": "紧张→释然",
              "visual_motifs": ["纸飞机", "黑板", "阳光"]
            }
          ]
          ```

          ID 格式：scene-1, scene-2, ...
        user: "剧本：\n{{#llm_normalize.normalized_text#}}"
      output:
        - { variable: scenes, type: array[object] }

  - id: llm_extract_shots
    type: llm
    data:
      title: Step 3c: 提取段落/镜头
      model: qwen-max
      prompt_template:
        system: |
          你是剧本段落提取专家。请将剧本分解为**段落（beats）**，每个 beat 是一个完整的情绪/动作单元。

          ## Beat 定义
          - 一个 beat 通常对应 1 个或几个连续镜头
          - 切换场景 = 新 beat
          - 时间跳跃 = 新 beat
          - 情绪/地点显著变化 = 新 beat

          ## 输出格式
          ```json
          [
            {
              "id": "beat-1",
              "scene_id": "scene-1",
              "characters_involved": ["lin-zhixia", "zhang-san"],
              "content_summary": "林知夏在教室听到老师提问后的内心独白",
              "emotional_state": "紧张/焦虑",
              "narrative_function": "建立人物性格 / 推动情节 / 揭示背景 / 营造氛围",
              "estimated_shots": 3
            }
          ]
          ```
        user: "剧本：\n{{#llm_normalize.normalized_text#}}"
      output:
        - { variable: beats, type: array[object] }

  - id: code_merge
    type: code
    data:
      title: Step 4: 合并 + 校验
      variables:
        - { name: meta, value_selector: [llm_extract_metadata, metadata] }
        - { name: chars, value_selector: [llm_extract_characters, characters] }
        - { name: scenes, value_selector: [llm_extract_scenes, scenes] }
        - { name: beats, value_selector: [llm_extract_shots, beats] }
      code_language: python3
      code: |
        import re
        import uuid

        # 1. 校验 + 清洗角色
        BLACKLIST = {"特写", "中景", "全景", "旁白", "她", "他", "他们"}
        cleaned_chars = []
        seen_ids = set()
        for c in (chars or []):
            if not isinstance(c, dict):
                continue
            name = c.get("name", "").strip()
            if name in BLACKLIST or len(name) < 2:
                continue
            cid = c.get("id") or re.sub(r'[^a-z0-9-]', '-', name.lower())
            if cid in seen_ids:
                cid = f"{cid}-{uuid.uuid4().hex[:4]}"
            seen_ids.add(cid)
            c["id"] = cid
            cleaned_chars.append(c)

        # 2. 校验场景 ID
        for s in (scenes or []):
            sid = s.get("id") or f"scene-{uuid.uuid4().hex[:4]}"
            s["id"] = sid

        # 3. 校验 beats
        for b in (beats or []):
            bid = b.get("id") or f"beat-{uuid.uuid4().hex[:4]}"
            b["id"] = bid

        return {
            "metadata": meta,
            "characters": cleaned_chars,
            "scenes": scenes or [],
            "beats": beats or [],
            "stats": {
                "character_count": len(cleaned_chars),
                "scene_count": len(scenes or []),
                "beat_count": len(beats or []),
            }
        }
      outputs:
        merged: { type: object, children: null }

  - id: http_persist
    type: http-request
    data:
      title: Step 5: 持久化到 FastAPI
      method: POST
      url: "http://host.docker.internal:8000/api/aicss/v2/scripts/save"
      headers:
        Content-Type: application/json
      body:
        type: json
        data:
          project_id: "{{#env.AICSS_PROJECT_ID#}}"
          script_data: "{{#code_merge.merged#}}"

  - id: end
    type: end
    data:
      title: End
      outputs:
        - { variable: script_data, value_selector: [code_merge, merged] }
        - { variable: stats, value_selector: [code_merge, merged, stats] }
```

### 工作流：`shot_generation.yml`（分镜生成，含知识库）

```yaml
nodes:
  - id: start
    type: start
    data:
      variables:
        - { name: project_id, required: true }
        - { name: scene_id, required: true }

  - id: kb_retrieval_style
    type: knowledge-retrieval
    data:
      title: 检索分镜风格指南
      knowledge_base_id: "aicss-shot-style-kb"
      query: "分镜景别 运镜 视觉风格"
      retrieval_config:
        top_k: 5
        reranking_enable: true

  - id: kb_retrieval_scenes
    type: knowledge-retrieval
    data:
      title: 检索场景模板
      knowledge_base_id: "aicss-scene-templates-kb"
      query: "{{#start.scene_id#}}"

  - id: llm_generate_shots
    type: llm
    data:
      title: 生成分镜
      model: qwen-max
      prompt_template:
        system: |
          你是专业分镜师。请为给定的剧本场景生成完整的分镜表。

          ## 严格遵循以下枚举值
          shot_size ∈ {
            "Extreme Wide Shot", "Wide Shot", "Full Shot", "Medium Wide Shot",
            "Medium Shot", "Medium Close-up", "Close-up", "Extreme Close-up"
          }

          camera_movement ∈ {
            "Static", "Pan Left", "Pan Right", "Tilt Up", "Tilt Down",
            "Dolly In", "Dolly Out", "Dolly Left", "Dolly Right",
            "Truck Left", "Truck Right", "Pedestal Up", "Pedestal Down",
            "Zoom In", "Zoom Out", "Roll Left", "Roll Right",
            "Handheld", "Steadicam"
          }

          camera_angle ∈ {"Eye Level", "Low Angle", "High Angle", "Dutch Angle", "Over the Shoulder", "Bird's Eye View"}

          ## 输出格式（严格 JSON）
          ```json
          [
            {
              "shot_number": 1,
              "shot_size": "Extreme Close-up",
              "camera_movement": "Static",
              "camera_angle": "Eye Level",
              "duration_seconds": 2.5,
              "characters_in_frame": ["lin-zhixia"],
              "action": "林知夏眨眼睛，眼眶微红",
              "dialogue": "（无）",
              "sound_effects": ["时钟滴答", "心跳声"],
              "emotional_beat": "紧张 → 期待",
              "visual_focus": "林知夏的瞳孔倒影",
              "visual_prompt": "extreme close-up of girl's eye, iris reflects classroom, soft window light, paper craft style"
            }
          ]
          ```

          ## 知识库参考
          分镜风格: {{#kb_retrieval_style.result#}}
          场景模板: {{#kb_retrieval_scenes.result#}}

          要求：
          - 同一场景分 5-8 个镜头
          - 镜头时长总和接近场景估算时长
          - 起始镜头建议从远景/中景建立空间
          - 关键情绪点用特写强化
          - 运镜节奏要有变化（不能连续 3 个 Static）
        user: |
          场景 ID：{{#start.scene_id#}}
          项目 ID：{{#start.project_id#}}
          请生成分镜 JSON。
      output:
        - { variable: shots, type: array[object] }

  - id: code_validate
    type: code
    data:
      variables:
        - { name: shots, value_selector: [llm_generate_shots, shots] }
      code_language: python3
      code: |
        SIZE_ENUM = {"Extreme Wide Shot", "Wide Shot", "Full Shot", "Medium Wide Shot",
                     "Medium Shot", "Medium Close-up", "Close-up", "Extreme Close-up"}
        MOVE_ENUM = {"Static", "Pan Left", "Pan Right", "Tilt Up", "Tilt Down",
                     "Dolly In", "Dolly Out", "Dolly Left", "Dolly Right",
                     "Truck Left", "Truck Right", "Pedestal Up", "Pedestal Down",
                     "Zoom In", "Zoom Out", "Roll Left", "Roll Right",
                     "Handheld", "Steadicam"}
        ANGLE_ENUM = {"Eye Level", "Low Angle", "High Angle", "Dutch Angle",
                      "Over the Shoulder", "Bird's Eye View"}

        validated = []
        for idx, shot in enumerate(shots or []):
            shot["shot_number"] = idx + 1
            shot["shot_size"] = shot.get("shot_size") if shot.get("shot_size") in SIZE_ENUM else "Medium Shot"
            shot["camera_movement"] = shot.get("camera_movement") if shot.get("camera_movement") in MOVE_ENUM else "Static"
            shot["camera_angle"] = shot.get("camera_angle") if shot.get("camera_angle") in ANGLE_ENUM else "Eye Level"
            shot["duration_seconds"] = max(0.5, min(30.0, float(shot.get("duration_seconds") or 3.0)))
            validated.append(shot)
        return {"shots": validated, "count": len(validated)}
      outputs:
        result: { type: object, children: null }

  - id: http_persist
    type: http-request
    data:
      title: 保存到 FastAPI
      method: POST
      url: "http://host.docker.internal:8000/api/aicss/v2/shots/save"
      body:
        type: json
        data:
          project_id: "{{#start.project_id#}}"
          scene_id: "{{#start.scene_id#}}"
          shots: "{{#code_validate.result.shots#}}"

  - id: end
    type: end
```

### 工作流：`character_asset.yml`（Dify → ComfyUI）

```yaml
nodes:
  - id: start
    type: start
    data:
      variables:
        - { name: character_id, required: true }
        - { name: project_id, required: true }

  - id: kb_retrieval
    type: knowledge-retrieval
    data:
      title: 检索角色视觉风格指南
      knowledge_base_id: "aicss-visual-style-kb"
      query: "角色 visual prompt 风格 标签 范例"

  - id: http_get_character
    type: http-request
    data:
      title: 获取角色信息
      method: GET
      url: "http://host.docker.internal:8000/api/aicss/v2/characters/{{#start.character_id#}}"

  - id: llm_build_prompt
    type: llm
    data:
      title: 生成 visual prompt
      model: qwen-max
      prompt_template:
        system: |
          你是 AI 图像 prompt 工程师。请根据角色描述生成英文 visual prompt。
          要求：
          - 50-80 个 token
          - 包含：人物特征 + 服装 + 姿态 + 背景 + 风格
          - 风格关键词：paper craft, hand-cut paper, layered paper art, white edges
          - 视角：character turnaround front view（用于三视图）

          ## 风格参考（来自知识库）
          {{#kb_retrieval.result#}}

          只输出 prompt 字符串本身，不要任何其他文字。
        user: |
          角色：{{#http_get_character.response.name#}}
          性别：{{#http_get_character.response.gender#}}
          性格：{{#http_get_character.response.personality_traits#}}
          视觉特征：{{#http_get_character.response.visual_signature#}}
          剧本上下文：{{#http_get_character.response.scene_context#}}
      output:
        - { variable: visual_prompt, type: string }

  - id: code_build_workflow
    type: code
    data:
      variables:
        - { name: prompt, value_selector: [llm_build_prompt, visual_prompt] }
        - { name: char_id, value_selector: [start, character_id] }
      code_language: python3
      code: |
        import json, uuid
        template = json.load(open("/app/workflow_export/character_three_view.json"))
        template["6"]["inputs"]["text"] = f"character turnaround front view, {prompt}, paper craft style, white background"
        template["7"]["inputs"]["text"] = f"character turnaround side view, {prompt}, paper craft style, white background"
        template["8"]["inputs"]["text"] = f"character turnaround back view, {prompt}, paper craft style, white background"
        seed = abs(hash(char_id)) % (10**8)
        template["10"]["inputs"]["seed"] = seed
        template["11"]["inputs"]["seed"] = seed + 1
        template["12"]["inputs"]["seed"] = seed + 2
        return {
          "workflow_json": template,
          "client_id": f"aicss-{uuid.uuid4().hex[:8]}"
        }
      outputs:
        payload: { type: object, children: null }

  - id: http_submit
    type: http-request
    data:
      title: 提交到 ComfyUI
      method: POST
      url: "http://host.docker.internal:8188/prompt"
      body:
        type: json
        data:
          prompt: "{{#code_build_workflow.payload.workflow_json#}}"
          client_id: "{{#code_build_workflow.payload.client_id#}}"

  - id: http_poll
    type: http-request
    data:
      title: 轮询结果
      method: GET
      url: "http://host.docker.internal:8188/history/{{#http_submit.response.prompt_id#}}"
      retry:
        enabled: true
        max_retries: 60
        retry_interval_ms: 5000

  - id: http_download_front
    type: http-request
    data:
      title: 下载正面图
      method: GET
      url: "http://host.docker.internal:8188/view?filename={{#http_poll.response.outputs.10.images.0.filename#}}&type=output"

  - id: http_download_side
    type: http-request
    data:
      title: 下载侧面图
      method: GET
      url: "http://host.docker.internal:8188/view?filename={{#http_poll.response.outputs.11.images.0.filename#}}&type=output"

  - id: http_download_back
    type: http-request
    data:
      title: 下载背面图
      method: GET
      url: "http://host.docker.internal:8188/view?filename={{#http_poll.response.outputs.12.images.0.filename#}}&type=output"

  - id: http_persist
    type: http-request
    data:
      title: 保存到 FastAPI
      method: POST
      url: "http://host.docker.internal:8000/api/aicss/v2/characters/save-three-view"
      body:
        type: multipart
        data:
          project_id: "{{#start.project_id#}}"
          character_id: "{{#start.character_id#}}"
          front_b64: "{{#http_download_front.response_body#}}"
          side_b64: "{{#http_download_side.response_body#}}"
          back_b64: "{{#http_download_back.response_body#}}"

  - id: end
    type: end
```

---

## 2.6 知识库内容建议

### 知识库 1：`aicss-script-style-kb`（剧本规范）

**初始上传文件**：

```markdown
# AICSS 剧本格式规范（示例）

## 1. 场景标记
格式：`[SCENE N - 地点 - 时间]`

范例：
- `[SCENE 1 - 高三(1)班教室 - 早晨]`
- `[SCENE 2 - 学校天台 - 黄昏]`

## 2. 角色台词
格式：`角色名（情绪）：台词内容`

范例：
- `林知夏（紧张）：老师...`
- `张老师（严厉）：上课！`

## 3. 动作描述
无前缀，直接描述。

范例：
- `林知夏低着头，手指无意识地转着笔。`
- `窗外，一只纸飞机缓缓飞过。`

## 4. 旁白
用斜体或 `[旁白]` 标记。

范例：
- `[旁白] 那年夏天，蝉鸣格外刺耳。`
```

### 知识库 2：`aicss-shot-style-kb`（分镜风格）

```markdown
# AICSS 分镜风格指南

## 1. 景别选用原则
- 开场：Wide Shot / Full Shot 建立空间
- 关键情绪：Close-up / Extreme Close-up 强化
- 群体：Wide Shot / Medium Wide Shot
- 动作：Medium Shot 兼顾动作和表情

## 2. 运镜节奏
- 对话场景：70% Static + 30% Subtle Movement
- 动作场景：50% Movement + 50% Static
- 转场镜头：Dolly / Pan 推动叙事

## 3. 视觉风格关键词
- 纸雕风格：paper craft, hand-cut, layered paper, white edges
- 东方意境：mist, scroll painting, calligraphy, ink wash
- 青春氛围：warm light, golden hour, school uniform, cherry blossom

## 4. AICSS 视觉参考案例
- 《千与千寻》：watercolor + ink wash，柔和色彩
- 《你的名字》：photorealistic + light leak，青春色彩
- 《大鱼海棠》：paper cut + Chinese painting，国风
```

### 知识库 3：`aicss-visual-style-kb`（AI Prompt 范例库）

```markdown
# Visual Prompt 范例库

## 角色三视图范例
character turnaround front view, 17-year-old Chinese girl,
long straight black hair, brown eyes, school uniform (white shirt + blue skirt),
gentle but melancholic expression,
standing pose, full body, head to toe,
paper craft style, hand-cut paper silhouette,
flat colors with white edges visible,
white background, orthographic perspective,
by hayao miyazaki, by makoto shinkai,
highly detailed, 8k

character turnaround side view, [同上], profile view from left,
paper craft style, hand-cut paper silhouette,
white background, orthographic perspective

character turnaround back view, [同上], back of head visible,
paper craft style, hand-cut paper silhouette,
white background, orthographic perspective

## 场景范例
wide shot, ancient Chinese mountain temple,
misty morning, traditional curved roof,
stone steps, red lanterns, paper offerings,
sakura trees blooming, sunlight rays through clouds,
paper craft style, layered paper art,
white edges visible, soft gradients,
atmospheric perspective, color grading inspired by Spirited Away

closeup, weathered stone Buddha statue face,
moss covered, water dripping,
intricate carved details, golden ratio composition,
photorealistic + paper texture overlay,
soft natural lighting from above

mood shot, empty school rooftop at sunset,
golden hour, dramatic clouds,
abandoned paper airplanes scattered,
wind blowing through fence,
paper craft aesthetic, layered paper depth,
nostalgic, melancholic, contemplative
```

### 知识库 4：`aicss-scene-templates-kb`（场景模板库）

```markdown
# 场景描述模板库

## 校园类
- "high school classroom, rows of desks, blackboard with chalk dust,
   posters on wall, fluorescent lighting, posters, school motto banner"
- "school rooftop, fence, abandoned items, distant city view, sky"
- "school hallway, lockers, bulletin boards, students walking"

## 家庭类
- "small apartment kitchen, refrigerator, gas stove, morning sunlight through window"
- "bedroom, single bed, desk with books, warm lamp light, family photo on wall"

## 奇幻类
- "floating islands, waterfalls, ancient ruins, glowing crystals, multiple moons"
- "enchanted forest, bioluminescent mushrooms, fog, ancient trees, magic aura"

## 都市类
- "neon-lit street, rain-soaked asphalt, vending machines, late night"
- "skyscraper rooftop, city skyline, helicopter searchlights, dramatic clouds"
```

---

## 2.7 Dify 知识库的最佳实践

### 提示词模板（在 LLM 节点中使用）

```
你是 [角色定位]。

## 任务
[具体任务说明]

## 参考资料
以下是从知识库检索到的相关资料，可能对你有帮助：
---
{{#knowledge_retrieval.result#}}
---

## 输出要求
[严格 JSON / 格式要求]

## 重要规则
1. 如果参考文档中有明确规范/示例，**严格遵循**
2. 如果参考文档与任务不相关，**忽略并独立完成任务**
3. 不要提及"参考文档"或"知识库"等元信息
4. 不要在输出中解释你的推理过程
```

### 知识库分段优化

```yaml
# Dify 知识库配置
chunk_strategy: "paragraph"   # 按段落分
chunk_size: 800              # tokens
chunk_overlap: 50
pre_processing_rules:
  - "remove_extra_whitespace"
  - "remove_urls"
  - "remove_emails"
```

### Embedding 模型选择

| 模型 | 优势 | 适用 |
|------|------|------|
| `text-embedding-v3` (DashScope) | 中文一流 | 中文剧本 |
| `bge-large-zh-v1.5` (本地) | 完全离线 | 隐私场景 |
| `text-embedding-3-large` (OpenAI) | 英文最佳 | 英文剧本 |
| `bge-m3` (本地) | 多语言 | 中英混合 |

切换 Embedding：在 Dify Web UI → `知识库` → 设置 → `Embedding 模型`。

---

## 2.8 调试与日志

```bash
# Dify 容器日志
cd ~/projects/aicss-tools/dify/docker
docker compose logs -f api

# 工作流执行历史（Web UI）
# 进入应用 → 工作流 → 查看每次执行的 input/output/trace

# 直接调用工作流 API 测试
curl -X POST http://localhost:8001/v1/workflows/run \
  -H "Authorization: Bearer app-你的API-key" \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {"raw_text": "测试剧本内容..."},
    "response_mode": "blocking",
    "user": "test-user"
  }'

# 流式响应（SSE）
curl -X POST http://localhost:8001/v1/workflows/run \
  -H "Authorization: Bearer app-你的API-key" \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {...},
    "response_mode": "streaming",
    "user": "test-user"
  }'
```

---

## 2.9 Dify 工作流导入/导出

### 导出（备份 / 跨环境复制）

Web UI → 工作室 → 选工作流 → 右上角 ... → `导出 DSL`

文件格式：`script_parse.yml`，可提交到 git。

### 导入（新环境恢复）

Web UI → 工作室 → `导入 DSL` → 上传 yml 文件。

### 用 API 批量导入（CI/CD）

```bash
curl -X POST http://localhost:8001/v1/apps/import \
  -H "Authorization: Bearer app-管理员token" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@script_parse.yml" \
  -F "mode=silent-import"
```

---

## 验收清单

```
ComfyUI 部分：
✅ http://127.0.0.1:8188 能访问
✅ 工作流 1 (txt2img_basic) 提交后能生成图像
✅ 工作流 3 (depth_anything_v2) 输入图像能输出深度图
✅ 工作流 5 (wan2.1_i2v) 能生成 5s 视频（如果显存够）
✅ Z-Image-Turbo 模型加载成功

Dify 部分：
✅ http://127.0.0.1:3000 能登录
✅ qwen-max 响应正常（"你好"测试）
✅ 工作流 script_parse_with_kb 能解析简单剧本
✅ 知识库 1 (script-style) 上传并能检索

集成部分：
✅ Dify 节点能调用 ComfyUI（http://host.docker.internal:8188）
✅ Dify 节点能调用 FastAPI（http://host.docker.internal:8000）
✅ 工作流完整执行成功（剧本 → 三视图 → 持久化）
```

---

*文档生成时间: 2026-08-01*
*环境基础：WSL2 Ubuntu + RTX 4060 Ti 16GB + Docker Desktop*