# AI Cinematic Spatial System (AICSS)

> Convert a 2D cinematic image into a depth-layered, pseudo-3D spatial scene — objects segmented by edge-aware masks, arranged in Z-depth layers, rendered as interactive billboards in a Three.js viewport.

---

## Architecture

```
User uploads image
        │
        ▼
┌──────────────────────────────────────────────────────────────┐
│  Frontend  (React + Vite + Tailwind)                        │
│                                                              │
│  Toolbar  →  ImageCanvas  →  LayerSelector  →  SplitControls│
│                           (2D SVG)          (palette)        │
│                                                              │
│  Viewer3D (Three.js)  ←  billboard RGBA textures            │
└──────────────────────────────────────────────────────────────┘
        │  POST /api/aicss/analyze
        ▼
┌──────────────────────────────────────────────────────────────┐
│  Backend  (FastAPI + Uvicorn)                               │
│                                                              │
│  /analyze          — full pipeline                          │
│  /billboard        — polygon-cropped RGBA cutout            │
│  /multiface        — 6-face pseudo-3D textures              │
└──────────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────────┐
│  ML Models (PyTorch, loaded once at startup)                 │
│                                                              │
│  DepthAnything V2-Large    ← depth map                      │
│  Grounding DINO Base       ← detection boxes + scores        │
│  SAM2.1 ViT-L              ← instance masks                 │
│                                                              │
│  Post-processing: Canny edge refinement → polygon contours    │
└──────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
.
├── frontend/                    # React 19 + TypeScript + Vite + Tailwind
│   ├── src/
│   │   ├── App.tsx              # Root layout: Toolbar + 2D/3D split panes
│   │   ├── main.tsx             # React mount
│   │   ├── index.css            # Global styles (Tailwind base)
│   │   ├── components/
│   │   │   ├── ImageCanvas.tsx  # 2D SVG canvas — polygon/rect masks, layer colors
│   │   │   ├── LayerSelector.tsx# 15-color swatch palette for depth layers
│   │   │   ├── SplitControls.tsx# "Split Image" → generate billboard RGBA textures
│   │   │   └── Viewer3D.tsx     # Three.js canvas — billboards in Z-depth 3D space
│   │   ├── services/
│   │   │   └── aicssService.ts  # Axios client for all backend endpoints
│   │   ├── store/
│   │   │   └── useAppStore.ts   # Zustand global store
│   │   └── types/
│   │       └── index.ts         # TypeScript interfaces
│   ├── dist/                    # Production build (gitignored)
│   ├── node_modules/            # (gitignored)
│   ├── package.json
│   ├── vite.config.ts
│   └── README.md
│
├── backend/                     # Python 3.10+ · FastAPI · PyTorch
│   ├── app/
│   │   ├── main.py              # FastAPI app, CORS, lifespan (model loading)
│   │   ├── config.py            # All settings via AICSS_* env vars
│   │   ├── endpoints.py         # All REST endpoints (analyze, billboard, ...)
│   │   ├── models/
│   │   │   ├── model_manager.py # Singleton: loads all 3 ML models at startup
│   │   │   ├── depth_loader.py  # DepthAnything V2 wrapper
│   │   │   ├── grounding_dino_loader.py  # Grounding DINO wrapper
│   │   │   └── sam2_loader.py   # SAM2 + refine_mask_edges + extract_polygon_from_mask
│   │   └── utils/
│   │       ├── image_utils.py   # base64/PIL helpers, depth scaling, RGBA builder
│   │       └── spatial_utils.py # Layer bucketing, scene graph builder
│   ├── thirdparty/              # Local SAM2 builds (gitignored)
│   ├── sam2.1_l.pt             # SAM2.1 ViT-L checkpoint (gitignored, ~449 MB)
│   ├── requirements.txt
│   ├── run.py                   # `python run.py` launcher
│   ├── README.md
│   └── SPEC.md
│
├── .gitignore                   # Covers frontend dist/node_modules, backend .venv/sam2.1_*.pt
└── README.md                    # (this file)
```

---

## Pipeline: From Image to 3D Scene

### Step 1 — Depth Estimation
`DepthAnything V2 Large` takes the full image and produces a **depth map** (H×W, normalized 0–1), scaled to approximate meters (default scale = 50 m).

### Step 2 — Object Detection
`Grounding DINO Base` takes a user-supplied segmentation prompt (e.g. `"person,car,building,tree"`) and returns **bounding boxes + confidence scores** for each detected category.

### Step 3 — Instance Segmentation
`SAM2.1 ViT-L` takes each detection box as a prompt and produces a **pixel-accurate binary mask** per object.

### Step 4 — Edge Refinement (Post-processing)
The SAM2 mask contour is extracted and **snapped to nearby Canny edges** (max snap distance = 8 px). This tightens the polygon boundary to match the object's actual silhouette. The result is a simplified polygon (`arc_len * 0.002` Douglas-Peucker tolerance) returned as `[[x_norm, y_norm], ...]`.

### Step 5 — Spatial Layer Assignment
Each object's **median depth** within its mask is computed from the depth map. Objects are bucketed into:

| Layer      | Z range |
|------------|---------|
| foreground | 0 – 5 m |
| midground  | 5 – 15 m |
| background | 15 – 50 m |
| sky        | 50 m+ |

### Step 6 — Scene Graph
Spatial relations (`leftOf`, `rightOf`, `inFrontOf`, `behind`, `above`, `below`) are derived from bounding-box centroid offsets and depth deltas between all object pairs.

### Step 7 — Billboard Generation
When the user clicks **Split Image**, each assigned object is sent to `/api/aicss/billboard`. The backend crops the image to the polygon's tight bounding box and uses the polygon mask to produce a **transparent RGBA PNG** (background outside the mask = alpha 0).

### Step 8 — 3D Rendering
The Three.js `Viewer3D` places each object's billboard as a plane in world space:
- **X**: derived from bbox center
- **Y**: derived from bbox center (Y-flipped for 3D)
- **Z**: derived from median depth, mapped to –5 (near) … +5 (far)

---

## API Reference

Base URL: `http://localhost:8000` (configurable via `VITE_AICSS_BACKEND`)

### Full Pipeline
```
POST /api/aicss/analyze
Body:   { "imageUrl": "data:image/...", "segmentationPrompt": "person,car,tree", "shotId": "shot_001" }
Reply:  { analysisId, depthMapUrl, objects[], layers[], sceneGraph }
```

### Billboard (RGBA Cutout)
```
POST /api/aicss/billboard
Body:   { "imageUrl": "...", "objectId": "...", "boundingBox": {x,y,w,h}, "polygon": [[x,y],...] }
Reply:  { "billboardUrl": "data:image/png;base64,..." }
```
`polygon` overrides `boundingBox` when provided (3+ points). Falls back to rectangle if empty.

### 6-Face Pseudo-3D
```
POST /api/aicss/multiface
Body:   { "imageUrl": "...", "objectId": "...", "boundingBox": {...}, "polygon": [...] }
Reply:  { "faces": { front, back, left, right, top, bottom } }
```

### Depth Only / Segment Only / Layers / Scene Graph
```
POST /api/aicss/depth        → { depthMapUrl }
POST /api/aicss/segment      → { objects[] }
POST /api/aicss/layers       → { layers[] }
POST /api/aicss/scene-graph  → { sceneGraph }
GET  /health                 → { status, device, models_loaded }
```

Interactive docs: `http://localhost:8000/docs` (Swagger UI) or `http://localhost:8000/redoc` (ReDoc).

---

## Configuration

### Frontend

| File | Variable | Default | Meaning |
|---|---|---|---|
| `frontend/.env` | `VITE_AICSS_BACKEND` | `http://localhost:8000` | Backend base URL |

### Backend

| Environment Variable | Default | Meaning |
|---|---|---|
| `AICSS_HOST` | `0.0.0.0` | Server bind address |
| `AICSS_PORT` | `8000` | Server port |
| `AICSS_DEVICE` | `cuda` | `cuda` or `cpu` |
| `AICSS_DEPTH_MODEL` | `depth-anything/Depth-Anything-V2-Large-hf` | HuggingFace model ID |
| `AICSS_GROUNDING_DINO_MODEL` | `IDEA-Research/grounding-dino-base` | HuggingFace model ID |
| `AICSS_SAM2_MODEL_SIZE` | `vit_l` | SAM2 size: `vit_l`, `vit_b`, `vit_s`, `vit_t` |
| `AICSS_SEGMENTATION_PROMPT` | `person,car,building,tree,...` | Comma-separated classes to detect |
| `AICSS_HF_TOKEN` | _(empty)_ | HuggingFace token for gated models |

---

## Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+
- CUDA 12.x (for GPU acceleration)

### 1 — Backend

```bash
cd backend

# Create venv
python -m venv .venv

# Activate (PowerShell)
.\.venv\Scripts\Activate.ps1

# Install PyTorch (CUDA 12.1) + all deps
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt

# Download SAM2 checkpoint (place sam2.1_l.pt in backend/)
# https://github.com/facebookresearch/segment-anything-2

# Start server (models load on startup)
python run.py
# or: .venv\Scripts\python run.py
```

### 2 — Frontend

```bash
cd frontend

npm install
npm run dev      # http://localhost:5173
```

### 3 — Use

1. Open `http://localhost:5173`
2. Click **Import Image** and select a photo
3. Optionally edit the segmentation prompt (e.g. `"person,tree,building"`)
4. Click **Analyze** — wait for depth map + masks + layers
5. Assign objects to depth layers by clicking them + a color swatch
6. Click **Split Image** — billboards are generated
7. Switch to **Camera** mode to orbit the 3D scene

---

## Model Disk Space

| Model | Approx. Size |
|-------|-------------|
| DepthAnything V2 Large | ~600 MB |
| Grounding DINO Base | ~400 MB |
| SAM2.1 ViT-L | ~449 MB |
| **Total (excluding cache)** | **~1.4 GB** |

HuggingFace download cache (`~/.cache/huggingface/`) and thirdparty SAM2 builds are gitignored.

---

## Key Data Structures

```typescript
// Polygon contour — edge-refined, normalized 0-1
type PolygonPoint = [number, number];

// Single detected object
interface DetectedObject {
  id: string;
  classLabel: string;
  depth: number;              // median depth in meters
  boundingBox: BoundingBox;   // {x, y, w, h} normalized 0-1
  maskDataUrl: string;        // base64 PNG mask
  polygon: PolygonPoint[];     // edge-refined contour (Douglas-Peucker simplified)
  layer: string;              // "foreground" | "midground" | "background" | "sky"
}

// Full analysis response
interface AicssResult {
  analysisId: string;
  depthMapUrl: string;
  objects: DetectedObject[];
  layers: SpatialLayer[];
  sceneGraph: SceneGraph;
}
```

---

## Frontend State (Zustand)

`useAppStore` is the single source of truth:

| Key | Type | Purpose |
|---|---|---|
| `originalImageUrl` | `string` | Full data URL of imported image |
| `imageWidth / imageHeight` | `number` | Original pixel dimensions |
| `analysisResult` | `AicssResult \| null` | Full pipeline response |
| `imageMode` | `'depth' \| 'original'` | 2D panel background |
| `assignments` | `Record<objectId, colorIndex>` | Object → layer color |
| `selectedLayerIndex` | `number \| null` | Active color swatch |
| `billboardAssets` | `Record<objectId, BillboardAsset>` | RGBA textures from backend |
| `editMode` | `'director' \| 'camera'` | Director = assign layers; Camera = move billboards |
| `past / future` | `HistoryEntry[]` | Undo/redo stack for assignments |
