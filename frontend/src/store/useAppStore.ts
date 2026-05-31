// ─────────────────────────────────────────────────────────────────────────────
// AICSS Global Store — Zustand
// Manages: image, analysis result, layer assignments, edit mode, history
// ─────────────────────────────────────────────────────────────────────────────
import { create } from 'zustand';
import type {
  AicssResult,
  DetectedObject,
  LayerAssignments,
  EditMode,
  HistoryEntry,
  BillboardAsset,
  BillboardOffset,
} from '../types';

const MAX_HISTORY = 50;

interface AppState {
  // Image
  originalImageUrl: string;
  originalImageBase64: string;
  imageWidth: number;
  imageHeight: number;

  // Analysis
  analysisResult: AicssResult | null;
  isAnalyzing: boolean;
  analysisError: string | null;

  // Layer assignments: objectId -> colorIndex
  assignments: LayerAssignments;
  selectedLayerIndex: number | null; // which color slot is currently active

  // Billboard assets (RGBA textures from backend)
  billboardAssets: Record<string, BillboardAsset>;

  // Billboard 3D offsets
  billboardOffsets: Record<string, BillboardOffset>;

  // Selected object in 2D canvas
  selectedObjectId: string | null;

  // Edit mode
  editMode: EditMode;

  // User-configurable segmentation prompt
  segmentationPrompt: string;

  // Image view mode: 'depth' | 'original'
  imageMode: 'depth' | 'original';

  // History for undo/redo
  past: HistoryEntry[];
  future: HistoryEntry[];

  // Actions
  setImage: (url: string, base64: string, width: number, height: number) => void;
  setAnalysisResult: (result: AicssResult) => void;
  setIsAnalyzing: (v: boolean) => void;
  setAnalysisError: (msg: string | null) => void;

  // Layer assignment
  selectLayer: (colorIndex: number | null) => void;
  assignObjectToLayer: (objectId: string, colorIndex: number) => void;
  unassignObject: (objectId: string) => void;
  toggleObjectLayer: (objectId: string) => void;
  clearLayer: (colorIndex: number) => void;
  clearAllAssignments: () => void;

  // Billboard assets
  setBillboardAsset: (objectId: string, rgbaUrl: string) => void;

  // Billboard offsets (3D drag)
  setBillboardOffset: (objectId: string, offsetX: number, offsetZ: number) => void;

  // Selection
  setSelectedObjectId: (id: string | null) => void;

  // Edit mode
  setEditMode: (mode: EditMode) => void;
  setSegmentationPrompt: (prompt: string) => void;
  setImageMode: (mode: 'depth' | 'original') => void;

  // History
  pushHistory: () => void;
  undo: () => void;
  redo: () => void;
  canUndo: () => boolean;
  canRedo: () => boolean;

  // Reset
  reset: () => void;
}

const initialState = {
  originalImageUrl: '',
  originalImageBase64: '',
  imageWidth: 0,
  imageHeight: 0,
  analysisResult: null,
  isAnalyzing: false,
  analysisError: null,
  assignments: {} as LayerAssignments,
  selectedLayerIndex: null as number | null,
  billboardAssets: {} as Record<string, BillboardAsset>,
  billboardOffsets: {} as Record<string, BillboardOffset>,
  selectedObjectId: null as string | null,
  editMode: 'director' as EditMode,
  segmentationPrompt: 'person,car,building,tree,lamp,door,window,chair,table',
  imageMode: 'depth' as 'depth' | 'original',
  past: [] as HistoryEntry[],
  future: [] as HistoryEntry[],
};

export const useAppStore = create<AppState>((set, get) => ({
  ...initialState,

  setImage: (url, base64, width, height) =>
    set({ originalImageUrl: url, originalImageBase64: base64, imageWidth: width, imageHeight: height }),

  setAnalysisResult: (result) =>
    set({ analysisResult: result, analysisError: null }),

  setIsAnalyzing: (v) => set({ isAnalyzing: v }),

  setAnalysisError: (msg) => set({ analysisError: msg }),

  selectLayer: (colorIndex) => set({ selectedLayerIndex: colorIndex }),

  assignObjectToLayer: (objectId, colorIndex) => {
    set((state) => ({
      assignments: { ...state.assignments, [objectId]: colorIndex },
    }));
  },

  unassignObject: (objectId) => {
    set((state) => {
      const next = { ...state.assignments };
      delete next[objectId];
      return { assignments: next };
    });
  },

  toggleObjectLayer: (objectId) => {
    set((state) => {
      const currentLayer = state.assignments[objectId];
      const selectedLayer = state.selectedLayerIndex;

      if (currentLayer !== undefined) {
        // Already assigned — remove from layer
        return {
          past: [
            ...state.past.slice(-MAX_HISTORY + 1),
            { assignments: { ...state.assignments }, timestamp: Date.now() },
          ],
          future: [],
          assignments: Object.fromEntries(
            Object.entries(state.assignments).filter(([k]) => k !== objectId),
          ),
        };
      } else if (selectedLayer !== null) {
        // Assign to selected layer
        return {
          past: [
            ...state.past.slice(-MAX_HISTORY + 1),
            { assignments: { ...state.assignments }, timestamp: Date.now() },
          ],
          future: [],
          assignments: { ...state.assignments, [objectId]: selectedLayer },
        };
      }
      return {};
    });
  },

  clearLayer: (colorIndex) => {
    get().pushHistory();
    set((state) => {
      const next = { ...state.assignments };
      for (const [k, v] of Object.entries(next)) {
        if (v === colorIndex) delete next[k];
      }
      return { assignments: next };
    });
  },

  clearAllAssignments: () => {
    get().pushHistory();
    set({ assignments: {} });
  },

  setBillboardAsset: (objectId, rgbaUrl) =>
    set((state) => ({
      billboardAssets: {
        ...state.billboardAssets,
        [objectId]: { objectId, rgbaUrl },
      },
    })),

  setBillboardOffset: (objectId, offsetX, offsetZ) =>
    set((state) => ({
      billboardOffsets: {
        ...state.billboardOffsets,
        [objectId]: { objectId, offsetX, offsetZ },
      },
    })),

  setSelectedObjectId: (id) => set({ selectedObjectId: id }),

  setEditMode: (mode) => set({ editMode: mode }),

  setSegmentationPrompt: (prompt) => set({ segmentationPrompt: prompt }),

  setImageMode: (mode) => set({ imageMode: mode }),

  pushHistory: () =>
    set((state) => ({
      past: [...state.past.slice(-MAX_HISTORY + 1), { assignments: { ...state.assignments }, timestamp: Date.now() }],
      future: [],
    })),

  undo: () => {
    const state = get();
    if (state.past.length === 0) return;
    const prev = state.past[state.past.length - 1];
    set({
      assignments: prev.assignments,
      past: state.past.slice(0, -1),
      future: [{ assignments: { ...state.assignments }, timestamp: Date.now() }, ...state.future],
    });
  },

  redo: () => {
    const state = get();
    if (state.future.length === 0) return;
    const next = state.future[0];
    set({
      assignments: next.assignments,
      future: state.future.slice(1),
      past: [...state.past, { assignments: { ...state.assignments }, timestamp: Date.now() }],
    });
  },

  canUndo: () => get().past.length > 0,
  canRedo: () => get().future.length > 0,

  reset: () => set(initialState),
}));

// Keyboard shortcut handler for undo/redo
if (typeof window !== 'undefined') {
  window.addEventListener('keydown', (e: KeyboardEvent) => {
    const ctrl = e.ctrlKey || e.metaKey;
    if (ctrl && e.key === 'z' && !e.shiftKey) {
      e.preventDefault();
      useAppStore.getState().undo();
    }
    if (ctrl && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) {
      e.preventDefault();
      useAppStore.getState().redo();
    }
  });
}
