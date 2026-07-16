// ─────────────────────────────────────────────────────────────────────────────
// AICSS Sequence Store — Zustand
// Manages: sequence data, frame navigation, playback control, cross-frame tracking
// ─────────────────────────────────────────────────────────────────────────────
import { create } from 'zustand';
import type {
  SequenceResult,
  FrameResult,
  CrossFrameObject,
  SceneLink,
  SceneLinksResponse,
  AnalyzeSequenceRequest,
  AnalyzeFromScriptRequest,
} from '../types/sequence';
import {
  analyzeSequence,
  analyzeFromScript,
  getSequence,
  getSceneLinks,
} from '../services/sequenceService';

interface SequenceState {
  // 序列数据
  sequenceId: string | null;
  currentShotId: string | null;
  sequenceResult: SequenceResult | null;
  sceneLinksResponse: SceneLinksResponse | null;

  // 帧状态
  frames: FrameResult[];
  currentFrameIndex: number;

  // 跨帧追踪
  crossFrameObjects: CrossFrameObject[];
  sceneLinks: SceneLink[];

  // 选中物体
  selectedGlobalObjectId: string | null;

  // 播放控制
  isPlaying: boolean;
  playbackSpeed: number;

  // 加载状态
  loading: boolean;
  progress: number;
  progressMessage: string;
  error: string | null;

  // Actions
  analyzeSequence: (request: AnalyzeSequenceRequest) => Promise<void>;
  analyzeFromScript: (request: AnalyzeFromScriptRequest) => Promise<void>;
  loadSequence: (sequenceId: string) => Promise<void>;
  loadSceneLinks: (sequenceId: string) => Promise<void>;

  // 帧导航
  setCurrentFrame: (index: number) => void;
  nextFrame: () => void;
  prevFrame: () => void;

  // 播放控制
  play: () => void;
  pause: () => void;
  setPlaybackSpeed: (speed: number) => void;

  // 选择
  setSelectedGlobalObjectId: (id: string | null) => void;

  // 重置
  reset: () => void;
}

const initialState = {
  sequenceId: null,
  currentShotId: null,
  sequenceResult: null,
  sceneLinksResponse: null,
  frames: [],
  currentFrameIndex: 0,
  crossFrameObjects: [],
  sceneLinks: [],
  selectedGlobalObjectId: null,
  isPlaying: false,
  playbackSpeed: 1,
  loading: false,
  progress: 0,
  progressMessage: '',
  error: null,
};

export const useSequenceStore = create<SequenceState>((set, get) => ({
  ...initialState,

  analyzeSequence: async (request) => {
    set({ loading: true, progress: 0, progressMessage: '正在分析序列...', error: null });

    try {
      const result = await analyzeSequence(request);
      set({
        sequenceId: result.sequenceId,
        currentShotId: result.shotId,
        sequenceResult: result,
        frames: result.frames,
        crossFrameObjects: result.crossFrameObjects,
        sceneLinks: result.sceneLinks,
        currentFrameIndex: 0,
        loading: false,
        progress: 100,
        progressMessage: '分析完成',
      });
    } catch (err) {
      set({
        loading: false,
        error: err instanceof Error ? err.message : String(err),
        progressMessage: '分析失败',
      });
    }
  },

  analyzeFromScript: async (request) => {
    set({ loading: true, progress: 0, progressMessage: '正在分析剧本场景...', error: null });

    try {
      const result = await analyzeFromScript(request);
      set({
        sequenceId: result.sequenceId,
        currentShotId: result.shotId,
        sequenceResult: result,
        frames: result.frames,
        crossFrameObjects: result.crossFrameObjects,
        sceneLinks: result.sceneLinks,
        currentFrameIndex: 0,
        loading: false,
        progress: 100,
        progressMessage: '分析完成',
      });
    } catch (err) {
      set({
        loading: false,
        error: err instanceof Error ? err.message : String(err),
        progressMessage: '分析失败',
      });
    }
  },

  loadSequence: async (sequenceId) => {
    set({ loading: true, error: null });
    try {
      const result = await getSequence(sequenceId);
      set({
        sequenceId: result.sequenceId,
        currentShotId: result.shotId,
        sequenceResult: result,
        frames: result.frames,
        crossFrameObjects: result.crossFrameObjects,
        sceneLinks: result.sceneLinks,
        loading: false,
      });
    } catch (err) {
      set({ loading: false, error: err instanceof Error ? err.message : String(err) });
    }
  },

  loadSceneLinks: async (sequenceId) => {
    try {
      const response = await getSceneLinks(sequenceId);
      set({ sceneLinksResponse: response });
    } catch (err) {
      set({ error: err instanceof Error ? err.message : String(err) });
    }
  },

  setCurrentFrame: (index) => {
    const { frames } = get();
    if (index >= 0 && index < frames.length) {
      set({ currentFrameIndex: index });
    }
  },

  nextFrame: () => {
    const { currentFrameIndex, frames } = get();
    if (currentFrameIndex < frames.length - 1) {
      set({ currentFrameIndex: currentFrameIndex + 1 });
    }
  },

  prevFrame: () => {
    const { currentFrameIndex } = get();
    if (currentFrameIndex > 0) {
      set({ currentFrameIndex: currentFrameIndex - 1 });
    }
  },

  play: () => set({ isPlaying: true }),
  pause: () => set({ isPlaying: false }),

  setPlaybackSpeed: (speed) => set({ playbackSpeed: speed }),

  setSelectedGlobalObjectId: (id) => set({ selectedGlobalObjectId: id }),

  reset: () => set(initialState),
}));
