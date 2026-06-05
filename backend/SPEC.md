# AICSS Backend — Specification

This file is a lightweight backend reference. The runtime source of truth is:

- `backend/app/config.py`
- `backend/app/endpoints.py`
- `backend/app/main.py`

If this file conflicts with code, trust the code.

---

## Overview

AICSS backend is a FastAPI inference service that accepts image payloads from the frontend, runs depth estimation and segmentation workflows, derives spatial metadata, and returns image-derived scene structures for the UI.

---

## Runtime Architecture

```text
Frontend → FastAPI → Model Manager
                    ├── DepthAnything V2
                    ├── Grounding DINO
                    ├── SAM2
                    ├── DashScope VLM
                    └── DashScope Inpaint
```

---

## Effective API Endpoints

All endpoints are mounted under `/api/aicss` unless noted.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/analyze` | full pipeline |
| `POST` | `/depth` | depth-only generation |
| `POST` | `/segment` | segmentation-only generation |
| `POST` | `/layers` | rebuild spatial layers |
| `POST` | `/scene-graph` | rebuild scene graph |
| `POST` | `/billboard` | RGBA billboard cutout |
| `POST` | `/multiface` | six-face pseudo-3D texture generation |
| `POST` | `/inpaint` | masked image editing via DashScope |
| `GET` | `/health` | service health |
| `GET` | `/` | root service metadata |

---

## Request Notes

### `POST /api/aicss/analyze`

Current request model:

```json
{
  "imageUrl": "data:image/png;base64,...",
  "shotId": "shot_001",
  "apiKey": "your_dashscope_key"
}
```

Notes:
- `apiKey` is required by the current request schema.
- the response can include `vlmDetectedClasses` and `vlmDetectedScene`.

### `POST /api/aicss/segment`

Current request model:

```json
{
  "imageUrl": "data:image/png;base64,...",
  "apiKey": "your_dashscope_key"
}
```

### `POST /api/aicss/layers`

Current request model:

```json
{
  "depthMap": "data:image/png;base64,...",
  "objects": [],
  "imageWidth": 1024,
  "imageHeight": 768
}
```

### `POST /api/aicss/inpaint`

Current request model:

```json
{
  "imageUrl": "data:image/png;base64,...",
  "maskDataUrl": "data:image/png;base64,...",
  "prompt": "remove the object and reconstruct the background",
  "apiKey": "your_dashscope_key"
}
```

Notes:
- `apiKey` is optional only if `AICSS_DASHSCOPE_API_KEY` is configured on the backend.

---

## Models

| Model | Purpose | Runtime default |
|---|---|---|
| `depth-anything/Depth-Anything-V2-Large-hf` | depth estimation | enabled |
| `IDEA-Research/grounding-dino-base` | object detection | enabled |
| `SAM2` | instance segmentation | `AICSS_SAM2_MODEL_SIZE=vit_l` |
| `Qwen-VL` via DashScope | scene and class detection | used during analyze/segment flows |
| `wanx2.1-imageedit` via DashScope | masked inpaint | used for `/inpaint` |

---

## Depth Buckets

Current defaults from `app/config.py`:

| Layer | Range |
|---|---|
| foreground | 0–5 |
| midground | 5–15 |
| background | 15–50 |
| sky | 50+ |

---

## Environment Variables

The backend uses the `AICSS_` prefix.

| Variable | Default |
|---|---|
| `AICSS_HOST` | `0.0.0.0` |
| `AICSS_PORT` | `8000` |
| `AICSS_RELOAD` | `true` |
| `AICSS_DEVICE` | `cuda` |
| `AICSS_HF_TOKEN` | empty |
| `AICSS_DEPTH_MODEL` | `depth-anything/Depth-Anything-V2-Large-hf` |
| `AICSS_GROUNDING_DINO_MODEL` | `IDEA-Research/grounding-dino-base` |
| `AICSS_SAM2_MODEL_SIZE` | `vit_l` |
| `AICSS_SEGMENTATION_PROMPT` | built-in fallback string |
| `AICSS_DASHSCOPE_API_KEY` | empty |
| `AICSS_DASHSCOPE_MODEL` | `wanx2.1-imageedit` |
| `AICSS_DASHSCOPE_FUNCTION` | `description_edit_with_mask` |
| `AICSS_INPAINT_TIMEOUT` | `120` |

---

## Operational Notes

- startup preloads models through FastAPI lifespan
- logs are written to `backend/logs/aicss.log`
- CORS is open to all origins for development
- `python run.py` is the recommended launcher

---

## Known Gaps

- this file is intentionally concise and may lag behind implementation unless maintained together with code
- no deployment or Docker spec is included here
- no automated test contract is documented here
- `app/utils/inpaint_utils.py` contains hardcoded debug paths that should be cleaned up
