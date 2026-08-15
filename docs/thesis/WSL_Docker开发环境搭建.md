# WSL2 + Docker 开发环境搭建指南（ComfyUI + Dify + Blender 三工作流方案）

> **目标：在 Windows 11 上搭建一个与生产一致的开发环境，所有 AI 服务（ComfyUI / Dify / Blender）和 AICSS 后端都跑在 Docker 容器里，前端在 Windows 上调试，所有数据/模型通过 WSL 文件系统共享。开发体验近似纯 Linux，AI 模型推理性能不打折扣。**
>
> 适用版本：AICinematicSpatialSystem v2
> 文档日期：2026-08-01
> 预计搭建时间：60-90 分钟（含模型下载）

---

## 0. 当前环境确认

```
Windows 11 (win32 10.0.19045)
├── PowerShell
├── WSL2
│   ├── Ubuntu (默认发行版, Running, v2)
│   └── docker-desktop (Running, v2)
├── Docker version 29.6.2
├── Docker Compose v5.3.1
└── GPU: NVIDIA GeForce RTX 4060 Ti (16GB)

✅ WSL2 已就绪
✅ Docker Desktop 已安装
✅ GPU 可直通到 WSL2（nvidia-smi 可见）
```

---

## 1. 推荐目录布局

把项目整体从 `F:\AICinematicSpatialSystem` 移到 WSL 文件系统（`\\wsl$\Ubuntu\...`），性能比 `/mnt/f` 快 3-5 倍，对 AI 模型加载影响很大。

### 1.1 推荐：项目根目录迁到 WSL

```bash
# 在 WSL2 Ubuntu 内执行
mkdir -p ~/projects
cp -r /mnt/f/AICinematicSpatialSystem ~/projects/AICinematicSpatialSystem
cd ~/projects/AICinematicSpatialSystem

# 或者用 git clone（如果用了版本控制）
# git clone https://github.com/yourname/AICinematicSpatialSystem.git ~/projects/AICinematicSpatialSystem
```

### 1.2 备选：保持项目在 /mnt/f

如果不想迁移大量已有数据，可以继续用 `/mnt/f/AICinematicSpatialSystem`，但 Dockerfile 里要用 `WORKDIR /workspace` 挂载，性能会稍差但可接受。

**建议**：
- 模型权重（~50GB）放在 WSL 文件系统：`~/projects/aicss-data/models`
- 项目代码：放在 WSL 文件系统：`~/projects/AICinematicSpatialSystem`
- 仅前端用 Windows 编辑器（VSCode Remote）

### 1.3 Windows 资源管理器访问 WSL

```
\\wsl$\Ubuntu\home\<用户名>\projects\AICinematicSpatialSystem
```

或者在 VSCode 里安装 `WSL` 扩展直接打开。

---

## 2. WSL2 系统级优化

### 2.1 配置 `.wslconfig`（Windows 侧）

编辑 `C:\Users\liuqi\.wslconfig`（不存在则创建）：

```ini
[wsl2]
# 限制 WSL 内存（避免吃光 Windows）
memory=24GB
# 限制 CPU 核数
processors=12
# 启用 swap（避免 OOM）
swap=8GB
# 启用嵌套虚拟化（Docker Desktop 需要）
nestedVirtualization=true
# 自动释放缓存
autoMemoryReclaim=gradual

[experimental]
# 启用镜像文件系统（更快的 IO）
sparseVhd=true
# 自动同步时间
hostReuseUptime=true
```

**重启 WSL 让配置生效**（PowerShell）：

```powershell
wsl --shutdown
# 然后重新打开 Ubuntu
```

### 2.2 Ubuntu 侧：基础依赖

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y build-essential git curl wget htop nvtop \
                    nvidia-cuda-toolkit libgl1-mesa-glx libglib2.0-0 \
                    unzip p7zip-full
```

### 2.3 验证 GPU 直通

```bash
# 在 WSL 内
nvidia-smi
# 应该看到 RTX 4060 Ti

# 验证 Docker 能否访问 GPU
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
# 应该看到相同的 GPU 信息
```

---

## 3. Docker Compose 一键启动所有服务

### 3.1 项目目录结构（在 WSL 内）

```
~/projects/AICinematicSpatialSystem/
├── backend/                    # FastAPI 代码（保留原状）
├── frontend/                   # React 代码（保留原状）
├── blender_aicss/              # Blender 插件源码
├── workflows/                  # ComfyUI 工作流 JSON
│   ├── character_three_view.json
│   ├── scene_keyframes.json
│   ├── txt2img_basic.json
│   ├── img2img.json
│   ├── lama_inpaint.json
│   ├── depth_anything_v2.json
│   ├── grounding_dino.json
│   ├── sam2_segment.json
│   ├── wan2.1_i2v.json
│   └── paper_diorama.json
├── dify_workflows/             # Dify 工作流 DSL（导出后）
│   ├── script_parse.yml
│   ├── shot_generation.yml
│   ├── character_asset.yml
│   ├── scene_asset.yml
│   ├── video_generation.yml
│   ├── blender_export.yml
│   └── master_production.yml
├── docker/
│   ├── Dockerfile.backend
│   ├── Dockerfile.comfyui
│   ├── Dockerfile.blender
│   ├── Dockerfile.dify
│   └── init-scripts/
│       ├── 01-init-comfyui.sh
│       └── 02-init-dify.sh
├── data/                       # 持久化数据（git 忽略）
│   ├── comfyui/
│   │   ├── models/
│   │   ├── output/
│   │   └── input/
│   ├── dify/
│   │   ├── db/
│   │   └── storage/
│   ├── projects/               # AICSS 项目工作空间
│   └── cache/                  # HF / pip 缓存
├── docker-compose.yml          # 一键启动
├── .env                        # 密钥配置
└── README.md
```

### 3.2 `docker-compose.yml`（核心配置）

```yaml
version: "3.9"

x-common-env: &common-env
  HF_ENDPOINT: "https://hf-mirror.com"
  HF_HUB_DISABLE_XET: "1"
  HF_HOME: "/workspace/cache/huggingface"

services:
  # ─────────────────────────────────────────────────────────────────
  # AICSS FastAPI 后端
  # ─────────────────────────────────────────────────────────────────
  aicss-backend:
    build:
      context: .
      dockerfile: docker/Dockerfile.backend
    container_name: aicss-backend
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - ./backend:/workspace/backend
      - ./data/projects:/workspace/.workspace/projects
      - ./data/cache:/workspace/cache
      - ./workflows:/workspace/workflows:ro
      - ./dify_workflows:/workspace/dify_workflows:ro
    environment:
      - AICSS_DIFY_URL=http://dify-api:8001
      - AICSS_COMFYUI_URL=http://comfyui:8188
      - AICSS_BLENDER_URL=http://aicss-blender:8889
      - DASHSCOPE_API_KEY=${DASHSCOPE_API_KEY:-}
      - AICSS_IMAGE_MODE=local
      - AICSS_VIDEO_MODE=local
      - AICSS_LLM_MODE=local
      - DASHSCOPE_LLM_API_KEY=${DASHSCOPE_API_KEY:-}
    networks:
      - aicss-net
    depends_on:
      - comfyui
      - dify-api

  # ─────────────────────────────────────────────────────────────────
  # ComfyUI 推理服务（图像/视频 AI）
  # ─────────────────────────────────────────────────────────────────
  comfyui:
    build:
      context: .
      dockerfile: docker/Dockerfile.comfyui
    container_name: aicss-comfyui
    restart: unless-stopped
    ports:
      - "8188:8188"
    volumes:
      - ./data/comfyui/models:/workspace/models
      - ./data/comfyui/output:/workspace/output
      - ./data/comfyui/input:/workspace/input
      - ./workflows:/workspace/workflows:ro
      - ./data/cache/huggingface:/workspace/cache/huggingface
    environment:
      <<: *common-env
      - NVIDIA_VISIBLE_DEVICES=all
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    networks:
      - aicss-net

  # ─────────────────────────────────────────────────────────────────
  # Blender HTTP 服务（3D mesh 导出）
  # ─────────────────────────────────────────────────────────────────
  aicss-blender:
    build:
      context: .
      dockerfile: docker/Dockerfile.blender
    container_name: aicss-blender
    restart: unless-stopped
    ports:
      - "8889:8889"
    volumes:
      - ./blender_aicss:/workspace/blender_aicss:ro
      - ./data/projects:/workspace/projects
      - ./data/cache/huggingface:/workspace/cache/huggingface
    environment:
      - AICSS_BLENDER_PORT=8889
      - NVIDIA_VISIBLE_DEVICES=all
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu, utility]
    networks:
      - aicss-net

  # ─────────────────────────────────────────────────────────────────
  # Dify 编排服务
  # ─────────────────────────────────────────────────────────────────
  dify-db:
    image: postgres:15-alpine
    container_name: aicss-dify-db
    restart: unless-stopped
    environment:
      POSTGRES_DB: dify
      POSTGRES_USER: dify
      POSTGRES_PASSWORD: dify123
    volumes:
      - ./data/dify/db:/var/lib/postgresql/data
    networks:
      - aicss-net

  dify-redis:
    image: redis:7-alpine
    container_name: aicss-dify-redis
    restart: unless-stopped
    networks:
      - aicss-net

  dify-api:
    build:
      context: .
      dockerfile: docker/Dockerfile.dify
    container_name: aicss-dify-api
    restart: unless-stopped
    depends_on:
      - dify-db
      - dify-redis
    ports:
      - "8001:8001"
    volumes:
      - ./data/dify/storage:/app/api/storage
      - ./dify_workflows:/app/workflow_export:ro
    environment:
      - DB_USERNAME=dify
      - DB_PASSWORD=dify123
      - DB_HOST=dify-db
      - DB_PORT=5432
      - DB_DATABASE=dify
      - REDIS_HOST=dify-redis
      - REDIS_PORT=6379
      - SECRET_KEY=dify-aicss-secret-change-me
      - CONSOLE_API_URL=http://dify-web:3000
    networks:
      - aicss-net

  dify-web:
    image: langgenius/dify-web:latest
    container_name: aicss-dify-web
    restart: unless-stopped
    depends_on:
      - dify-api
    ports:
      - "3000:3000"
    environment:
      - CONSOLE_API_URL=http://dify-api:8001
      - APP_API_URL=http://dify-api:8001
    networks:
      - aicss-net

  # ─────────────────────────────────────────────────────────────────
  # Ollama 本地 LLM 服务（替代 DashScope，可选）
  # ─────────────────────────────────────────────────────────────────
  ollama:
    image: ollama/ollama:latest
    container_name: aicss-ollama
    restart: unless-stopped
    ports:
      - "11434:11434"
    volumes:
      - ./data/ollama:/root/.ollama
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    networks:
      - aicss-net

networks:
  aicss-net:
    driver: bridge
```

### 3.3 `.env` 文件

```bash
# 阿里云 DashScope（如果用云端模型）
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx

# Dify 超级管理员
DIFY_ADMIN_EMAIL=admin@aicss.local
DIFY_ADMIN_PASSWORD=AICSS@dify2026

# 项目路径
AICSS_PROJECT_ROOT=~/projects/AICinematicSpatialSystem
```

---

## 4. 各服务的 Dockerfile

### 4.1 `docker/Dockerfile.backend`

```dockerfile
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /workspace

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev ffmpeg libsm6 libxext6 \
        libxrender-dev libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

# 代码挂载（开发模式热重载）
COPY backend /workspace/backend
COPY workflows /workspace/workflows
COPY dify_workflows /workspace/dify_workflows

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

### 4.2 `docker/Dockerfile.comfyui`

```dockerfile
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

WORKDIR /workspace

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3.11-venv python3-pip \
        git wget ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.11 /usr/bin/python

# ComfyUI
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /workspace/ComfyUI
WORKDIR /workspace/ComfyUI

# Python 依赖
RUN pip install --upgrade pip wheel \
    && pip install torch torchvision torchaudio \
        --index-url https://download.pytorch.org/whl/cu124 \
    && pip install -r requirements.txt

# 必备插件
RUN mkdir -p /workspace/ComfyUI/custom_nodes && \
    cd /workspace/ComfyUI/custom_nodes && \
    git clone https://github.com/ltdrdata/ComfyUI-Impact-Pack.git && \
    git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git && \
    git clone https://github.com/city96/ComfyUI-WanVideoWrapper.git && \
    git clone https://github.com/ltdrdata/ComfyUI-Manager.git

# 安装插件依赖（容错）
RUN for d in custom_nodes/*/; do \
        if [ -f "$d/requirements.txt" ]; then \
            pip install -r "$d/requirements.txt" 2>&1 || true; \
        fi; \
    done

# 工作流挂载点
RUN mkdir -p /workspace/workflows /workspace/output /workspace/input /workspace/models

EXPOSE 8188

# 启动命令（从挂载的工作流目录读取）
CMD ["python", "main.py", "--listen", "0.0.0.0", "--port", "8188", "--disable-auto-launch"]
```

### 4.3 `docker/Dockerfile.blender`

```dockerfile
FROM nvidia/cuda:12.4.1-base-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    BLENDER_VERSION=4.2.0

WORKDIR /workspace

# Blender 4.2 LTS
RUN wget -q "https://download.blender.org/release/Blender${BLENDER_VERSION%.*}.${BLENDER_VERSION##*.}/blender-${BLENDER_VERSION}-linux-x64.tar.xz" \
        -O /tmp/blender.tar.xz \
    && tar -xJf /tmp/blender.tar.xz -C /opt \
    && rm /tmp/blender.tar.xz \
    && ln -sf /opt/blender-${BLENDER_VERSION}-linux-x64/blender /usr/local/bin/blender \
    && ln -sf /opt/blender-${BLENDER_VERSION}-linux-x64/blender.bin /usr/local/bin/blender.bin

# 系统依赖 + Blender Python pip
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3-pip libgl1 libglu1-mesa libxi6 libxrender1 \
        libxxf86vm1 libxfixes3 libxrandr2 libxinerama1 libxcursor1 \
        libxkbcommon0 libsm6 libice6 libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Blender 嵌入式 Python 安装 aiohttp
RUN BLENDER_PY=$(find /opt/blender-${BLENDER_VERSION}-linux-x64 -name "python3.11" -type f | head -1) && \
    if [ -z "$BLENDER_PY" ]; then \
        BLENDER_PY="/opt/blender-${BLENDER_VERSION}-linux-x64/python/bin/python3.11"; \
    fi && \
    echo "Using Blender Python: $BLENDER_PY" && \
    $BLENDER_PY -m ensurepip && \
    $BLENDER_PY -m pip install --upgrade pip aiohttp requests

# Blender 插件源码
COPY blender_aicss /workspace/blender_aicss

# 项目数据挂载
RUN mkdir -p /workspace/projects /workspace/cache

EXPOSE 8889

# 启动：headless Blender + 加载插件 + 开启 HTTP 服务
CMD blender --background \
        --python /workspace/blender_aicss/server/boot.py \
        --python-expr "import blender_aicss.preferences as p; from blender_aicss.preferences import get_server; s = get_server(); s.start(); import time; time.sleep(999999)"
```

> 备注：上面的启动方式需要在 `blender_aicss/server/boot.py` 写一个引导脚本注册插件。

### 4.4 `docker/Dockerfile.dify`

```dockerfile
FROM langgenius/dify-api:latest

# Dify 自定义：默认启用 + 预导入我们的工作流
COPY docker/init-scripts/02-init-dify.sh /docker-entrypoint-initdb.d/

# 默认配置已 OK，需要时挂载 volumes 覆盖
```

---

## 5. 一键启动

### 5.1 首次启动（下载所有镜像）

```bash
cd ~/projects/AICinematicSpatialSystem

# 1. 拉取所有镜像（首次约 30GB）
docker compose pull

# 2. 构建自定义镜像（首次约 20 分钟）
docker compose build

# 3. 启动所有服务（后台运行）
docker compose up -d

# 4. 查看状态
docker compose ps
```

### 5.2 查看日志

```bash
# 全部日志
docker compose logs -f

# 单服务
docker compose logs -f aicss-backend
docker compose logs -f comfyui
docker compose logs -f aicss-blender

# 最近 100 行
docker compose logs --tail=100 aicss-backend
```

### 5.3 停止 / 重启

```bash
# 停止（保留容器）
docker compose stop

# 停止并删除容器（保留 volumes）
docker compose down

# 完全重置（含数据卷，慎用！）
docker compose down -v

# 重启单个服务
docker compose restart aicss-backend
```

---

## 6. 关键服务验证

### 6.1 验证 AICSS Backend

```bash
curl http://localhost:8000/health
# {"status":"ok","device":"cuda","models_loaded":true}

curl http://localhost:8000/docs
# Swagger UI
```

### 6.2 验证 ComfyUI

```bash
# 健康检查
curl http://localhost:8188/system_stats
# {"system":{"os":"linux",...},"devices":[{"name":"NVIDIA GeForce RTX 4060 Ti",...}]}

# 浏览器访问 UI
open http://localhost:8188
```

### 6.3 验证 Blender 服务

```bash
curl http://localhost:8889/health
# {"status":"ok","service":"aicss-blender"}

curl http://localhost:8889/info
# {"blender_version":"4.2.0","scene_objects":0,"meshes":0,...}
```

### 6.4 验证 Dify

```bash
# Dify Web UI
open http://localhost:3000

# 默认账号
# Email: admin@aicss.local
# Password: AICSS@dify2026
```

---

## 7. 在 Windows 侧开发

### 7.1 VSCode Remote WSL 模式

```
1. VSCode 安装扩展 "WSL" (ms-vscode-remote.remote-wsl)
2. 打开命令面板 (Ctrl+Shift+P)
3. 搜索 "WSL: Connect to WSL"
4. 选择 ~/projects/AICinematicSpatialSystem
5. VSCode 现在跑在 Windows，但所有命令都在 WSL 执行
```

VSCode 还会推荐安装：
- `ms-python.python`
- `ms-python.vscode-pylance`
- `dbaeumer.vscode-eslint`
- `bradlc.vscode-tailwindcss`
- `ms-azuretools.vscode-docker`

### 7.2 前端开发（保持 Windows）

```bash
# 在 Windows PowerShell
cd F:\AICinematicSpatialSystem\frontend

# 用 Windows 的 Node 调试
npm install
npm run dev
# → http://localhost:5173
```

**配置前端环境变量指向 WSL 内的服务**：

```bash
# frontend/.env.development
VITE_API_BASE_URL=http://localhost:8000
VITE_COMFYUI_URL=http://localhost:8188
VITE_BLENDER_URL=http://localhost:8889
VITE_DIFY_URL=http://localhost:3000
```

> 由于 WSL2 会自动把容器端口映射到 `localhost`，Windows 侧直接访问 `localhost:端口` 即可。

### 7.3 后端开发（在 WSL 内）

```bash
# 在 WSL Ubuntu 内
cd ~/projects/AICinematicSpatialSystem
code .  # 用 VSCode Remote WSL 打开

# 后端代码修改 → 容器内 uvicorn --reload 自动重启
# 日志：docker compose logs -f aicss-backend
```

---

## 8. 模型下载与缓存

### 8.1 ComfyUI 模型（启动后下载）

在 ComfyUI 容器内执行（一次性）：

```bash
# 进入容器
docker compose exec comfyui bash

# Z-Image-Turbo（首选）
cd /workspace/models/checkpoints
wget https://hf-mirror.com/Tongyi-MAI/Z-Image-Turbo/resolve/main/z-image-turbo-fp8.safetensors

# SDXL（备用）
wget https://hf-mirror.com/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors

# Depth-Anything-V2
wget https://hf-mirror.com/depth-anything/Depth-Anything-V2-Large/resolve/main/depth_anything_v2_vitl.pth

# Grounding-DINO
wget https://hf-mirror.com/IDEA-Research/grounding-dino-base/resolve/main/groundingdino_swit_ogc.pth

# SAM2（hiera large）
wget https://hf-mirror.com/facebook/sam2-hiera-large/resolve/main/sam2_hiera_large.pt

# Wan2.1 I2V（视频，可选，14GB）
# wget https://hf-mirror.com/Wan-AI/Wan2.1-I2V-14B-480P/resolve/main/diffusion_pytorch_model.safetensors

exit
```

**模型会持久化**在 `./data/comfyui/models/`，重启容器不丢失。

### 8.2 Ollama 模型（本地 LLM）

```bash
docker compose exec ollama ollama pull qwen2.5:7b
docker compose exec ollama ollama pull llama3.2:3b
```

### 8.3 缓存目录结构

```
data/
├── comfyui/
│   ├── models/
│   │   ├── checkpoints/        # Z-Image-Turbo, SDXL
│   │   ├── vae/
│   │   ├── loras/
│   │   ├── controlnet/
│   │   └── diffusion_models/   # Wan2.1
│   ├── output/                # 生成的图像
│   └── input/                 # 输入图像（用户上传）
├── dify/
│   ├── db/                    # PostgreSQL 数据
│   └── storage/               # 文件存储
├── projects/                  # AICSS 项目工作空间
├── cache/
│   └── huggingface/           # HF 缓存
└── ollama/                    # Ollama 模型
```

---

## 9. 在容器内调试工作流

### 9.1 ComfyUI 工作流调试

```bash
# 1. 进入 ComfyUI 容器
docker compose exec comfyui bash

# 2. 启动 Python REPL
python3

# 3. 模拟提交工作流
import json, requests
workflow = json.load(open("/workspace/workflows/character_three_view.json"))
resp = requests.post(
    "http://localhost:8188/prompt",
    json={"prompt": workflow, "client_id": "test"},
)
print(resp.json())
# → {"prompt_id": "abc..."}

# 4. 等待结果
import time
prompt_id = resp.json()["prompt_id"]
for _ in range(60):
    hist = requests.get(f"http://localhost:8188/history/{prompt_id}").json()
    if prompt_id in hist:
        print("Done:", hist[prompt_id]["outputs"])
        break
    time.sleep(2)
```

### 9.2 Blender 服务调试

```bash
# 进入 Blender 容器
docker compose exec aicss-blender bash

# Blender Python 环境
blender --background --python-expr "import bpy; print(bpy.app.version)"
# Blender 4.2.0

# 交互式调试
blender --background --python-console
>>> import bpy
>>> bpy.ops.mesh.primitive_cube_add()
```

### 9.3 Dify 工作流调试

```bash
# 进入 Dify API 容器
docker compose exec dify-api bash

# 直接调用工作流 API
curl -X POST http://localhost:8001/v1/workflows/run \
  -H "Authorization: Bearer app-xxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {"raw_text": "测试剧本"},
    "response_mode": "blocking",
    "user": "test-user"
  }'
```

---

## 10. 关键性能优化

### 10.1 GPU 共享策略

ComfyUI 和 Blender 不能同时使用 GPU（会 OOM），需要分时复用：

```yaml
# 方案 A: 同时跑两个轻量服务（适合 16GB+ VRAM）
# RTX 4060 Ti 16GB 够用：ComfyUI 占 8-10GB + Blender Cycles 4-6GB
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: 1
          capabilities: [gpu]

# 方案 B: 单服务模式（适合 8GB VRAM）
# 用环境变量切换 AICSS_BLENDER_ENABLED / AICSS_COMFYUI_ENABLED
```

### 10.2 文件系统挂载优化

```yaml
# ❌ 慢（WSL2 跨 fs）
volumes:
  - /mnt/c/Users/...:/workspace

# ✅ 快（WSL 内部 fs）
volumes:
  - ~/projects/...:/workspace

# ✅ 最快（named volume，但容器间共享难）
volumes:
  - aicss-data:/workspace
```

### 10.3 镜像下载优化

```bash
# 配置 Docker 镜像加速（编辑 /etc/docker/daemon.json 或 Docker Desktop Settings）
{
  "registry-mirrors": [
    "https://docker.mirrors.ustc.edu.cn",
    "https://hub-mirror.c.163.com"
  ]
}

# 重启 Docker Desktop
```

### 10.4 Blender 容器启动优化

```dockerfile
# 缓存 Blender Python 预编译字节码
RUN /opt/blender-4.2.0-linux-x64/python/bin/python3.11 -m compileall /opt/blender-4.2.0-linux-x64/python/lib/python3.11/site-packages

# 预热：启动一次 Blender 让 bpy 完成初始化（避免首次调用延迟）
RUN blender --background --python-expr "import bpy; print('OK')" || true
```

---

## 11. 日常开发工作流

### 11.1 启动开发环境

```bash
# WSL Ubuntu
cd ~/projects/AICinematicSpatialSystem
docker compose up -d
docker compose ps   # 确认全部 healthy
```

### 11.2 修改 ComfyUI 工作流

```
1. 打开 ComfyUI Web UI: http://localhost:8188
2. 在浏览器里拖拽节点，配置参数
3. 点击 "Save" → 保存到 ~/projects/.../workflows/xxx.json
4. Git 提交
5. Dify 调用该 JSON（无需重启服务）
```

### 11.3 修改 Blender 插件

```bash
# 1. 修改 blender_aicss/xxx.py
# 2. 重启 Blender 容器
docker compose restart aicss-blender

# 3. 验证
curl http://localhost:8889/health
```

### 11.4 修改 Dify 工作流

```
1. 打开 Dify Web UI: http://localhost:3000
2. 编辑工作流
3. 点击 "发布"
4. Dify API 自动 reload，无需重启服务
```

### 11.5 修改后端代码

```bash
# uvicorn --reload 自动检测代码变化并重启
docker compose logs -f aicss-backend
# 应该看到 "Detected file change... Restarting workers"
```

### 11.6 调试模型加载问题

```bash
# ComfyUI 显存不足？
docker compose exec comfyui nvidia-smi
# 应该看到 ComfyUI 进程占用

# 重启 ComfyUI（释放显存）
docker compose restart comfyui
```

---

## 12. 常见问题

### Q1：Docker Compose 启动后 AICSS Backend unhealthy？

```bash
# 查看具体错误
docker compose logs aicss-backend

# 常见原因：DASHSCOPE_API_KEY 未设置
# 解决：编辑 .env，加上 API key，然后
docker compose up -d aicss-backend
```

### Q2：ComfyUI 报 "Out of Memory"？

```bash
# 检查 GPU 占用
docker compose exec comfyui nvidia-smi

# Blender 也占显存？临时停掉
docker compose stop aicss-blender

# 再启动 ComfyUI
docker compose start comfyui
```

### Q3：Blender 容器内 Blender 命令找不到？

```bash
# 检查 PATH
docker compose exec aicss-blender which blender

# 应该输出 /usr/local/bin/blender
# 如果没找到，重新构建：
docker compose build aicss-blender
docker compose up -d aicss-blender
```

### Q4：Windows 浏览器访问 localhost:8188 显示"拒绝连接"？

```bash
# 检查 WSL 端口转发
netsh interface portproxy show all  # PowerShell

# Docker Desktop 默认会自动转发，但有时候需要重启
# 任务栏右键 Docker Desktop → Restart
```

### Q5：模型下载慢？

```bash
# 在容器内手动下载（使用镜像）
docker compose exec comfyui bash
export HF_ENDPOINT=https://hf-mirror.com
wget https://hf-mirror.com/...

# 或者用 huggingface-cli（推荐）
pip install huggingface_hub
huggingface-cli download Tongyi-MAI/Z-Image-Turbo \
    --local-dir /workspace/models/checkpoints/ \
    --resume-download
```

### Q6：如何重置所有数据？

```bash
# ⚠️ 危险操作！会删除所有项目、模型、工作流状态
cd ~/projects/AICinematicSpatialSystem
docker compose down -v   # 删除容器 + volumes
rm -rf data/             # 删除数据
docker compose build     # 重新构建镜像
docker compose up -d
```

---

## 13. 推荐开发插件（VSCode）

| 插件 | 用途 |
|------|-----|
| `ms-vscode-remote.remote-wsl` | WSL 远程开发 |
| `ms-azuretools.vscode-docker` | Docker 容器管理 |
| `ms-python.python` | Python 调试 |
| `ms-python.vscode-pylance` | Python 智能提示 |
| `bradlc.vscode-tailwindcss` | 前端样式 |
| `esbenp.prettier-vscode` | 代码格式化 |
| `tamasfe.even-better-toml` | 配置高亮 |
| `redhat.vscode-yaml` | YAML 高亮（Dify 工作流） |
| `bierner.json-color-tokenizer` | JSON 可视化 |
| `EditorConfig.EditorConfig` | 代码风格统一 |

### 推荐 settings.json

```json
{
  "python.defaultInterpreterPath": "/usr/bin/python3.11",
  "python.analysis.autoImportCompletions": true,
  "[python]": {
    "editor.formatOnSave": true,
    "editor.defaultFormatter": "ms-python.black-formatter"
  },
  "[yaml]": {
    "editor.formatOnSave": true,
    "editor.defaultFormatter": "redhat.vscode-yaml"
  },
  "remote.WSL.fileWatcher.polling": true,
  "files.watcherExclude": {
    "**/node_modules/**": true,
    "**/.git/**": true,
    "**/data/**": true
  }
}
```

---

## 14. 一键脚本（可选）

`scripts/dev-up.sh`（放在项目根）：

```bash
#!/bin/bash
# 一键启动开发环境

set -e

cd "$(dirname "$0")/.."

echo "==> 检查环境..."
command -v docker >/dev/null 2>&1 || { echo "❌ Docker 未安装"; exit 1; }
command -v nvidia-smi >/dev/null 2>&1 || { echo "❌ 未检测到 NVIDIA 驱动"; exit 1; }

echo "==> 拉取镜像..."
docker compose pull

echo "==> 构建自定义镜像..."
docker compose build

echo "==> 启动服务..."
docker compose up -d

echo "==> 等待服务就绪..."
sleep 10
docker compose ps

echo ""
echo "✅ 开发环境已启动！"
echo ""
echo "访问地址："
echo "  AICSS Backend:    http://localhost:8000/docs"
echo "  ComfyUI:          http://localhost:8188"
echo "  Blender Service:  http://localhost:8889/info"
echo "  Dify Web:         http://localhost:3000"
echo ""
echo "查看日志: docker compose logs -f [service_name]"
echo "停止环境: docker compose down"
```

使用：

```bash
chmod +x scripts/dev-up.sh
./scripts/dev-up.sh
```

---

## 15. 验收清单

完成以下所有项，环境即搭建完成：

```
✅ WSL2 Ubuntu 可用，GPU 直通正常
✅ Docker / Docker Compose 可用
✅ docker compose up -d 成功启动所有服务
✅ curl localhost:8000/health 返回 ok
✅ curl localhost:8188/system_stats 返回 GPU 信息
✅ curl localhost:8889/health 返回 aicss-blender
✅ http://localhost:3000 Dify Web UI 可登录
✅ VSCode 通过 WSL 远程连接成功
✅ 前端 npm run dev 可访问 http://localhost:5173
✅ Z-Image-Turbo 模型下载并加载成功
✅ 提交一次 ComfyUI 工作流，轮询拿到结果
✅ Blender 服务返回 scene info
✅ Dify 工作流可调用 ComfyUI 和 Blender HTTP 服务
```

---

## 16. 下一步

环境就绪后，按以下顺序开发：

| 顺序 | 任务 | 工时 |
|------|------|-----|
| 1 | 在 ComfyUI Web UI 中制作 `txt2img_basic.json` 并测试 | 2-3h |
| 2 | 制作 `character_three_view.json` + `scene_keyframes.json` | 6-8h |
| 3 | 制作 `depth_anything_v2.json` / `sam2_segment.json` / `lama_inpaint.json` | 8-10h |
| 4 | 编写 AICSS Backend 的 `comfyui_client.py`（替代 Diffusers） | 8-12h |
| 5 | 编写 Dify 工作流 `script_parse.yml` | 4-6h |
| 6 | 编写 Blender 插件 `scene_builder.py` + `material_factory.py` | 20-30h |
| 7 | 编写 Blender 插件 `http_server.py` + `routes.py` | 20-25h |
| 8 | 端到端联调 | 10-15h |
| **总计** | | **78-109h** |

---

*文档生成时间: 2026-08-01*
*环境基础：Windows 11 + WSL2 + Ubuntu + Docker Desktop + RTX 4060 Ti 16GB*