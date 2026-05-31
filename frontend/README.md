# AICSS Frontend

AI Cinematic Spatial System — Web UI for real-time scene depth analysis, object segmentation, and pseudo-3D billboard rendering.

## Tech Stack

| Category | Library |
|---|---|
| Framework | React 19 + TypeScript |
| Bundler | Vite 8 |
| 3D Rendering | Three.js + `@react-three/fiber` + `@react-three/drei` |
| State Management | Zustand |
| Styling | Tailwind CSS v4 |
| HTTP Client | Axios |
| Icons | Lucide React |

## Project Structure

```
src/
├── App.tsx                  # Root layout: Toolbar + 2D/3D split panes + resize handle
├── main.tsx                # React mount
├── index.css               # Global styles (Tailwind base)
├── components/
│   ├── ImageCanvas.tsx     # 2D SVG overlay: polygon/rect masks, object highlights, layer coloring
│   ├── LayerSelector.tsx    # 15-color swatch palette; click to select active layer for assignment
│   ├── SplitControls.tsx    # "Split Image" → billboard generation; progress / error display
│   └── Viewer3D.tsx        # Three.js canvas: billboard meshes in 3D world space
├── services/
│   └── aicssService.ts     # Axios wrapper around backend REST API
├── store/
│   └── useAppStore.ts      # Zustand global store (image, analysis result, assignments, history)
└── types/
    └── index.ts            # Shared TypeScript interfaces (DetectedObject, SpatialLayer, etc.)
```

## State Management (Zustand)

`useAppStore` is the single source of truth for the entire UI:

| State key | Type | Purpose |
|---|---|---|
| `originalImageUrl` | `string` | Full data URL of the imported image |
| `originalImageBase64` | `string` | Base64 without prefix (for API payload) |
| `imageWidth / imageHeight` | `number` | Original image dimensions in pixels |
| `analysisResult` | `AicssResult \| null` | Full pipeline response: depth map, objects, layers, scene graph |
| `imageMode` | `'depth' \| 'original'` | 2D panel background: depth map or original photo |
| `assignments` | `Record<objectId, colorIndex>` | Maps each detected object to a layer color |
| `selectedLayerIndex` | `number \| null` | Currently active color swatch (0-14) |
| `selectedObjectId` | `string \| null` | Object highlighted on the 2D canvas |
| `billboardAssets` | `Record<objectId, BillboardAsset>` | RGBA textures fetched from `/api/aicss/billboard` |
| `editMode` | `'director' \| 'camera'` | Director = assign objects to layers; Camera = adjust billboard positions |
| `past / future` | `HistoryEntry[]` | Undo/redo stack for layer assignments |

## Key Data Flow

```
Import Image
    │
    ▼
POST /api/aicss/analyze          (analyzeImage in aicssService)
    │
    ├─► Depth-Anything-V2         → depthMapUrl
    ├─► Grounding DINO            → boxes + scores
    ├─► SAM2 + Canny edge refine  → object masks + polygon contours
    ├─► Spatial layering           → layers[]
    └─► Scene graph               → sceneGraph{}

    ▼
analysisResult → displayed in ImageCanvas (2D panel)
              → displayed in Viewer3D  (3D panel)
              → objects assigned to layers via LayerSelector

Split Image button
    │
    ▼
POST /api/aicss/billboard        (generateBillboard)
    │
    └─► Crop using polygon mask   → RGBA PNG → Viewer3D texture
```

## API Endpoints

All calls go to `http://localhost:8000` by default (configurable via `VITE_AICSS_BACKEND`).

| Method | Path | Payload | Response |
|---|---|---|---|
| `POST` | `/api/aicss/analyze` | `{imageUrl, segmentationPrompt, shotId}` | `AicssResult` |
| `POST` | `/api/aicss/billboard` | `{imageUrl, objectId, boundingBox, polygon}` | `{billboardUrl}` |
| `POST` | `/api/aicss/multiface` | `{imageUrl, objectId, boundingBox, polygon}` | `{faces: {front, back, left, right, top, bottom}}` |
| `GET` | `/health` | — | `{status, device, models_loaded}` |

## Key TypeScript Types

```typescript
// Each detected object carries both bbox + polygon contour
interface DetectedObject {
  id: string;
  classLabel: string;
  depth: number;           // median depth in meters
  boundingBox: BoundingBox; // {x, y, w, h} normalized 0-1
  maskDataUrl: string;      // base64 PNG mask
  polygon: [number, number][]; // edge-refined contour, 0-1 range
  layer: string;            // "near" | "mid" | "far"
}

// Full pipeline result
interface AicssResult {
  analysisId: string;
  depthMapUrl: string;
  objects: DetectedObject[];
  layers: SpatialLayer[];
  sceneGraph: SceneGraph;
}
```

## Running Locally

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173
```

The frontend assumes the backend is running at `http://localhost:8000`. See the [backend README](../backend/README.md) for setup instructions.

## Scripts

| Command | Purpose |
|---|---|
| `npm run dev` | Start Vite dev server with HMR |
| `npm run build` | Type-check + production build to `dist/` |
| `npm run preview` | Serve the production build locally |
