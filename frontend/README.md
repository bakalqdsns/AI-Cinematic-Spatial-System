# AICSS Frontend

React-based UI for the AI Cinematic Spatial System. It provides the import workflow, 2D mask inspection, layer assignment, billboard generation, optional inpaint preview, and a Three.js 3D viewer.

---

## Responsibilities

The frontend is responsible for:

- importing an image and normalizing it to a 1920×1080 working resolution
- collecting a DashScope API key from the user
- calling backend analysis and generation endpoints
- displaying polygon or rectangle mask overlays in 2D
- assigning detected objects into color-based layers
- generating billboard textures for 3D preview
- restoring the latest persisted session from IndexedDB

---

## Tech Stack

- React 19
- TypeScript 6
- Vite 8
- Tailwind CSS v4
- Zustand 5
- Axios
- Three.js + `@react-three/fiber` + `@react-three/drei`
- IndexedDB

---

## Project Structure

```text
frontend/
├── src/
│   ├── App.tsx                      root layout and top-level workflow
│   ├── main.tsx                     React bootstrap
│   ├── index.css                    global styles
│   ├── components/
│   │   ├── ImageCanvas.tsx          2D overlay view
│   │   ├── LayerSelector.tsx        color layer palette
│   │   ├── SplitControls.tsx        billboard generation and inpaint actions
│   │   ├── InpaintPreviewDialog.tsx result preview dialog
│   │   └── Viewer3D.tsx             Three.js scene viewer
│   ├── services/
│   │   └── aicssService.ts          backend API client
│   ├── store/
│   │   └── useAppStore.ts           global Zustand store
│   ├── types/
│   │   └── index.ts                 shared types and layer colors
│   └── utils/
│       ├── db.ts                    IndexedDB session persistence
│       └── resolution.ts            unused resolution helpers
├── .env.example
├── package.json
└── README.md
```

---

## Local Development

### Prerequisites
- Node.js 18+
- npm 9+
- a running backend at `http://localhost:8000` unless you override the URL

### Setup

```bash
cd frontend
copy .env.example .env
npm install
npm run dev
```

Other useful scripts:

```bash
npm run build
npm run preview
```

Default dev URL:
- `http://localhost:5173`

---

## Environment Variables

The frontend currently uses one effective environment variable in code:

| Variable | Default | Purpose |
|---|---|---|
| `VITE_AICSS_BACKEND` | `http://localhost:8000` | backend base URL |

Example `.env`:

```env
VITE_AICSS_BACKEND=http://localhost:8000
```

Note: `.env.example` currently contains a commented DashScope key example, but the running frontend actually collects the API key from the toolbar and sends it in request payloads instead of reading it from Vite env.

---

## Runtime Workflow

### 1. Image import

`App.tsx` reads an image file and renders it onto a canvas at a fixed `1920×1080` target size before storing it in Zustand.

This means:
- all later analysis requests use the normalized image
- letterboxing or pillarboxing may be introduced for source images with a different aspect ratio
- the app currently does not expose a full manual crop UI even though crop-related state exists

### 2. Analyze flow

The toolbar triggers `analyzeImage(...)` from `aicssService.ts`.

Current request shape:

```json
{
  "imageUrl": "data:image/png;base64,...",
  "shotId": "shot_001",
  "apiKey": "your_dashscope_key"
}
```

Important notes:
- the API key is entered manually in the toolbar UI
- `analyze` depends on that key in the current backend implementation
- VLM-related metadata may come back as `vlmDetectedClasses` and `vlmDetectedScene`

### 3. 2D mask overlay

`ImageCanvas.tsx` renders:
- polygons when `obj.polygon.length >= 3`
- rectangle fallback when no valid polygon exists

Objects can be clicked and assigned to one of 15 color layers.

### 4. Billboard generation

`SplitControls.tsx` iterates assigned objects and calls `POST /api/aicss/billboard` for each of them.

Generated assets are stored in:
- `billboardAssets` inside `useAppStore.ts`

### 5. 3D preview

`Viewer3D.tsx` turns generated billboard assets into textured planes in a Three.js scene.

Placement is derived from:
- bounding box center for X/Y
- object depth for Z

### 6. Inpaint flow

The frontend includes an inpaint preview dialog and calls the backend `POST /api/aicss/inpaint` endpoint from `aicssService.ts`.

This flow uses:
- the cropped object image
- an inverse mask
- a text prompt
- the same DashScope API key when provided by the user

---

## API Client

The frontend API layer lives in `src/services/aicssService.ts`.

Implemented client functions:

| Function | Endpoint |
|---|---|
| `analyzeImage` | `POST /api/aicss/analyze` |
| `generateBillboard` | `POST /api/aicss/billboard` |
| `generateMultiface` | `POST /api/aicss/multiface` |
| `inpaintImage` | `POST /api/aicss/inpaint` |
| `checkHealth` | `GET /health` |

The Axios client uses:
- base URL from `VITE_AICSS_BACKEND`
- timeout of `120000` ms

---

## State Management

Global state lives in `src/store/useAppStore.ts`.

Key state groups:
- image source and dimensions
- analysis result and error/loading state
- object-to-layer assignments
- selected object and selected layer
- billboard asset URLs
- inpaint preview state
- API key state
- undo/redo history
- crop and billboard offset placeholders

Important implementation notes:
- `dashscopeApiKey` is stored in the Zustand store
- crop-related fields exist but are not exposed as a complete user workflow
- `billboardOffsets` and `setBillboardOffset` exist in state, but the current codebase does not expose a complete authoring interaction for them

---

## Session Persistence

IndexedDB persistence lives in `src/utils/db.ts`.

Documented capabilities in code:
- save a session
- update a session
- load a session
- list sessions
- delete a session

Current UI behavior:
- on app mount, the frontend tries to restore the most recent stored session
- the current UI does not expose a session list or explicit session management panel
- restoration currently focuses on the latest session path rather than a broader workspace recovery flow

---

## Components Overview

### `App.tsx`
- top toolbar
- image import
- analyze trigger
- split-pane layout
- latest session restore

### `ImageCanvas.tsx`
- renders 2D overlay masks
- supports object selection
- visualizes polygon or rectangle shapes

### `LayerSelector.tsx`
- 15-color layer palette
- used for assignment and clearing operations

### `SplitControls.tsx`
- split image action
- progress/error handling
- inpaint-related actions

### `InpaintPreviewDialog.tsx`
- previews inpaint result before replacement

### `Viewer3D.tsx`
- renders billboard planes in 3D
- supports director/camera viewing modes

---

## Current Limitations and Risks

- the crop workflow appears only partially implemented in state and helper types
- billboard offset state exists, but no complete editing UI is exposed for it
- session persistence exists in code, but no complete session management interface is present
- the toolbar key entry is functional, but this is not a secure secret-management approach for production use
- the frontend README previously omitted `InpaintPreviewDialog.tsx` and IndexedDB behavior
- `src/utils/resolution.ts` exists but appears unused in the current UI flow

---

## Frontend / Backend Integration Checklist

Before debugging frontend behavior, verify:

1. backend is running on the expected URL
2. `VITE_AICSS_BACKEND` matches the backend origin
3. a valid DashScope API key is available for analysis/inpaint requests
4. backend `/health` returns success
5. browser console and network panel show the expected request payloads

---

## What This README Does Not Cover Yet

This document focuses on codebase understanding and local development. It does not yet provide:

- production build deployment guidance
- automated test setup
- UI design system rules
- performance profiling workflow

---

## Related Docs

- repository overview: `../README.md`
- backend service guide: `../backend/README.md`
- frontend state types: `src/types/index.ts`
- frontend store: `src/store/useAppStore.ts`
- frontend API client: `src/services/aicssService.ts`
