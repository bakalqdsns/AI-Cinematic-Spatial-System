# AICSS Backend

FastAPI inference service for the AI Cinematic Spatial System. It exposes the runtime APIs for depth estimation, segmentation, spatial layering, billboard generation, multiface texture generation, and masked inpaint.

---

## Responsibilities

The backend is responsible for:

- loading all ML models at startup
- receiving image or mask payloads from the frontend
- generating depth maps and segmented objects
- deriving spatial layers and scene graph relations
- creating transparent RGBA billboard cutouts
- forwarding masked inpaint requests to DashScope

The actual runtime behavior is defined by:

- `app/config.py`
- `app/endpoints.py`
- `app/main.py`

---

## Tech Stack

- Python 3.10+
- FastAPI
- Uvicorn
- PyTorch + TorchVision
- Transformers
- OpenCV
- Pillow
- NumPy
- DashScope SDK

---

## Directory Guide

```text
backend/
├── app/
│   ├── main.py                  FastAPI app, CORS, startup lifecycle
│   ├── config.py                all AICSS_* settings
│   ├── endpoints.py             API schemas and handlers
│   ├── models/
│   │   ├── model_manager.py     model lifecycle singleton
│   │   ├── depth_loader.py      DepthAnything wrapper
│   │   ├── grounding_dino_loader.py
│   │   └── sam2_loader.py       SAM2 inference and contour refinement
│   └── utils/
│       ├── image_utils.py       base64, PIL, depth helpers
│       ├── spatial_utils.py     layer and scene-graph helpers
│       ├── vlm_utils.py         DashScope VLM integration
│       └── inpaint_utils.py     DashScope inpaint integration
├── requirements.txt
├── run.py                       recommended launcher
├── README.md
└── SPEC.md                      older spec, not fully aligned with runtime
```

---

## Prerequisites

- Python 3.10+
- enough disk space for model caches and checkpoints
- CUDA 12.x recommended for practical inference speed
- DashScope API access for VLM and inpaint workflows

---

## Setup

### 1. Create a virtual environment

```bash
cd backend
python -m venv .venv
```

Activate it:

```bash
# PowerShell
.\.venv\Scripts\Activate.ps1

# CMD
.\.venv\Scripts\activate.bat

# Bash / Git Bash / WSL
source .venv/bin/activate
```

### 2. Install dependencies

GPU example:

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
```

CPU-only example:

```bash
pip install -r requirements.txt
```

### 3. Prepare model assets

#### SAM2 checkpoint

The `AICSS_SAM2_MODEL_SIZE` setting must match the checkpoint file placed under the backend cache path used by the app.

Runtime default:

- `AICSS_SAM2_MODEL_SIZE=vit_l`
- expected checkpoint family: `sam2.1_l.pt`

Common mappings:

| Setting | Checkpoint |
|---|---|
| `vit_l` | `sam2.1_l.pt` |
| `vit_b` | `sam2.1_b.pt` |
| `vit_s` | `sam2.1_s.pt` |
| `vit_t` | `sam2.1_t.pt` |

Download source:
- [Segment Anything 2 releases](https://github.com/facebookresearch/segment-anything-2/releases)

#### HuggingFace models

The app redirects HuggingFace caches into `backend/.cache/` via `app/config.py`.

You may choose to pre-download the models before the first launch:

```bash
python -c "from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor; AutoProcessor.from_pretrained('IDEA-Research/grounding-dino-base'); AutoModelForZeroShotObjectDetection.from_pretrained('IDEA-Research/grounding-dino-base')"

python -c "from transformers import AutoModelForDepthEstimation, AutoImageProcessor; AutoImageProcessor.from_pretrained('depth-anything/Depth-Anything-V2-Large-hf'); AutoModelForDepthEstimation.from_pretrained('depth-anything/Depth-Anything-V2-Large-hf')"
```

---

## Running the Server

Recommended:

```bash
python run.py
```

Other common variants:

```bash
python run.py --cpu
python run.py --port 8080
```

Direct Uvicorn also works, but `run.py` is the recommended entry because it aligns with the repo workflow:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

On startup, FastAPI lifespan tries to preload all models. If model loading fails, the service may still start, but inference endpoints can fail later.

Useful URLs after startup:

- `http://localhost:8000/health`
- `http://localhost:8000/docs`
- `http://localhost:8000/redoc`

---

## Configuration

All settings are defined in `app/config.py` and use the `AICSS_` prefix.

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `AICSS_HOST` | `0.0.0.0` | bind host |
| `AICSS_PORT` | `8000` | bind port |
| `AICSS_RELOAD` | `true` | enable auto reload |
| `AICSS_DEVICE` | `cuda` | `cuda` or `cpu` |
| `AICSS_HF_TOKEN` | empty | HuggingFace token |
| `AICSS_DEPTH_MODEL` | `depth-anything/Depth-Anything-V2-Large-hf` | depth model ID |
| `AICSS_GROUNDING_DINO_MODEL` | `IDEA-Research/grounding-dino-base` | detection model ID |
| `AICSS_SAM2_MODEL_SIZE` | `vit_l` | SAM2 size selector |
| `AICSS_SEGMENTATION_PROMPT` | built-in default list | fallback segmentation prompt |
| `AICSS_DASHSCOPE_API_KEY` | empty | server fallback DashScope key |
| `AICSS_DASHSCOPE_MODEL` | `wanx2.1-imageedit` | inpaint model name |
| `AICSS_DASHSCOPE_FUNCTION` | `description_edit_with_mask` | DashScope function |
| `AICSS_INPAINT_TIMEOUT` | `120` | inpaint timeout in seconds |

### Example `.env`

```env
AICSS_DEVICE=cuda
AICSS_PORT=8000
AICSS_RELOAD=true
AICSS_SAM2_MODEL_SIZE=vit_l
AICSS_DASHSCOPE_API_KEY=your_dashscope_key
```

Note: the repository currently does not ship a `backend/.env.example` unless you add one explicitly.

---

## API Endpoints

All API endpoints are mounted under `/api/aicss`.

### `POST /api/aicss/analyze`

Runs the full pipeline.

Request body:

```json
{
  "imageUrl": "data:image/png;base64,...",
  "shotId": "shot_001",
  "apiKey": "your_dashscope_key"
}
```

Notes:
- `apiKey` is required by the current request model.
- the backend uses it for DashScope VLM-based class and scene detection.
- the response also includes `vlmDetectedClasses` and `vlmDetectedScene` when available.

### `POST /api/aicss/depth`

Depth-only request.

```json
{
  "imageUrl": "data:image/png;base64,..."
}
```

### `POST /api/aicss/segment`

Segmentation-only request.

```json
{
  "imageUrl": "data:image/png;base64,...",
  "apiKey": "your_dashscope_key"
}
```

### `POST /api/aicss/layers`

Rebuilds depth layers from a depth map and object list.

```json
{
  "depthMap": "data:image/png;base64,...",
  "objects": [],
  "imageWidth": 1024,
  "imageHeight": 768
}
```

### `POST /api/aicss/scene-graph`

Rebuilds the spatial graph.

```json
{
  "shotId": "shot_001",
  "objects": []
}
```

### `POST /api/aicss/billboard`

Generates a transparent RGBA cutout for one object.

```json
{
  "imageUrl": "data:image/png;base64,...",
  "objectId": "obj_person_0",
  "boundingBox": { "x": 0.12, "y": 0.31, "w": 0.08, "h": 0.55 },
  "polygon": [[0.12, 0.31], [0.20, 0.31], [0.20, 0.86], [0.12, 0.86]]
}
```

Notes:
- `polygon` is optional.
- when omitted or empty, the backend falls back to the bounding box.

### `POST /api/aicss/multiface`

Generates six pseudo-3D faces.

```json
{
  "imageUrl": "data:image/png;base64,...",
  "objectId": "obj_person_0",
  "boundingBox": { "x": 0.12, "y": 0.31, "w": 0.08, "h": 0.55 },
  "polygon": [[0.12, 0.31], [0.20, 0.31], [0.20, 0.86], [0.12, 0.86]]
}
```

### `POST /api/aicss/inpaint`

Performs masked image editing through DashScope.

```json
{
  "imageUrl": "data:image/png;base64,...",
  "maskDataUrl": "data:image/png;base64,...",
  "prompt": "remove the person and reconstruct the background",
  "apiKey": "your_dashscope_key"
}
```

Notes:
- `apiKey` is optional only if `AICSS_DASHSCOPE_API_KEY` is configured on the server.
- this endpoint is implemented in the codebase but was previously undocumented.

### `GET /health`

Returns:

```json
{
  "status": "ok",
  "device": "cuda",
  "models_loaded": true
}
```

---

## DashScope Usage

The backend uses DashScope in two places:

1. `vlm_utils.py`
   - scene recognition
   - class extraction for segmentation prompt generation
2. `inpaint_utils.py`
   - masked image editing

Implications for developers:

- if no server-side `AICSS_DASHSCOPE_API_KEY` is configured, the frontend must provide an API key for supported requests
- `analyze` and `segment` depend on VLM-assisted detection flow in the current implementation
- network latency and provider-side limits can affect perceived response time

---

## Logging and Runtime Behavior

- logs are written to `backend/logs/aicss.log`
- model loading happens during FastAPI lifespan
- CORS is currently configured with `allow_origins=["*"]` for development convenience
- backend root is injected into `sys.path` in `app/main.py` to support `from app...` imports

---

## Known Issues and Current Limitations

- `SPEC.md` does not fully match the runtime code and should not be treated as the primary source of truth.
- `app/utils/inpaint_utils.py` contains hardcoded local debug output paths that are not portable.
- there is no automated backend test suite documented in this repository.
- there is no production deployment or Docker guidance yet.
- model startup can be slow on CPU-only environments.

---

## Troubleshooting

### Backend starts but inference fails
- verify that required model weights are available
- verify the SAM2 checkpoint filename matches `AICSS_SAM2_MODEL_SIZE`
- inspect `backend/logs/aicss.log`
- check `http://localhost:8000/health`

### `analyze` or `segment` fails unexpectedly
- confirm a valid DashScope API key is provided
- confirm outbound network access to DashScope is available
- review request payload fields against `app/endpoints.py`

### Very slow startup
- expected on first run or CPU-only mode
- pre-download HuggingFace models to reduce cold-start time

---

## Related Docs

- repository overview: `../README.md`
- frontend development guide: `../frontend/README.md`
- backend runtime config: `app/config.py`
- backend API schemas: `app/endpoints.py`
