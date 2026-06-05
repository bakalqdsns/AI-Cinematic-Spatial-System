// ─────────────────────────────────────────────────────────────────────────────
// AICSS Global Store — Zustand
// Manages: image, analysis result, layer assignments, edit mode, history, crop, inpaint
// ─────────────────────────────────────────────────────────────────────────────
import { create } from 'zustand';
import { DEFAULT_DEPTH_SPLIT_THRESHOLDS } from '../utils/depthSplit';
import type {
  AicssResult,
  LayerAssignments,
  EditMode,
  ImageViewMode,
  HistoryEntry,
  BillboardAsset,
  DepthLayerBillboardAsset,
  BillboardOffset,
  CropParams,
  DepthLayerKey,
  DepthSplitResult,
  DepthSplitThresholds,
} from '../types';

const MAX_HISTORY = 50;

interface AppState {
  // Image
  originalImageUrl: string;
  originalImageBase64: string;
  imageWidth: number;
  imageHeight: number;

  // Crop
  croppedImageUrl: string;
  cropParams: CropParams | null;

  // Analysis
  analysisResult: AicssResult | null;
  isAnalyzing: boolean;
  analysisError: string | null;

  // Layer assignments: objectId -> colorIndex
  assignments: LayerAssignments;
  selectedLayerIndex: number | null;

  // Billboard assets (RGBA textures from backend)
  billboardAssets: Record<string, BillboardAsset>;
  depthLayerBillboardAssets: Partial<Record<DepthLayerKey, DepthLayerBillboardAsset>>;

  // Billboard 3D offsets
  billboardOffsets: Record<string, BillboardOffset>;

  // Selected object in 2D canvas
  selectedObjectId: string | null;

  // Edit mode
  editMode: EditMode;

  // Image view mode: 'depth' | 'original' | 'depth-layer'
  imageMode: ImageViewMode;

  // Depth split preview
  depthSplitResult: DepthSplitResult | null;
  depthSplitLoading: boolean;
  depthSplitError: string | null;
  selectedDepthLayer: DepthLayerKey | null;
  depthSplitThresholds: DepthSplitThresholds;
  depthSplitConfirmed: boolean;

  // Inpaint
  inpaintPreviewUrl: string | null;
  inpaintLoading: boolean;
  inpaintError: string | null;

  // DashScope API key (user-entered, stored in localStorage)
  dashscopeApiKey: string;

  // History for undo/redo
  past: HistoryEntry[];
  future: HistoryEntry[];

  // Actions
  setImage: (url: string, base64: string, width: number, height: number) => void;
  setCroppedImage: (url: string, params: CropParams | null) => void;
  setAnalysisResult: (result: AicssResult | null) => void;
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
  setDepthLayerBillboardAsset: (layer: DepthLayerKey, rgbaUrl: string) => void;
  clearDepthLayerBillboardAssets: () => void;

  // Billboard offsets (3D drag)
  setBillboardOffset: (objectId: string, offsetX: number, offsetZ: number) => void;

  // Selection
  setSelectedObjectId: (id: string | null) => void;

  // Edit mode
  setEditMode: (mode: EditMode) => void;
  setImageMode: (mode: ImageViewMode) => void;

  // Depth split
  setDepthSplitResult: (result: DepthSplitResult | null) => void;
  setDepthSplitLoading: (v: boolean) => void;
  setDepthSplitError: (msg: string | null) => void;
  setSelectedDepthLayer: (layer: DepthLayerKey | null) => void;
  setDepthSplitThresholds: (thresholds: DepthSplitThresholds) => void;
  setDepthSplitConfirmed: (confirmed: boolean) => void;
  clearDepthSplit: () => void;

  // Inpaint
  setInpaintPreview: (url: string | null) => void;
  setInpaintLoading: (v: boolean) => void;
  setInpaintError: (msg: string | null) => void;

  // DashScope API key
  setDashscopeApiKey: (key: string) => void;

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
  croppedImageUrl: '',
  cropParams: null as CropParams | null,
  analysisResult: null as AicssResult | null,
  isAnalyzing: false,
  analysisError: null as string | null,
  assignments: {} as LayerAssignments,
  selectedLayerIndex: null as number | null,
  billboardAssets: {} as Record<string, BillboardAsset>,
  depthLayerBillboardAssets: {} as Partial<Record<DepthLayerKey, DepthLayerBillboardAsset>>,
  billboardOffsets: {} as Record<string, BillboardOffset>,
  selectedObjectId: null as string | null,
  editMode: 'director' as EditMode,
  imageMode: 'depth' as ImageViewMode,
  depthSplitResult: null as DepthSplitResult | null,
  depthSplitLoading: false,
  depthSplitError: null as string | null,
  selectedDepthLayer: null as DepthLayerKey | null,
  depthSplitThresholds: DEFAULT_DEPTH_SPLIT_THRESHOLDS,
  depthSplitConfirmed: false,
  inpaintPreviewUrl: null as string | null,
  inpaintLoading: false,
  inpaintError: null as string | null,
  dashscopeApiKey: '',
  past: [] as HistoryEntry[],
  future: [] as HistoryEntry[],
};

export const useAppStore = create<AppState>((set, get) => ({
  ...initialState,

  setImage: (url, base64, width, height) =>
    set({
      originalImageUrl: url,
      originalImageBase64: base64,
      imageWidth: width,
      imageHeight: height,
      depthSplitResult: null,
      depthSplitError: null,
      selectedDepthLayer: null,
      depthLayerBillboardAssets: {},
      depthSplitConfirmed: false,
      imageMode: 'original',
    }),

  setCroppedImage: (url, params) =>
    set({ croppedImageUrl: url, cropParams: params }),

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

  setDepthLayerBillboardAsset: (layer, rgbaUrl) =>
    set((state) => ({
      depthLayerBillboardAssets: {
        ...state.depthLayerBillboardAssets,
        [layer]: { layer, rgbaUrl },
      },
    })),

  clearDepthLayerBillboardAssets: () => set({ depthLayerBillboardAssets: {} }),

  setBillboardOffset: (objectId, offsetX, offsetZ) =>
    set((state) => ({
      billboardOffsets: {
        ...state.billboardOffsets,
        [objectId]: { objectId, offsetX, offsetZ },
      },
    })),

  setSelectedObjectId: (id) => set({ selectedObjectId: id }),

  setEditMode: (mode) => set({ editMode: mode }),

  setImageMode: (mode) => set({ imageMode: mode }),

  setDepthSplitResult: (result) => set({ depthSplitResult: result }),

  setDepthSplitLoading: (v) => set({ depthSplitLoading: v }),

  setDepthSplitError: (msg) => set({ depthSplitError: msg }),

  setSelectedDepthLayer: (layer) => set({ selectedDepthLayer: layer }),

  setDepthSplitThresholds: (thresholds) => set({ depthSplitThresholds: thresholds }),

  setDepthSplitConfirmed: (confirmed) => set({ depthSplitConfirmed: confirmed }),

  clearDepthSplit: () =>
    set({
      depthSplitResult: null,
      depthSplitLoading: false,
      depthSplitError: null,
      selectedDepthLayer: null,
      depthLayerBillboardAssets: {},
      depthSplitConfirmed: false,
      imageMode: 'original',
    }),

  setInpaintPreview: (url) => set({ inpaintPreviewUrl: url }),

  setInpaintLoading: (v) => set({ inpaintLoading: v }),

  setInpaintError: (msg) => set({ inpaintError: msg }),

  setDashscopeApiKey: (key) => set({ dashscopeApiKey: key }),

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

// Persist DashScope API key in localStorage
const STORED_KEY = 'aicss_dashscope_apikey';
if (typeof window !== 'undefined') {
  const stored = localStorage.getItem(STORED_KEY);
  if (stored) {
    useAppStore.getState().setDashscopeApiKey(stored);
  }

  let previousDashscopeApiKey = useAppStore.getState().dashscopeApiKey;
  useAppStore.subscribe((state) => {
    const nextKey = state.dashscopeApiKey;
    if (nextKey === previousDashscopeApiKey) return;
    previousDashscopeApiKey = nextKey;

    if (nextKey) localStorage.setItem(STORED_KEY, nextKey);
    else localStorage.removeItem(STORED_KEY);
  });
}
