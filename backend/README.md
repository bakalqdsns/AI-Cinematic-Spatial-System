# AICSS Backend

FastAPI inference server for the AI Cinematic Spatial System. Runs the full depth + segmentation pipeline and serves RGBA billboard textures.

## Prerequisites

- Python 3.10+
- CUDA 12.x (optional — GPU recommended for real-time inference)

## Setup

### 1 — Virtual environment

```bash
cd backend

python -m venv .venv

# Activate
# PowerShell:
.\.venv\Scripts\Activate.ps1
# CMD:
.\.venv\Scripts\activate.bat
# Bash / Git Bash / WSL:
source .venv/bin/activate
```

### 2 — Install dependencies

```bash
# GPU (CUDA 12.1)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt

# CPU only
pip install -r requirements.txt
```

### 3 — Download SAM2 checkpoint

Place the SAM2.1 checkpoint in `backend/`. The filename must match `sam2_model_size` in config:

| Config value | Expected file |
|---|---|
| `vit_l` | `sam2.1_l.pt` |
| `vit_b` | `sam2.1_b.pt` |
| `vit_s` | `sam2.1_s.pt` |
| `vit_t` | `sam2.1_t.pt` |

Download from: https://github.com/facebookresearch/segment-anything-2/releases

### 4 — (Optional) Pre-download HuggingFace models

```bash
python -c "from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor; \
    AutoProcessor.from_pretrained('IDEA-Research/grounding-dino-base'); \
    AutoModelForZeroShotObjectDetection.from_pretrained('IDEA-Research/grounding-dino-base')"

python -c "from transformers import AutoModelForDepthEstimation, AutoImageProcessor; \
    AutoImageProcessor.from_pretrained('depth-anything/Depth-Anything-V2-Large-hf'); \
    AutoModelForDepthEstimation.from_pretrained('depth-anything/Depth-Anything-V2-Large-hf')"
```

Models are cached in `~/.cache/huggingface/`.

### 5 — Start the server

```bash
# Standard (auto-detects .venv, GPU mode, reload enabled)
python run.py

# Force CPU mode
python run.py --cpu

# Custom port
python run.py --port 8080
```

On first launch, all three ML models are loaded into memory — expect ~30 s startup on GPU, ~3 min on CPU. Models are held in memory for the lifetime of the process (no per-request loading).

## Configuration

All settings are read from environment variables with the `AICSS_` prefix:

```bash
AICSS_HOST=0.0.0.0
AICSS_PORT=8000
AICSS_DEVICE=cuda        # cuda | cpu
AICSS_DEPTH_MODEL=depth-anything/Depth-Anything-V2-Large-hf
AICSS_GROUNDING_DINO_MODEL=IDEA-Research/grounding-dino-base
AICSS_SAM2_MODEL_SIZE=vit_l   # vit_l | vit_b | vit_s | vit_t
AICSS_SEGMENTATION_PROMPT=person,car,building,tree,lamp,door,window,chair,table
AICSS_HF_TOKEN=hf_xxx    # required for gated HuggingFace models
```

Or via `backend/.env`:

```env
AICSS_DEVICE=cuda
AICSS_SAM2_MODEL_SIZE=vit_l
AICSS_PORT=8000
```

## API Endpoints

All endpoints are mounted under `/api/aicss`. Interactive docs available at `/docs` (Swagger) or `/redoc` (ReDoc).

### POST `/api/aicss/analyze`
Full pipeline. Runs depth estimation → object detection → segmentation → edge refinement → spatial layering → scene graph.

```json
// Request
{
  "imageUrl": "data:image/png;base64,...",
  "segmentationPrompt": "person,car,tree,building",
  "shotId": "shot_001"
}

// Response
{
  "analysisId": "aicss_abc123",
  "depthMapUrl": "data:image/png;base64,...",
  "objects": [
    {
      "id": "obj_person_0",
      "classLabel": "person",
      "depth": 3.4,
      "boundingBox": {"x": 0.12, "y": 0.31, "w": 0.08, "h": 0.55},
      "maskDataUrl": "data:image/png;base64,...",
      "polygon": [[0.12, 0.31], [0.20, 0.31], [0.20, 0.86], [0.12, 0.86]],
      "layer": "foreground"
    }
  ],
  "layers": [
    { "id": "layer_foreground_0", "name": "foreground", "zMin": 0, "zMax": 5, "objects": [...] }
  ],
  "sceneGraph": { "shotId": "shot_001", "nodes": [...] }
}
```

### POST `/api/aicss/billboard`
Crop an object from the image using its polygon mask and return a transparent RGBA PNG.

```json
// Request
{
  "imageUrl": "data:image/png;base64,...",
  "objectId": "obj_person_0",
  "boundingBox": {"x": 0.12, "y": 0.31, "w": 0.08, "h": 0.55},
  "polygon": [[0.12, 0.31], [0.20, 0.31], [0.20, 0.86], [0.12, 0.86]]
}

// polygon is optional — if omitted or empty, falls back to boundingBox rectangle
```

```json
// Response
{ "billboardUrl": "data:image/png;base64,..." }
```

### POST `/api/aicss/multiface`
Six views of the cropped object (front, back, left, right, top, bottom) for pseudo-3D billboard use.

```json
// Request — same as /billboard
{ "imageUrl": "...", "objectId": "...", "boundingBox": {...}, "polygon": [...] }
```

```json
// Response
{
  "faces": {
    "front": "data:image/png;base64,...",
    "back": "data:image/png;base64,...",
    "left": "data:image/png;base64,...",
    "right": "data:image/png;base64,...",
    "top": "data:image/png;base64,...",
    "bottom": "data:image/png;base64,..."
  }
}
```

### POST `/api/aicss/depth`
Depth map only.

```json
// Request:  { "imageUrl": "..." }
// Response: { "depthMapUrl": "data:image/png;base64,..." }
```

### POST `/api/aicss/segment`
Segmentation only (no depth or scene graph).

```json
// Request:  { "imageUrl": "...", "segmentationPrompt": "..." }
// Response: { "objects": [...] }
```

### POST `/api/aicss/layers`
Re-build spatial layers from existing objects + depth map.

```json
// Request:  { "depthMapUrl": "...", "objects": [...], "imageWidth": 1024, "imageHeight": 768 }
// Response: { "layers": [...] }
```

### POST `/api/aicss/scene-graph`
Re-build scene graph from objects.

```json
// Request:  { "shotId": "...", "objects": [...] }
// Response: { "sceneGraph": { "shotId": "...", "nodes": [...] } }
```

### GET `/health`

```json
{ "status": "ok", "device": "cuda", "models_loaded": true }
```

## Edge Refinement

After SAM2 produces a binary mask, the backend runs a post-processing step:

1. Canny edge detection on the original image (`GaussianBlur(5×5) → Canny(40, 120)`)
2. For each contour point of the mask, search within 8 px radius
3. If a Canny edge pixel is found within that radius, snap the contour vertex to it
4. Douglas-Peucker simplification (`arc_len * 0.002`, min 0.8 px tolerance) to reduce polygon point count
5. Result stored in `polygon: [[x_norm, y_norm], ...]`

This ensures the 2D canvas overlay and the billboard cutout follow the object's actual silhouette, not the SAM2 box approximation.

## Depth Buckets

Configured in `config.py`:

```python
depth_buckets = [
    (0, 5,   "foreground"),
    (5, 15,  "midground"),
    (15, 50, "background"),
    (50, inf,"sky"),
]
```

## Architecture

```
app/
├── main.py              # FastAPI app, CORS, lifespan
├── config.py            # Pydantic Settings (AICSS_* env vars)
├── endpoints.py         # All REST endpoints
├── models/
│   ├── model_manager.py # Singleton: loads all 3 models on startup
│   ├── depth_loader.py  # DepthAnything V2
│   ├── grounding_dino_loader.py
│   └── sam2_loader.py   # SAM2 + refine_mask_edges + extract_polygon_from_mask
└── utils/
    ├── image_utils.py   # base64, PIL, depth scaling, RGBA
    └── spatial_utils.py # Layer bucketing, scene graph
```

## Dependencies

| Package | Purpose |
|---|---|
| `fastapi` + `uvicorn` | Web framework + ASGI server |
| `torch` + `torchvision` | PyTorch runtime |
| `transformers` | Grounding DINO + DepthAnything |
| `ultralytics` | SAM2 wrapper |
| `opencv-python` | Canny edge detection, polygon fill |
| `pillow` | Image I/O |
| `pydantic` + `pydantic-settings` | Request/response schemas, env config |
| `httpx` | HTTP client for URL image loading |
