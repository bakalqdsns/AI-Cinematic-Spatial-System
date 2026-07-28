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
  model_mode: string;
  vlm_mode: string;
  image_mode: string;
  video_mode: string;
  dashscope_llm_model: string;
  dashscope_vlm_model: string;
  dashscope_image_model: string;
  llm_base_url: string;
  llm_model: string;
  image_model_id: string;
  image_dtype: string;
  video_provider: string;
  // Per-component DashScope API keys (masked as "***" after initial read).
  // Each component has its own key so users can mix vendors / accounts.
  dashscope_llm_api_key: string | null;
  dashscope_vlm_api_key: string | null;
  dashscope_image_api_key: string | null;
  dashscope_video_api_key: string | null;
}

export type SettingsPatch = Partial<{
  model_mode: string;
  vlm_mode: string;
  image_mode: string;
  video_mode: string;
  dashscope_llm_model: string;
  dashscope_vlm_model: string;
  dashscope_image_model: string;
  llm_base_url: string;
  llm_model: string;
  image_model_id: string;
  image_dtype: string;
  video_provider: string;
  dashscope_llm_api_key: string;
  dashscope_vlm_api_key: string;
  dashscope_image_api_key: string;
  dashscope_video_api_key: string;
}>;

export async function fetchSettings(): Promise<RuntimeSettings> {
  const resp = await client.get<RuntimeSettings>('/api/aicss/settings');
  return resp.data;
}

export async function updateSettings(patch: SettingsPatch): Promise<RuntimeSettings> {
  const resp = await client.post<RuntimeSettings>('/api/aicss/settings', patch);
  return resp.data;
}
