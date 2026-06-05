# AI Cinematic Spatial System (AICSS)

> Convert a 2D image into a depth-layered pseudo-3D scene, segment foreground objects, generate transparent billboard textures, and preview the result in an interactive Three.js workspace.

**[中文版](./README-zh.md)**

---

## What This Project Does

AICSS is a full-stack toolchain for turning a single image into a layered spatial composition:

- the frontend imports and normalizes an image to a 1920×1080 working canvas
- the backend estimates depth, detects objects, segments masks, and derives spatial layers
- the frontend lets users inspect masks, assign color layers, generate billboard cutouts, and preview the result in 3D
- optional DashScope-powered VLM detection and inpaint flows improve object understanding and patch generation

This repository contains both the browser UI and the inference backend.

---

## Architecture

```text
User imports image
      │
      ▼
┌──────────────────────────────────────────────────────────────┐
│ Frontend (React + Vite + Zustand + Three.js)                │
│                                                              │
│ Toolbar → ImageCanvas → LayerSelector → SplitControls       │
│                2D overlay        layer assignment            │
│                                                              │
│ Viewer3D renders generated RGBA billboard textures          │
└──────────────────────────────────────────────────────────────┘
      │
      │ POST /api/aicss/analyze
      ▼
┌──────────────────────────────────────────────────────────────┐
│ Backend (FastAPI + PyTorch)                                  │
│                                                              │
│ analyze      full pipeline                                   │
│ billboard    polygon-aware RGBA cutout                       │
│ multiface    6-face pseudo-3D textures                       │
│ inpaint      masked image edit via DashScope                 │
└──────────────────────────────────────────────────────────────┘
      │
      ▼
┌──────────────────────────────────────────────────────────────┐
│ Models and post-processing                                   │
│                                                              │
│ DepthAnything V2      depth estimation                       │
│ Grounding DINO        object detection                       │
│ SAM2                  instance masks                         │
│ Qwen-VL               scene/category hints                   │
│ OpenCV post-process   contour refinement                     │
└──────────────────────────────────────────────────────────────┘
```

---

## Repository Layout

```text
.
├── frontend/                     React 19 + TypeScript + Vite app
│   ├── src/
│   │   ├── App.tsx              root layout and import flow
│   │   ├── components/          2D/3D UI components
│   │   ├── services/            backend API client
│   │   ├── store/               Zustand state store
│   │   ├── types/               shared frontend types
│   │   └── utils/               IndexedDB persistence and helpers
│   ├── .env.example             frontend environment template
│   ├── package.json
│   └── README.md
│
├── backend/                      FastAPI inference service
│   ├── app/
│   │   ├── main.py              app entry, CORS, lifespan
│   │   ├── config.py            all AICSS_* settings
│   │   ├── endpoints.py         REST endpoints and schemas
│   │   ├── models/              model loaders and manager
│   │   └── utils/               image, spatial, VLM, inpaint helpers
│   ├── requirements.txt
│   ├── run.py                   recommended backend launcher
│   ├── README.md
│   └── SPEC.md                  older backend spec, currently not fully aligned
│
├── README.md                     this file
└── README-zh.md                  Chinese version
```

---

## End-to-End Flow

1. Import an image in the frontend.
2. The frontend resizes it to a 1920×1080 working surface.
3. Click `Analyze` to call `POST /api/aicss/analyze`.
4. The backend:
   - loads the image
   - predicts a depth map
   - uses DashScope VLM to infer scene/object classes
   - runs Grounding DINO + SAM2 for segmentation
   - refines contours into polygons
   - assigns depth layers and builds a scene graph
5. The frontend displays masks in 2D and lets the user assign color layers.
6. Click `Split Image` to call `POST /api/aicss/billboard` for selected objects.
7. The generated RGBA assets are previewed in `Viewer3D`.
8. Optional inpaint uses `POST /api/aicss/inpaint` for masked edits.

---

## Tech Stack

### Frontend
- React 19
- TypeScript 6
- Vite 8
- Tailwind CSS v4
- Zustand 5
- Three.js + `@react-three/fiber` + `@react-three/drei`
- Axios
- IndexedDB for local session persistence

### Backend
- Python 3.10+
- FastAPI + Uvicorn
- PyTorch + TorchVision
- Transformers
- OpenCV + Pillow + NumPy
- DashScope APIs for VLM and inpaint

---

## Local Development Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+
- npm 9+
- CUDA 12.x recommended for usable inference speed
- DashScope API key for `analyze`, `segment`, and inpaint-related workflows

### 1. Start the backend

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
python run.py
```

If you do not have CUDA, install dependencies without the CUDA wheel and run:

```bash
python run.py --cpu
```

### 2. Configure the frontend

```bash
cd frontend
copy .env.example .env
npm install
npm run dev
```

The default frontend setting is:

```env
VITE_AICSS_BACKEND=http://localhost:8000
```

### 3. Verify the system

- backend health: `http://localhost:8000/health`
- backend docs: `http://localhost:8000/docs`
- frontend dev server: `http://localhost:5173`

### 4. Use the app

1. Open the frontend in a browser.
2. Paste or type a DashScope API key in the toolbar.
3. Import an image.
4. Click `Analyze`.
5. Select layers and assign objects.
6. Click `Split Image`.
7. Inspect the billboards in the 3D viewer.

---

## Configuration Summary

### Frontend

| Variable | Default | Purpose |
|---|---|---|
| `VITE_AICSS_BACKEND` | `http://localhost:8000` | Backend base URL |

### Backend

Actual backend settings are defined in `backend/app/config.py`.

| Variable | Default | Purpose |
|---|---|---|
| `AICSS_HOST` | `0.0.0.0` | Bind host |
| `AICSS_PORT` | `8000` | Bind port |
| `AICSS_RELOAD` | `true` | Auto reload in development |
| `AICSS_DEVICE` | `cuda` | `cuda` or `cpu` |
| `AICSS_HF_TOKEN` | empty | HuggingFace token |
| `AICSS_DEPTH_MODEL` | `depth-anything/Depth-Anything-V2-Large-hf` | Depth model ID |
| `AICSS_GROUNDING_DINO_MODEL` | `IDEA-Research/grounding-dino-base` | Detection model ID |
| `AICSS_SAM2_MODEL_SIZE` | `vit_l` | SAM2 checkpoint size |
| `AICSS_SEGMENTATION_PROMPT` | built-in default list | fallback prompt |
| `AICSS_DASHSCOPE_API_KEY` | empty | server-side DashScope key fallback |
| `AICSS_DASHSCOPE_MODEL` | `wanx2.1-imageedit` | inpaint model |
| `AICSS_INPAINT_TIMEOUT` | `120` | inpaint timeout in seconds |

---

## API Surface

All backend endpoints are mounted under `/api/aicss`.

| Method | Path | Notes |
|---|---|---|
| `POST` | `/analyze` | full pipeline, requires `imageUrl`, `shotId`, `apiKey` |
| `POST` | `/depth` | depth only |
| `POST` | `/segment` | segmentation only, requires `imageUrl`, `apiKey` |
| `POST` | `/layers` | rebuild layers from `depthMap` and objects |
| `POST` | `/scene-graph` | rebuild scene graph |
| `POST` | `/billboard` | generate transparent cutout |
| `POST` | `/multiface` | generate 6 pseudo-3D faces |
| `POST` | `/inpaint` | masked image edit, `apiKey` optional if env var exists |
| `GET` | `/health` | runtime status |

For exact request/response schemas, use:
- `http://localhost:8000/docs`
- `backend/app/endpoints.py`
- `frontend/src/services/aicssService.ts`

---

## Development Notes

- Imported images are normalized to 1920×1080 in the frontend before analysis.
- The frontend stores the DashScope key in local state and uses it during `analyze` and inpaint requests.
- IndexedDB session restoration exists, but the current UI only restores the latest saved session path and does not expose a full session manager.
- `crop` and billboard offset related state exists in the frontend store, but the full interaction flow is not yet surfaced in the UI.
- Backend model loading happens during app startup via FastAPI lifespan.

---

## Known Issues and Risks

- `backend/SPEC.md` is not fully aligned with the running code.
- `backend/app/utils/inpaint_utils.py` contains hardcoded local debug paths that should be removed or replaced.
- There is no backend `.env.example` in the current repository.
- There are no automated tests or deployment docs in the current codebase.
- CORS is currently open to all origins for development convenience.

---

## Recommended Reading Order

- Start here: `README.md`
- Backend setup and API details: `backend/README.md`
- Frontend structure and workflow: `frontend/README.md`
- Runtime truth for backend config: `backend/app/config.py`
- Runtime truth for backend endpoints: `backend/app/endpoints.py`

---

## Current Documentation Scope

This documentation now focuses on local development and codebase understanding. It does not yet include:

- production deployment guidance
- Docker setup
- CI/CD instructions
- automated testing workflows

Those should be added separately when the project is ready for handoff or release.
