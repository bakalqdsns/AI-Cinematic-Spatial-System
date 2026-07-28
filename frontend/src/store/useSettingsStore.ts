// ─────────────────────────────────────────────────────────────────────────────
// Settings store — runtime config (LLM, image model, video provider, API keys).
// Backed by the backend's `/api/aicss/settings` endpoint.
// Persists dashscope API key + selected base URL across reloads via localStorage.
// ─────────────────────────────────────────────────────────────────────────────
import { create } from 'zustand';
import { fetchSettings, updateSettings } from '../services/settingsService';
import type { RuntimeSettings, SettingsPatch } from '../services/settingsService';

const STORAGE_KEY = 'aicss_runtime_settings_v1';

// ── Model download status ───────────────────────────────────────────────────────

export type ModelDownloadStatus = 'not_downloaded' | 'downloading' | 'downloaded' | 'error';

export interface ModelDownloadState {
  depth: ModelDownloadStatus;
  sam2: ModelDownloadStatus;
  grounding_dino: ModelDownloadStatus;
  qwen3vl: ModelDownloadStatus;
  lama: ModelDownloadStatus;
  image: ModelDownloadStatus;
}

interface SettingsState {
  open: boolean;
  loading: boolean;
  saving: boolean;
  error: string | null;
  settings: RuntimeSettings;
  hasFetched: boolean;

  // Model download status
  modelDownloads: ModelDownloadState;

  // UI
  setOpen: (open: boolean) => void;
  toggleOpen: () => void;

  // Lifecycle
  fetchSettings: () => Promise<void>;
  saveSettings: (patch: SettingsPatch) => Promise<void>;
  fetchModelDownloads: () => Promise<void>;

  // Direct mutations (used by the form before save)
  setLocalField: <K extends keyof RuntimeSettings>(key: K, value: RuntimeSettings[K]) => void;
  resetLocal: () => void;
  setModelDownloadStatus: (model: keyof ModelDownloadState, status: ModelDownloadStatus) => void;
}

const DEFAULT_SETTINGS: RuntimeSettings = {
  model_mode: 'cloud',
  vlm_mode: 'cloud',
  image_mode: 'cloud',
  video_mode: 'cloud',
  dashscope_llm_model: 'qwen3.7-plus',
  dashscope_vlm_model: 'qwen3-vl-flash-2026-01-22',
  dashscope_image_model: 'wan2.7-image-pro',
  llm_base_url: 'http://localhost:8080/v1',
  llm_model: 'qwen2.5-7b-q4_k_m',
  image_model_id: 'Tongyi-MAI/Z-Image-Turbo',
  image_dtype: 'bfloat16',
  video_provider: 'dashscope',
  dashscope_llm_api_key: null,
  dashscope_vlm_api_key: null,
  dashscope_image_api_key: null,
  dashscope_video_api_key: null,
};

const DEFAULT_MODEL_DOWNLOADS: ModelDownloadState = {
  depth: 'not_downloaded',
  sam2: 'not_downloaded',
  grounding_dino: 'not_downloaded',
  qwen3vl: 'not_downloaded',
  lama: 'not_downloaded',
  image: 'not_downloaded',
};

function loadFromLocalStorage(): Partial<RuntimeSettings> {
  if (typeof window === 'undefined') return {};
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    return JSON.parse(raw) as Partial<RuntimeSettings>;
  } catch {
    return {};
  }
}

function persistToLocalStorage(patch: Partial<RuntimeSettings>): void {
  if (typeof window === 'undefined') return;
  try {
    const current = loadFromLocalStorage();
    const merged = { ...current, ...patch };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(merged));
  } catch {
    // ignore quota / disabled storage
  }
}

export const useSettingsStore = create<SettingsState>((set, get) => ({
  open: false,
  loading: false,
  saving: false,
  error: null,
  settings: { ...DEFAULT_SETTINGS, ...loadFromLocalStorage() },
  hasFetched: false,
  modelDownloads: { ...DEFAULT_MODEL_DOWNLOADS },

  setOpen: (open) => set({ open }),
  toggleOpen: () => set((s) => ({ open: !s.open })),

  fetchSettings: async () => {
    set({ loading: true, error: null });
    try {
      const remote = await fetchSettings();
      // Merge: local storage wins for API keys (we don't want to overwrite a
      // user-supplied key with the server's masked "***" placeholder).
      const local = loadFromLocalStorage();
      const merged: RuntimeSettings = {
        ...remote,
        // Preserve locally-stored secrets if backend sent masked values.
        dashscope_llm_api_key:
          (remote.dashscope_llm_api_key && remote.dashscope_llm_api_key !== '***')
            ? remote.dashscope_llm_api_key
            : (local.dashscope_llm_api_key ?? null),
        dashscope_vlm_api_key:
          (remote.dashscope_vlm_api_key && remote.dashscope_vlm_api_key !== '***')
            ? remote.dashscope_vlm_api_key
            : (local.dashscope_vlm_api_key ?? null),
        dashscope_image_api_key:
          (remote.dashscope_image_api_key && remote.dashscope_image_api_key !== '***')
            ? remote.dashscope_image_api_key
            : (local.dashscope_image_api_key ?? null),
        dashscope_video_api_key:
          (remote.dashscope_video_api_key && remote.dashscope_video_api_key !== '***')
            ? remote.dashscope_video_api_key
            : (local.dashscope_video_api_key ?? null),
        // Preserve local dashscope model selections if backend sends empty/missing values
        dashscope_vlm_model: remote.dashscope_vlm_model || local.dashscope_vlm_model || DEFAULT_SETTINGS.dashscope_vlm_model,
        dashscope_image_model: remote.dashscope_image_model || local.dashscope_image_model || DEFAULT_SETTINGS.dashscope_image_model,
      };
      set({
        settings: merged,
        hasFetched: true,
        loading: false,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      set({ error: msg, loading: false });
    }
  },

  fetchModelDownloads: async () => {
    try {
      const resp = await fetch(`${import.meta.env.VITE_AICSS_BACKEND || 'http://localhost:8000'}/api/aicss/models/status`);
      if (!resp.ok) return;
      const data = await resp.json();
      const models = data.models ?? {};
      const current = get().modelDownloads;
      const updated: Partial<ModelDownloadState> = {};
      for (const key of Object.keys(current) as (keyof ModelDownloadState)[]) {
        const info = models[key];
        if (info) {
          updated[key] = info.status as ModelDownloadStatus;
        }
      }
      set((s) => ({ modelDownloads: { ...s.modelDownloads, ...updated } }));
    } catch {
      // Silently ignore — download status is a best-effort feature
    }
  },

  saveSettings: async (patch) => {
    set({ saving: true, error: null });
    try {
      // Optimistically apply locally so the UI reflects the change immediately.
      set((s) => ({ settings: { ...s.settings, ...patch } }));
      const remote = await updateSettings(patch);
      // Backend masks API keys in response; merge with what we know.
      const prev = get().settings;
      const next: RuntimeSettings = {
        ...remote,
        dashscope_llm_api_key:
          remote.dashscope_llm_api_key === '***'
            ? (patch.dashscope_llm_api_key ?? prev.dashscope_llm_api_key ?? null)
            : remote.dashscope_llm_api_key,
        dashscope_vlm_api_key:
          remote.dashscope_vlm_api_key === '***'
            ? (patch.dashscope_vlm_api_key ?? prev.dashscope_vlm_api_key ?? null)
            : remote.dashscope_vlm_api_key,
        dashscope_image_api_key:
          remote.dashscope_image_api_key === '***'
            ? (patch.dashscope_image_api_key ?? prev.dashscope_image_api_key ?? null)
            : remote.dashscope_image_api_key,
        dashscope_video_api_key:
          remote.dashscope_video_api_key === '***'
            ? (patch.dashscope_video_api_key ?? prev.dashscope_video_api_key ?? null)
            : remote.dashscope_video_api_key,
      };
      set({ settings: next, saving: false });
      // Persist API keys + non-secret UI choices for next session.
      persistToLocalStorage(patch);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      set({ error: msg, saving: false });
      // Re-fetch authoritative state on failure
      get().fetchSettings();
    }
  },

  setLocalField: (key, value) => {
    set((s) => ({ settings: { ...s.settings, [key]: value } }));
  },

  setModelDownloadStatus: (model, status) => {
    set((s) => ({ modelDownloads: { ...s.modelDownloads, [model]: status } }));
  },

  resetLocal: () => {
    set({ settings: { ...DEFAULT_SETTINGS, ...loadFromLocalStorage() } });
  },
}));
