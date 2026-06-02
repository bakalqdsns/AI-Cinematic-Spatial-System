# AICSS Frontend

React 19 + TypeScript web UI for the AI Cinematic Spatial System. Provides 2D mask overlay editing and 3D billboard rendering.

## Tech Stack

| Category | Library |
|---|---|
| Framework | React 19 + TypeScript 6 |
| Bundler | Vite 8 |
| 3D Rendering | Three.js + `@react-three/fiber` + `@react-three/drei` |
| State Management | Zustand 5 |
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
│   ├── ImageCanvas.tsx     # 2D SVG canvas
│   ├── LayerSelector.tsx   # 15-color swatch palette
│   ├── SplitControls.tsx   # Split button + progress/error display
│   └── Viewer3D.tsx       # Three.js canvas
├── services/
│   └── aicssService.ts    # Axios client for backend API
├── store/
│   └── useAppStore.ts     # Zustand global store
└── types/
    └── index.ts           # TypeScript interfaces
```

## App.tsx — Layout

The root component assembles three panels:

```
┌──────────────────────────────────────────────────────────────┐
│ Toolbar (fixed)                                              │
│  Import | Analyze | prompt | Undo | Redo | Director|Camera   │
├────────────────────────────┬─────────────────────────────────┤
│ Panel2D (resizable)       │ Viewer3D (flex-1)                │
│  ┌─ View toggle ───────┐  │                                 │
│  │ [Depth] [Original]  │  │   Three.js scene                 │
│  └────────────────────┘  │   billboard planes in Z-depth     │
│                            │                                 │
│  ImageCanvas (SVG)        │   OrbitControls                  │
│  polygon masks + labels    │                                 │
│                            │                                 │
│  LayerSelector            │                                 │
│  SplitControls            │                                 │
└────────────────────────────┴─────────────────────────────────┘
```

The resize handle between panels is draggable, clamped to 20–80 % split ratio.

## ImageCanvas.tsx

SVG overlay rendered on top of the background image (`<img>` element).

**Props:** `width`, `height` (canvas pixel dimensions)

**Rendering logic:**
- Iterates `analysisResult.objects`
- For each object: if `obj.polygon.length >= 3` → renders `<polygon>` with Douglas-Peucker points; otherwise renders `<rect>` fallback
- Fill: semi-transparent layer color (35 % opacity) if assigned
- Border: dashed when not selected, solid when selected
- Label text: class name + layer index
- Click → `handleObjectClick(obj, event)` in store

**Coordinate system:** all polygon points are normalized 0–1, scaled to canvas pixels at render time.

## LayerSelector.tsx

15 color swatches (`LAYER_COLORS` from `types/index.ts`). Clicking a swatch sets `selectedLayerIndex`. The next object clicked in `ImageCanvas` is assigned to that layer.

- `clearLayer(colorIndex)` — removes all assignments for that layer
- Counter shows `N / 15 used`

## SplitControls.tsx

"Split Image" button: iterates all assigned objects and calls `generateBillboard(imageUrl, obj.id, obj.boundingBox, obj.polygon)` for each. Stores the resulting RGBA base64 URLs in `billboardAssets`.

Errors are caught per-object so one failure doesn't block others.

## Viewer3D.tsx

Three.js `Canvas` with `OrbitControls`. World dimensions: `SCENE_WIDTH = 20`, `SCENE_HEIGHT = 15`.

**Billboard placement per object:**
```
posX = (bbox.cx - 0.5) * SCENE_WIDTH + (offset?.offsetX ?? 0)
posY = (1 - bbox.cy) * SCENE_HEIGHT   // Y-flip for 3D
posZ = (depth / 50) * 10 - 5          // 0 → -5 (near), 50 → +5 (far)
```

**Billboard rotation:** in director mode, billboards face the camera (billboard constraint). In camera mode, each billboard can be rotated freely.

**Texture loading:** `useEffect` loads the RGBA texture from `billboardAssets[obj.id].rgbaUrl` into a `THREE.Texture`.

**CameraController:** wraps `OrbitControls`, exposes a passive wheel listener for scroll-to-zoom.

## State Management (Zustand)

`useAppStore.ts` — single store, no slices. Key actions:

| Action | Signature | Effect |
|---|---|---|
| `setImage` | `(url, base64, w, h)` | Sets original image |
| `setAnalysisResult` | `(result)` | Stores full pipeline response |
| `setEditMode` | `('director' \| 'camera')` | Toggles interaction mode |
| `setImageMode` | `('depth' \| 'original')` | 2D panel background |
| `assignLayer` | `(objectId, colorIndex)` | Assigns object to layer |
| `clearLayer` | `(colorIndex)` | Clears all assignments for a layer |
| `pushHistory` | `()` | Saves snapshot to undo stack |
| `undo / redo` | `()` | Replaces assignments from past/future |
| `setBillboardAsset` | `(objectId, rgbaUrl)` | Stores generated RGBA texture |

Undo/redo: stores `{assignments, timestamp}` snapshots. Max 50 entries.

## API Client (aicssService.ts)

Axios instance at `http://localhost:8000` (configurable via `VITE_AICSS_BACKEND`). Timeout: 120 s.

```typescript
// Full pipeline
analyzeImage(imageUrl, segmentationPrompt, shotId): Promise<AicssResult>

// Billboard — polygon optional, falls back to bbox
generateBillboard(imageUrl, objectId, boundingBox, polygon?): Promise<string>

// 6-face textures
generateMultiface(imageUrl, objectId, boundingBox, polygon?): Promise<Record<string, string>>

// Health
checkHealth(): Promise<{ status, device, models_loaded }>
```

## Key Types

```typescript
type PolygonPoint = [number, number];           // normalized 0-1

interface DetectedObject {
  id: string;
  classLabel: string;
  depth: number;                // median meters
  boundingBox: BoundingBox;    // {x,y,w,h} 0-1
  maskDataUrl: string;         // base64 PNG mask
  polygon: PolygonPoint[];     // edge-refined contour
  layer: string;               // foreground|midground|background|sky
}

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
npm run dev       # http://localhost:5173 (HMR enabled)
npm run build     # type-check + production build → dist/
npm run preview   # serve dist/ locally
```

Requires the backend running at `http://localhost:8000` (or set `VITE_AICSS_BACKEND` in `frontend/.env`).

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `VITE_AICSS_BACKEND` | `http://localhost:8000` | Backend base URL |
