// ─────────────────────────────────────────────────────────────────────────────
// Settings service — fetches / mutates runtime settings on the AICSS backend.
// Mirrors the OpenAPI contract of `app/endpoints_settings.py`.
// ─────────────────────────────────────────────────────────────────────────────
import axios from 'axios';

const DEFAULT_BACKEND = import.meta.env.VITE_AICSS_BACKEND || 'http://localhost:8000';

const client = axios.create({
  baseURL: DEFAULT_BACKEND,
  timeout: 30_000,
});

export interface RuntimeSettings {
  llm_base_url: string;
  llm_model: string;
  image_model_id: string;
  image_dtype: string;
  video_provider: string;
  dashscope_api_key: string | null; // masked as "***" after initial read
}

export type SettingsPatch = Partial<{
  llm_base_url: string;
  llm_model: string;
  image_model_id: string;
  image_dtype: string;
  video_provider: string;
  dashscope_api_key: string;
}>;

export async function fetchSettings(): Promise<RuntimeSettings> {
  const resp = await client.get<RuntimeSettings>('/api/aicss/settings');
  return resp.data;
}

export async function updateSettings(patch: SettingsPatch): Promise<RuntimeSettings> {
  const resp = await client.post<RuntimeSettings>('/api/aicss/settings', patch);
  return resp.data;
}
