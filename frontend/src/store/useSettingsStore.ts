// ─────────────────────────────────────────────────────────────────────────────
// Settings store — runtime config (LLM, image model, video provider, API keys).
// Backed by the backend's `/api/aicss/settings` endpoint.
// Persists dashscope API key + selected base URL across reloads via localStorage.
// ─────────────────────────────────────────────────────────────────────────────
import { create } from 'zustand';
import { fetchSettings, updateSettings } from '../services/settingsService';
import type { RuntimeSettings, SettingsPatch } from '../services/settingsService';

const STORAGE_KEY = 'aicss_runtime_settings_v1';

interface SettingsState {
  open: boolean;
  loading: boolean;
  saving: boolean;
  error: string | null;
  settings: RuntimeSettings;
  hasFetched: boolean;

  // UI
  setOpen: (open: boolean) => void;
  toggleOpen: () => void;

  // Lifecycle
  fetchSettings: () => Promise<void>;
  saveSettings: (patch: SettingsPatch) => Promise<void>;

  // Direct mutations (used by the form before save)
  setLocalField: <K extends keyof RuntimeSettings>(key: K, value: RuntimeSettings[K]) => void;
  resetLocal: () => void;
}

const DEFAULT_SETTINGS: RuntimeSettings = {
  llm_base_url: 'http://localhost:8080/v1',
  llm_model: 'qwen3.5-9b',
  image_model_id: 'stabilityai/stable-diffusion-xl-base-1.0',
  image_dtype: 'bfloat16',
  video_provider: 'dashscope',
  dashscope_api_key: null,
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
        // Preserve locally-stored secret if backend sent us a masked value.
        dashscope_api_key:
          (remote.dashscope_api_key && remote.dashscope_api_key !== '***')
            ? remote.dashscope_api_key
            : (local.dashscope_api_key ?? null),
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

  saveSettings: async (patch) => {
    set({ saving: true, error: null });
    try {
      // Optimistically apply locally so the UI reflects the change immediately.
      set((s) => ({ settings: { ...s.settings, ...patch } }));
      const remote = await updateSettings(patch);
      // Backend masks dashscope_api_key in response; merge with what we know.
      const next: RuntimeSettings = {
        ...remote,
        dashscope_api_key: remote.dashscope_api_key === '***'
          ? (patch.dashscope_api_key ?? get().settings.dashscope_api_key ?? null)
          : remote.dashscope_api_key,
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

  resetLocal: () => {
    set({ settings: { ...DEFAULT_SETTINGS, ...loadFromLocalStorage() } });
  },
}));
