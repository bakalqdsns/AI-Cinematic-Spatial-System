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
- the request is asynchronous — the server polls DashScope until `AICSS_INPAINT_TIMEOUT` seconds (default `120`) elapse.

### `POST /api/aicss/paper-style`

Paper-cut / illustration style transfer for a photograph. Applies bilateral filtering, colour quantisation, and Canny edge compositing. Used as the first stage of paper-diorama texture generation.

Request body:

```json
{
  "imageUrl": "data:image/png;base64,...",
  "colorLevels": 12,
  "styleStrength": 0.7,
  "edgeLow": 50,
  "edgeHigh": 150
}
```

Response:

```json
{
  "styledImageUrl": "data:image/png;base64,..."
}
```

Notes:
- `colorLevels` (3–30): lower values yield flatter paper-cut colours.
- `styleStrength` (0–1): bilateral filter strength; higher = smoother flat areas.

### `POST /api/aicss/paper-diorama`

Generate a complete paper-diorama texture set for a single object cut out by `maskDataUrl`. Returns five images for downstream 3D rendering.

Request body:

```json
{
  "imageUrl": "data:image/png;base64,...",
  "maskDataUrl": "data:image/png;base64,...",
  "thicknessMin": 1.0,
  "thicknessMax": 5.0,
  "outlineWidth": 3,
  "colorLevels": 12,
  "styleStrength": 0.7
}
```

Response (all five fields are base64 PNGs):

```json
{
  "paper_style_url":   "data:image/png;base64,...",
  "outlined_url":      "data:image/png;base64,...",
  "thickness_url":     "data:image/png;base64,...",
  "thickness_gray_url":"data:image/png;base64,...",
  "normal_map_url":    "data:image/png;base64,..."
}
```

Notes:
- `maskDataUrl` is grayscale PNG, `255` = object, `0` = background.
- `thicknessMin` / `thicknessMax` are millimetres — they only affect normalisation; the relative height field is the same.
- paper-style uses RGBA so transparent pixels stay outside the paper region.

### `POST /api/aicss/paper-layer`

Same five-field texture set as `/paper-diorama`, but applied to a **full depth layer** (RGBA image where alpha = layer membership). Unlike `/paper-diorama`, no external mask is required — the alpha channel of `layerImageUrl` is the authoritative mask. An optional `layerMaskUrl` is intersected with the alpha when supplied.

Request body:

```json
{
  "layerImageUrl": "data:image/png;base64,...",
  "layerMaskUrl": "data:image/png;base64,...",
  "thicknessMin": 1.0,
  "thicknessMax": 5.0,
  "outlineWidth": 3,
  "colorLevels": 12,
  "styleStrength": 0.7
}
```

Response: same five-field payload as `/paper-diorama`.

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

## Project Workspace (Long-term Storage + Breakpoint Continuation)

The backend persists every project's intermediate ML products and textures to disk, organised by **project ID** under `backend/.workspace/projects/`. This gives you:

- A persistent project file (folder) for each shot that survives backend restarts.
- Step-level granularity — re-run any single step without redoing the others.
- Breakpoint continuation — re-open a project, see which phases are done, and continue from there.
- Human-readable manifest (`manifest.json`) that lists every saved artifact with SHA-256 + timestamps.

### Directory Layout

```
backend/.workspace/
└── projects/
    └── 20260630_220000_shot_001/
        ├── manifest.json           ← index + metadata (atomic rewrite)
        ├── input/
        │   └── original.png        ← original image
        ├── depth/
        │   └── depth_map.png       ← depth map
        ├── masks/
        │   ├── objects.json        ← all DetectedObject metadata
        │   └── mask_<objectId>.png ← per-object binary mask
        ├── layers/
        │   └── layer_assignments.json
        ├── scene/
        │   └── scene_graph.json
        ├── billboards/
        │   └── billboard_<objectId>.png
        ├── multiface/
        │   └── <objectId>_face_<front|back|left|right|top|bottom>.png
        ├── paper/
        │   ├── paper_style_<key>.png
        │   ├── paper_outlined_<key>.png
        │   ├── paper_thickness_<key>.png
        │   ├── paper_thickness_gray_<key>.png
        │   └── paper_normal_<key>.png
        ├── inpaint/
        │   └── inpaint_<ts>.png
        └── timeline/               (in manifest.json, not a separate folder)
```

### Manifest Schema

```json
{
  "projectId": "20260630_220000_shot_001",
  "shotId": "shot_001",
  "createdAt": "2026-06-30T22:00:00Z",
  "updatedAt": "2026-06-30T22:05:30Z",
  "imageWidth": 1920,
  "imageHeight": 1080,
  "inputHash": "sha256:abc123...",
  "artifacts": {
    "depth":   { "files": [...], "savedAt": "..." },
    "segment": { "files": [...], "savedAt": "..." },
    "layers":  { "files": [...], "savedAt": "..." },
    "paper":   { "files": [...], "savedAt": "..." }
  },
  "timeline": [
    { "phase": "analyze", "startedAt": "...", "finishedAt": "...", "durationMs": 12345 }
  ]
}
```

### Project Management Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/aicss/projects` (multipart) | Create a project, upload original image (returns `projectId`) |
| `POST` | `/api/aicss/projects/json` | Create a project with a JSON body (base64 data URL) |
| `GET` | `/api/aicss/projects` | List all projects (summary) |
| `GET` | `/api/aicss/projects/{pid}/manifest` | Read full manifest |
| `GET` | `/api/aicss/projects/{pid}/artifacts/{step}/{filename}` | Read a single artifact (PNG or JSON) |
| `POST` | `/api/aicss/projects/{pid}/checkpoint` | Record a phase-start / phase-end event in the timeline |
| `DELETE` | `/api/aicss/projects/{pid}` | Delete a project (irreversible) |

### Using `projectId` with existing endpoints

Every ML endpoint accepts an optional `projectId` field. When supplied, the endpoint writes its output artifacts into the matching project's `<step>/` directory and updates `manifest.json`.

| Endpoint | `projectId` persistence |
|---|---|
| `POST /api/aicss/analyze` | writes `depth/`, `masks/`, `layers/`, `scene/` |
| `POST /api/aicss/depth` | writes `depth/depth_map.png` |
| `POST /api/aicss/segment` | writes `masks/objects.json` + `masks/mask_<id>.png` × N |
| `POST /api/aicss/layers` | writes `layers/layer_assignments.json` |
| `POST /api/aicss/scene-graph` | writes `scene/scene_graph.json` |
| `POST /api/aicss/billboard` | writes `billboards/billboard_<id>.png` |
| `POST /api/aicss/multiface` | writes `multiface/<id>_face_<face>.png` × 6 |
| `POST /api/aicss/inpaint` | writes `inpaint/inpaint_<ts>.png` |
| `POST /api/aicss/paper-style` | writes `paper/paper_style_<key>.png` (use `layerKey` for naming) |
| `POST /api/aicss/paper-diorama` | writes 5 paper textures under `paper/` |
| `POST /api/aicss/paper-layer` | writes 5 paper textures under `paper/` (use `layerKey` for naming) |

When `projectId` is **not** supplied, endpoints behave exactly as before — backward compatible.

### Breakpoint-Continuation Example

1. User starts a project: `POST /api/aicss/projects/json` with `shotId` and `imageBase64`. Backend returns `projectId = "20260630_220000_shot_001"`.
2. Frontend passes that `projectId` to every subsequent `/analyze`, `/paper-layer`, etc. call.
3. The backend progressively fills the project's folders.
4. If the user closes the browser, on re-open the frontend calls `GET /projects/{pid}/manifest` to see which phases completed, then continues with the next phase.

### Configuration

| Env var | Default | Description |
|---|---|---|
| `AICSS_WORKSPACE_DIR` | `backend/.workspace/` | Project storage root. Subdirectory `projects/` is created automatically. |

The workspace is excluded from git via `.gitignore` (`backend/.workspace/`).

### Atomicity

- `manifest.json` is rewritten via `*.tmp` → `os.replace()` (atomic on POSIX, atomic-ish on Windows).
- Per-project `asyncio.Lock` serialises concurrent writes.
- Stale `*.tmp` files are cleaned up on store startup.

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
