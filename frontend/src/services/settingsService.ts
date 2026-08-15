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

export interface ProviderConfig {
  name: string;
  type: string; // "dashscope" | "openai_compatible" | any user-registered type
  base_url: string;
  api_key: string | null;
  extra_headers?: Record<string, string> | null;
  extra_json?: Record<string, unknown> | null;
  models: {
    llm?: string | null;
    vlm?: string | null;
    image?: string | null;
    video?: string | null;
  };
}

export interface RuntimeSettings {
  model_mode: string;
  vlm_mode: string;
  image_mode: string;
  video_mode: string;
  // Cloud provider per component: "dashscope" | "toapi"
  cloud_llm_provider: string;
  cloud_vlm_provider: string;
  cloud_image_provider: string;
  cloud_video_provider: string;
  // ToAPIs models (used when cloud_xxx_provider == "toapi")
  toapi_llm_model: string;
  toapi_image_model: string;
  toapi_video_model: string;
  // DashScope models (used when cloud_xxx_provider == "dashscope")
  dashscope_llm_model: string;
  dashscope_vlm_model: string;
  dashscope_image_model: string;
  // Local LLM
  llm_base_url: string;
  llm_model: string;
  // Local Image
  image_model_id: string;
  image_dtype: string;
  // Video provider string (used in local mode and dashscope mode)
  video_provider: string;
  // Per-component DashScope API keys (masked as "***" after initial read).
  dashscope_llm_api_key: string | null;
  dashscope_vlm_api_key: string | null;
  dashscope_image_api_key: string | null;
  dashscope_video_api_key: string | null;
  // ToAPIs API key (masked as "***"); used for ALL toapi components (LLM + Image + Video share it)
  toapi_llm_api_key: string | null;
  // Unified provider registry (new approach)
  providers: ProviderConfig[];
}

export type SettingsPatch = Partial<{
  model_mode: string;
  vlm_mode: string;
  image_mode: string;
  video_mode: string;
  cloud_llm_provider: string;
  cloud_vlm_provider: string;
  cloud_image_provider: string;
  cloud_video_provider: string;
  toapi_llm_model: string;
  toapi_image_model: string;
  toapi_video_model: string;
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
  toapi_llm_api_key: string;
  providers: ProviderConfig[];
}>;

export async function fetchSettings(): Promise<RuntimeSettings> {
  const resp = await client.get<RuntimeSettings>('/api/aicss/settings');
  return resp.data;
}

export async function updateSettings(patch: SettingsPatch): Promise<RuntimeSettings> {
  const resp = await client.post<RuntimeSettings>('/api/aicss/settings', patch);
  return resp.data;
}

// ── Provider registry API ──────────────────────────────────────────────────────

export interface ProviderTypeInfo {
  name: string;
  type: string;
  supports_chat: boolean;
  supports_vlm: boolean;
  supports_image: boolean;
  supports_video: boolean;
}

export async function listProviderTypes(): Promise<ProviderTypeInfo[]> {
  const resp = await client.get<ProviderTypeInfo[]>('/api/aicss/providers/types');
  return resp.data;
}

export async function pingProvider(component: string, name: string): Promise<boolean> {
  const resp = await client.post<{ alive: boolean }>('/api/aicss/providers/ping', {
    component, name,
  });
  return resp.data.alive;
}
