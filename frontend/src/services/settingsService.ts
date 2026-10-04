// ─────────────────────────────────────────────────────────────────────────────
// Settings service — fetches / mutates runtime settings on the AICSS backend.
//
// Thin wrapper around the generated OpenAPI client (`generated/settings` and
// `generated/cloudProviders`). The settings endpoints return free-form JSON
// (`Record<string, any>`) per the OpenAPI spec, so the wrappers below just
// cast the response to the existing frontend interfaces — no field mapping
// required (the wire format is already camelCase / snake_case mixed exactly
// as the existing `RuntimeSettings` interface expects).
// ─────────────────────────────────────────────────────────────────────────────
import { generatedClient } from './generatedClient';

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
  return generatedClient.settings.getSettingsApiAicssSettingsGet() as unknown as Promise<RuntimeSettings>;
}

export async function updateSettings(patch: SettingsPatch): Promise<RuntimeSettings> {
  return generatedClient.settings.postSettingsApiAicssSettingsPost({
    requestBody: patch as any,
  }) as unknown as Promise<RuntimeSettings>;
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
  return generatedClient.cloudProviders.getProviderTypesApiAicssProvidersTypesGet() as unknown as Promise<ProviderTypeInfo[]>;
}

export async function pingProvider(component: string, name: string): Promise<boolean> {
  const resp = await generatedClient.cloudProviders.pingProviderApiAicssProvidersPingPost({
    requestBody: { component, name } as any,
  }) as { alive: boolean };
  return resp.alive;
}

export interface SettingsStoreInfo {
  path: string;
  override_count: number;
  error?: string;
}

export async function fetchSettingsStore(): Promise<SettingsStoreInfo> {
  return generatedClient.settings.getSettingsStoreApiAicssSettingsStoreGet() as unknown as Promise<SettingsStoreInfo>;
}

export async function resetSettingsStore(): Promise<{ success: boolean; message: string }> {
  return generatedClient.settings.resetSettingsStoreApiAicssSettingsStoreDelete() as unknown as Promise<{ success: boolean; message: string }>;
}
