// ─────────────────────────────────────────────────────────────────────────────
// AICSS Global Store — Zustand
// Manages: image, analysis result, layer assignments, edit mode, history, crop, inpaint
// ─────────────────────────────────────────────────────────────────────────────
import { create } from 'zustand';
import { DEFAULT_DEPTH_SPLIT_THRESHOLDS } from '../utils/depthSplit';
import { DEFAULT_PAPER_DIORAMA_PARAMS } from '../types';
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
  PaperDioramaParams,
  DepthLayerDioramaAsset,
  ObjectDioramaAsset,
  LayerRegion,
  PolygonPoint,
} from '../types';

const MAX_HISTORY = 50;

// StripStep: 一次"剥离"操作的产物。前景→中景→背景→天空逐层推进。
// - regionId: 抠出物的唯一 id
// - baseImageDataUrl: 剥离前的 image（用于撤销）
// - inpaintResultUrl: LaMa 补全结果（也是下一轮的 baseImage）
// - billboardUrl: 这一层的 RGBA billboard（保存在 billboardAssets[regionId]）
// - 其余几何/深度信息用于 3D 渲染
export interface StripStep {
  regionId: string;
  baseImageDataUrl: string;
  inpaintResultUrl: string;
  billboardUrl?: string;
  layerPolygon: PolygonPoint[];
  depthLayer: DepthLayerKey;
  depthValue: number;
  colorIndex: number;
}

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

  // Layer regions: arbitrary polygon regions for multi-billboard 3D reconstruction.
  // Each LayerRegion can come from AI detection (source='ai', linked to an objectId)
  // or from user freehand drawing (source='manual').
  // This coexists with assignments — assignments manages AI-detected objects,
  // regions manages both AI objects and manual regions.
  regions: LayerRegion[];

  // Drawing mode state — owned by SplitControls (toolbar), consumed by ImageCanvas (overlay).
  // SplitControls calls startDrawing/cancelDrawing to transition state.
  // ImageCanvas reads drawMode/drawPoints to show the live polygon overlay.
  drawMode: 'idle' | 'drawing';
  drawPoints: PolygonPoint[];

  // Strip pipeline state — the heart of the multi-billboard reconstruction.
  // stripStack: history of completed strip steps (in order, near→far).
  // currentImageUrl: image that the canvas should currently display and that
  //   the next strip step will be applied to. Equal to originalImageUrl when
  //   stripStack is empty, and to the last step's inpaintResultUrl otherwise.
  // currentImageWidth / currentImageHeight: dimensions of currentImageUrl.
  // isStripping: true while a strip step is in-flight (inpaint request active).
  stripStack: StripStep[];
  currentImageUrl: string;
  currentImageBase64: string;
  currentImageWidth: number;
  currentImageHeight: number;
  isStripping: boolean;
  stripError: string | null;

  // Billboard assets (RGBA textures from backend)
  // billboardAssets: 按 objectId 索引，存储每个物体抠出的 RGBA 贴图（用于 billboard 模式）
  // depthLayerBillboardAssets: 按 DepthLayerKey 索引，存储每个深度层的 RGBA 贴图（用于 depth-layer 模式）
  // 两者的区别在于切分粒度：billboardAssets 以单个物体为单位，depthLayerBillboardAssets 以深度层级为单位
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

  // Paper Diorama 2.0
  dioramaParams: PaperDioramaParams;
  dioramaLoading: boolean;
  dioramaError: string | null;
  depthLayerDioramaAssets: Partial<Record<DepthLayerKey, DepthLayerDioramaAsset>>;
  objectDioramaAssets: Record<string, ObjectDioramaAsset>;
  dioramaMode: 'billboard' | 'paper';  // 渲染模式：'billboard' 使用 flat PlaneGeometry（扁平面片），'paper' 使用 BoxGeometry（含厚度）模拟纸模效果
  outlineEnabled: boolean;
  parallaxEnabled: boolean;
  parallaxIntensity: number;

  // Auto-generate state (one-click pipeline)
  autoGenPhase: 'idle' | 'analyzing' | 'splitting' | 'generating' | 'done' | 'error';
  autoGenProgress: number;
  autoGenError: string | null;

  // VLM detection hint shown in toolbar
  vlmHint: string | null;

  // Inpaint
  inpaintPreviewUrl: string | null;
  inpaintLoading: boolean;
  inpaintError: string | null;

  // 3D Mesh Export
  meshExportProgress: number;
  meshExportError: string | null;

  // DashScope API key — used by the inpaint endpoint (wanx2.1-imageedit).
  // Scene/object detection no longer needs this since VLM runs locally.
  // Field name kept as `dashscopeApiKey` for backwards compatibility with
  // existing localStorage data and downstream consumers.
  dashscopeApiKey: string;

  // History for undo/redo
  // 使用双栈结构：past 存储历史状态（Ctrl+Z 回退），future 存储已撤销的状态（Ctrl+Y 重做）
  // pushHistory 时将当前 assignments 快照写入 past，并清空 future（因为新操作打断了撤销链）
  // MAX_HISTORY = 50 限制历史栈深度，防止内存溢出
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

  // Layer regions (multi-billboard 3D reconstruction)
  addRegion: (region: LayerRegion) => void;
  updateRegion: (id: string, updates: Partial<LayerRegion>) => void;
  removeRegion: (id: string) => void;
  setRegions: (regions: LayerRegion[]) => void;
  clearRegions: () => void;

  // Drawing mode
  startDrawing: () => void;
  cancelDrawing: () => void;
  addDrawPoint: (point: PolygonPoint) => void;
  undoDrawPoint: () => void;
  clearDrawPoints: () => void;
  completeDrawing: () => Promise<void>; // samples depth, creates LayerRegion, adds to store

  // Strip pipeline actions
  // pushStripStep: append a completed strip step to the stack and advance currentImage*.
  pushStripStep: (step: StripStep) => void;
  // undoLastStripStep: pop the last step and restore currentImage* to the previous state.
  undoLastStripStep: () => void;
  // resetStripStack: clear all steps and restore currentImage* to the originally imported image.
  resetStripStack: () => void;
  // setStripping: set the in-flight flag for the strip pipeline.
  setStripping: (v: boolean) => void;
  // setStripError: capture any error encountered during a strip step.
  setStripError: (msg: string | null) => void;

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

  // Paper Diorama 2.0
  setDioramaParams: (params: Partial<PaperDioramaParams>) => void;
  setDioramaLoading: (v: boolean) => void;
  setDioramaError: (msg: string | null) => void;
  setDepthLayerDioramaAsset: (layer: DepthLayerKey, asset: DepthLayerDioramaAsset) => void;
  setObjectDioramaAsset: (objectId: string, asset: ObjectDioramaAsset) => void;
  clearDioramaAssets: () => void;
  setDioramaMode: (mode: 'billboard' | 'paper') => void;
  setOutlineEnabled: (enabled: boolean) => void;
  setParallaxEnabled: (enabled: boolean) => void;
  setParallaxIntensity: (intensity: number) => void;

  setVlmHint: (hint: string | null) => void;
  setAutoGenPhase: (phase: AppState['autoGenPhase']) => void;
  setAutoGenProgress: (progress: number) => void;
  setAutoGenError: (error: string | null) => void;

  // Inpaint
  setInpaintPreview: (url: string | null) => void;
  setInpaintLoading: (v: boolean) => void;
  setInpaintError: (msg: string | null) => void;

  // 3D Mesh Export
  setMeshExportProgress: (progress: number) => void;
  setMeshExportError: (error: string | null) => void;

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
  regions: [] as LayerRegion[],
  drawMode: 'idle' as const,
  drawPoints: [] as PolygonPoint[],
  stripStack: [] as StripStep[],
  currentImageUrl: '',
  currentImageBase64: '',
  currentImageWidth: 0,
  currentImageHeight: 0,
  isStripping: false,
  stripError: null,
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
  dioramaParams: DEFAULT_PAPER_DIORAMA_PARAMS,
  dioramaLoading: false,
  dioramaError: null as string | null,
  depthLayerDioramaAssets: {} as Partial<Record<DepthLayerKey, DepthLayerDioramaAsset>>,
  objectDioramaAssets: {} as Record<string, ObjectDioramaAsset>,
  dioramaMode: 'billboard' as const,
  outlineEnabled: true,
  parallaxEnabled: false,
  parallaxIntensity: 0.5,
  autoGenPhase: 'idle' as const,
  autoGenProgress: 0,
  autoGenError: null,
  vlmHint: null,
  inpaintPreviewUrl: null as string | null,
  inpaintLoading: false,
  inpaintError: null as string | null,
  meshExportProgress: 0,
  meshExportError: null as string | null,
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
      // Initialize currentImage* to the same as originalImage* — strip pipeline starts clean.
      currentImageUrl: url,
      currentImageBase64: base64,
      currentImageWidth: width,
      currentImageHeight: height,
      // Reset strip stack: image just changed, prior steps are stale.
      stripStack: [],
      stripError: null,
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

  addRegion: (region) =>
    set((state) => ({ regions: [...state.regions, region] })),

  updateRegion: (id, updates) =>
    set((state) => ({
      regions: state.regions.map((r) =>
        r.id === id ? { ...r, ...updates } : r,
      ),
    })),

  removeRegion: (id) =>
    set((state) => ({
      regions: state.regions.filter((r) => r.id !== id),
    })),

  setRegions: (regions) => set({ regions }),

  clearRegions: () => set({ regions: [] }),

  startDrawing: () => set({ drawMode: 'drawing', drawPoints: [] }),

  cancelDrawing: () => set({ drawMode: 'idle', drawPoints: [] }),

  addDrawPoint: (point) =>
    set((state) => ({
      drawPoints: [...state.drawPoints, point],
    })),

  undoDrawPoint: () =>
    set((state) => ({
      drawPoints: state.drawPoints.slice(0, -1),
    })),

  clearDrawPoints: () => set({ drawPoints: [] }),

  // ─── Strip pipeline ──────────────────────────────────────────────────────

  pushStripStep: (step) =>
    set((state) => {
      // Snapshot the image BEFORE this step is applied as the previous
      // currentImageUrl. The new currentImageUrl becomes the inpaint result.
      const base64 = step.inpaintResultUrl.split(',')[1] || '';
      // We can't read image dimensions synchronously here — the caller is
      // expected to provide them when they have them. Store step as-is and
      // let ImageCanvas observe currentImageUrl to keep width/height in sync.
      return {
        stripStack: [...state.stripStack, step],
        currentImageUrl: step.inpaintResultUrl,
        currentImageBase64: base64,
        drawPoints: [],
        drawMode: 'idle',
      };
    }),

  undoLastStripStep: () =>
    set((state) => {
      if (state.stripStack.length === 0) return {};
      const stack = state.stripStack.slice(0, -1);
      // Restore currentImage* to the previous step's baseImageDataUrl.
      // If stack is now empty, restore to originalImageUrl.
      const baseImageUrl =
        stack.length > 0
          ? stack[stack.length - 1].inpaintResultUrl
          : state.originalImageUrl;
      const baseImageBase64 =
        stack.length > 0
          ? stack[stack.length - 1].inpaintResultUrl.split(',')[1] || ''
          : state.originalImageBase64;
      return {
        stripStack: stack,
        currentImageUrl: baseImageUrl,
        currentImageBase64: baseImageBase64,
      };
    }),

  resetStripStack: () =>
    set((state) => ({
      stripStack: [],
      currentImageUrl: state.originalImageUrl,
      currentImageBase64: state.originalImageBase64,
      drawMode: 'idle',
      drawPoints: [],
    })),

  setStripping: (v) => set({ isStripping: v }),
  setStripError: (msg) => set({ stripError: msg }),

  completeDrawing: async () => {
    const { loadDepthMapImageData, sampleDepthAtPolygon, autoAssignDepthLayer } = await import('../utils/depthUtils');
    const state = get();
    if (state.drawMode !== 'drawing' || state.drawPoints.length < 3) return;

    const depthMapUrl = state.analysisResult?.depthMapUrl;
    const imageWidth = state.imageWidth || 1920;
    const imageHeight = state.imageHeight || 1080;
    const selectedLayerIndex = state.selectedLayerIndex;
    const regions = state.regions;
    const { LAYER_COLORS } = await import('../types');

    let depthValue = 128;
    let depthLayer: import('../types').DepthLayerKey = 'foreground';

    if (depthMapUrl) {
      try {
        const depthData = await loadDepthMapImageData(depthMapUrl);
        depthValue = sampleDepthAtPolygon(depthData, state.drawPoints, imageWidth, imageHeight);
        depthLayer = autoAssignDepthLayer(depthValue);
      } catch (err) {
        console.error('Failed to sample depth for polygon:', err);
      }
    }

    const colorIndex = selectedLayerIndex ?? (regions.length % LAYER_COLORS.length);

    const region: LayerRegion = {
      id: `region-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      polygon: state.drawPoints,
      depthLayer,
      colorIndex,
      source: 'manual',
      depthValue,
    };

    set({
      regions: [...regions, region],
      drawMode: 'idle',
      drawPoints: [],
    });
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

  // Paper Diorama 2.0
  setDioramaParams: (params) =>
    set((state) => ({
      dioramaParams: { ...state.dioramaParams, ...params },
    })),

  setDioramaLoading: (v) => set({ dioramaLoading: v }),

  setDioramaError: (msg) => set({ dioramaError: msg }),

  setDepthLayerDioramaAsset: (layer, asset) =>
    set((state) => ({
      depthLayerDioramaAssets: {
        ...state.depthLayerDioramaAssets,
        [layer]: asset,
      },
    })),

  setObjectDioramaAsset: (objectId, asset) =>
    set((state) => ({
      objectDioramaAssets: {
        ...state.objectDioramaAssets,
        [objectId]: asset,
      },
    })),

  clearDioramaAssets: () =>
    set({
      depthLayerDioramaAssets: {},
      objectDioramaAssets: {},
    }),

  setDioramaMode: (mode) => set({ dioramaMode: mode }),

  setOutlineEnabled: (enabled) => set({ outlineEnabled: enabled }),

  setParallaxEnabled: (enabled) => set({ parallaxEnabled: enabled }),

  setParallaxIntensity: (intensity: number) => set({ parallaxIntensity: intensity }),

  setAutoGenPhase: (phase) => set({ autoGenPhase: phase }),
  setAutoGenProgress: (progress) => set({ autoGenProgress: progress }),
  setAutoGenError: (error) => set({ autoGenError: error }),
  setVlmHint: (hint) => set({ vlmHint: hint }),

  setInpaintPreview: (url) => set({ inpaintPreviewUrl: url }),

  setInpaintLoading: (v) => set({ inpaintLoading: v }),

  setInpaintError: (msg) => set({ inpaintError: msg }),

  setMeshExportProgress: (progress) => set({ meshExportProgress: progress }),
  setMeshExportError: (error) => set({ meshExportError: error }),

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

  reset: () => set({
    ...initialState,
    vlmHint: null,
    autoGenPhase: 'idle',
    autoGenProgress: 0,
    autoGenError: null,
    regions: [],
    drawMode: 'idle',
    drawPoints: [],
  }),
}));

// Keyboard shortcut handler for undo/redo and draw mode
// 在模块顶层注册 keydown 监听器，而非在 React 组件中注册，
// 这样可以确保无论哪个组件获得焦点，Ctrl+Z / Ctrl+Y / Enter / Esc 都能正常工作。
// 检测 e.ctrlKey || e.metaKey 以兼容 macOS 的 Command 键。
if (typeof window !== 'undefined') {
  window.addEventListener('keydown', (e: KeyboardEvent) => {
    const ctrl = e.ctrlKey || e.metaKey;
    const state = useAppStore.getState();

    // Draw mode shortcuts (only active when drawing)
    if (state.drawMode === 'drawing') {
      if (e.key === 'Enter') {
        e.preventDefault();
        state.completeDrawing();
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        state.cancelDrawing();
        return;
      }
      if ((e.key === 'z' && ctrl) || e.key === 'Backspace') {
        e.preventDefault();
        state.undoDrawPoint();
        return;
      }
    }

    // Undo / redo
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
// 使用 localStorage 而非 Zustand 的 sessionStorage，因为 API key 需要在浏览器会话间持久保存，
// 且不同于其他全局状态（页面刷新后应保留），不存入 store session 是合理的隐私/持久化权衡。
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
