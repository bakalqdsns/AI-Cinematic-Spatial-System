# AICSS Backend

AI Cinematic Spatial System — Inference Server

## Setup

### 1. Create & activate virtual environment

```bash
cd backend

# Create venv
python -m venv .venv

# Activate (PowerShell / Windows)
.\.venv\Scripts\Activate.ps1
# or CMD: .\.venv\Scripts\activate.bat
# or Bash / Git Bash / WSL: source .venv/bin/activate
```

### 2. Install dependencies

```bash
# GPU (CUDA 12.x) — recommended
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt

# CPU only
pip install -r requirements.txt
```

### 3. (Optional) Pre-download models

```bash
# Grounding DINO
python -c "from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor; \
    AutoProcessor.from_pretrained('IDEA-Research/grounding-dino-base'); \
    AutoModelForZeroShotObjectDetection.from_pretrained('IDEA-Research/grounding-dino-base')"

# DepthAnything V2
python -c "from transformers import AutoModelForDepthEstimation, AutoImageProcessor; \
    AutoImageProcessor.from_pretrained('depth-anything/Depth-Anything-V2-Large'); \
    AutoModelForDepthEstimation.from_pretrained('depth-anything/Depth-Anything-V2-Large')"
```

### 4. Run

```bash
# Standard (auto-detects .venv, GPU mode)
python run.py

# Force CPU mode
python run.py --cpu

# Custom port
python run.py --port 8080
```

## Connect to Frontend

In your frontend code, point AICSS to the backend:

```typescript
// src/App.tsx or where you init services
import { initAicss } from './services/aicss/aicssService';

initAicss('http://localhost:8000');
```

Or via environment variable in `.env`:

```
VITE_AICSS_BACKEND=http://localhost:8000
```

## API Docs

Once running, visit:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health: http://localhost:8000/health

## Endpoint Summary

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/aicss/analyze` | Full pipeline |
| POST | `/api/aicss/depth` | Depth map only |
| POST | `/api/aicss/segment` | Object segmentation |
| POST | `/api/aicss/layers` | Build spatial layers |
| POST | `/api/aicss/scene-graph` | Build scene graph |
| POST | `/api/aicss/billboard` | RGBA billboard texture |
| POST | `/api/aicss/multiface` | 6-face pseudo-3D textures |
| GET | `/health` | Health check |

## Model Disk Space

| Model | Approx. Size |
|-------|-------------|
| DepthAnything V2 Large | ~600 MB |
| Grounding DINO Base | ~400 MB |
| SAM2.1 ViT-H (ultralytics) | ~2.5 GB |
| **Total** | **~3.5 GB** |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AICSS_DEVICE` | `cuda` | `cuda` or `cpu` |
| `AICSS_PORT` | `8000` | Server port |
| `AICSS_HOST` | `0.0.0.0` | Server host |
| `AICSS_HF_TOKEN` | `` | HuggingFace token for gated models |
| `AICSS_DEPTH_MODEL` | `depth-anything/Depth-Anything-V2-Large` | Depth model |
| `AICSS_SAM2_MODEL_SIZE` | `vit_h` | SAM2 size: `vit_h` or `vit_b` |
