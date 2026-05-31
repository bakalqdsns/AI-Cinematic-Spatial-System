# AICSS Backend — Specification

## Overview

Python FastAPI backend serving the AICSS (AI Cinematic Spatial System) inference pipeline.
Receives an image URL from the CineGen frontend, runs depth estimation + semantic segmentation,
and returns structured spatial data (depth maps, object masks, spatial layers, scene graph).

## Architecture

```
Frontend (CineGen)  →  FastAPI  →  PyTorch Models
                                      ├── DepthAnything V2  (depth estimation)
                                      ├── Grounding DINO   (object detection)
                                      └── SAM2            (instance segmentation)
```

## API Endpoints

All endpoints accept JSON with `imageUrl` (URL string) unless noted.
All responses are JSON.

### POST /api/aicss/analyze
Full pipeline — runs all steps and returns complete AicssData.

**Request:**
```json
{ "imageUrl": "https://...", "shotId": "shot_001" }
```

**Response:**
```json
{
  "analysisId": "aicss_xxx",
  "depthMapUrl": "data:image/png;base64,...",
  "layers": [ { "id": "...", "name": "foreground", "zMin": 0, "zMax": 5, "objects": [...] } ],
  "objects": [ { "id": "...", "classLabel": "person", "depth": 3.5, "boundingBox": {...}, "maskDataUrl": "..." } ],
  "sceneGraph": { "shotId": "...", "nodes": [...] }
}
```

### POST /api/aicss/depth
Depth map generation via DepthAnything V2.

**Request:** `{ "imageUrl": "https://..." }`
**Response:** `{ "depthMapUrl": "data:image/png;base64,..." }`

### POST /api/aicss/segment
Object segmentation via Grounding DINO + SAM2.

**Request:** `{ "imageUrl": "https://..." }`
**Response:** `{ "objects": [ { "id": "...", "classLabel": "person", "depth": 3.5, "boundingBox": {...} } ] }`

### POST /api/aicss/layers
Build spatial layers from depth map + objects.

**Request:** `{ "depthMap": "data:image/png;base64,...", "objects": [...], "imageWidth": 1024, "imageHeight": 768 }`
**Response:** `{ "layers": [...] }`

### POST /api/aicss/scene-graph
Build spatial relationship graph from objects.

**Request:** `{ "shotId": "...", "objects": [...] }`
**Response:** `{ "sceneGraph": { "shotId": "...", "nodes": [...] } }`

### POST /api/aicss/billboard
Generate RGBA billboard texture (cutout) for an object.

**Request:** `{ "imageUrl": "...", "objectId": "...", "boundingBox": {...} }`
**Response:** `{ "billboardUrl": "data:image/png;base64,..." }`

### POST /api/aicss/multiface
Generate 6-face pseudo-3D textures for an object.

**Request:** `{ "imageUrl": "...", "objectId": "...", "boundingBox": {...} }`
**Response:** `{ "faces": { "front": "...", "back": "...", "left": "...", "right": "...", "top": "...", "bottom": "..." } }`

## Models

| Model | Purpose | Size | Source |
|-------|---------|------|--------|
| DepthAnything V2 (ViT-L) | Depth estimation | ~600MB | HuggingFace: depth-anything/.. |
| Grounding DINO (base) | Object detection | ~400MB | HuggingFace: IDEA-Research/grounding-dino-base |
| SAM2 (sam2.1_b VIT_H) | Instance segmentation | ~2.5GB | Meta SAM2 |

## Depth Buckets

| Layer | Z range |
|-------|---------|
| foreground | 0 – 5m |
| midground | 5 – 15m |
| background | 15 – 50m |
| sky | 50m+ |

## Spatial Relations

Objects are related by: `leftOf`, `rightOf`, `inFrontOf`, `behind`, `above`, `below`
Derived from bounding box overlap and depth ordering.

## Tech Stack

- **Runtime**: Python 3.10+, CUDA 12.x
- **Web**: FastAPI + Uvicorn
- **ML**: PyTorch 2.x, torchvision, transformers
- **Segmentation**: Ultralytics SAM2, Grounding DINO
- **Image**: Pillow, OpenCV, rembg (optional background removal)

## Running

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Environment Variables

```
HF_TOKEN=hf_xxx              # HuggingFace token (for gated models)
AICSS_PORT=8000             # Server port
AICSS_HOST=0.0.0.0          # Server host
DEVICE=cuda                  # cuda or cpu
SAM2_MODEL_SIZE=vit_h       # vit_h or vit_b
DEPTH_MODEL=depth-anything-v2-vitl
```
