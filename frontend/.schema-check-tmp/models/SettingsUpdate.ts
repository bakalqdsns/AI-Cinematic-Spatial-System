/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Partial update payload. Any omitted field is left unchanged.
 */
export type SettingsUpdate = {
  /**
   * Global model mode: 'cloud' | 'local'
   */
  model_mode?: (string | null);
  /**
   * VLM mode: 'cloud' | 'local'
   */
  vlm_mode?: (string | null);
  /**
   * Image generation mode: 'cloud' | 'local'
   */
  image_mode?: (string | null);
  /**
   * Video generation mode: 'cloud' | 'local'
   */
  video_mode?: (string | null);
  /**
   * OpenAI-compatible base URL for the local LLM server
   */
  llm_base_url?: (string | null);
  /**
   * Local LLM model name (e.g. 'qwen2.5-7b-q4_k_m')
   */
  llm_model?: (string | null);
  /**
   * Diffusers model ID for local image generation
   */
  image_model_id?: (string | null);
  /**
   * Dtype for image generation: 'float16' | 'bfloat16' | 'float32'
   */
  image_dtype?: (string | null);
  /**
   * Video provider: 'dashscope' | 'local_wan' | 'svd'
   */
  video_provider?: (string | null);
  /**
   * [deprecated] Legacy single DashScope API key
   */
  dashscope_api_key?: (string | null);
  /**
   * DashScope API key for LLM calls
   */
  dashscope_llm_api_key?: (string | null);
  /**
   * DashScope API key for VLM (vision) calls
   */
  dashscope_vlm_api_key?: (string | null);
  /**
   * DashScope API key for image generation
   */
  dashscope_image_api_key?: (string | null);
  /**
   * DashScope API key for video generation
   */
  dashscope_video_api_key?: (string | null);
  /**
   * DashScope LLM model ID (e.g. 'qwen-plus')
   */
  dashscope_llm_model?: (string | null);
  /**
   * DashScope VLM model ID (e.g. 'qwen-vl-chat-v1')
   */
  dashscope_vlm_model?: (string | null);
  /**
   * DashScope image model ID (e.g. 'wanx-v1')
   */
  dashscope_image_model?: (string | null);
  /**
   * Cloud provider for LLM: 'dashscope' | 'toapi' (legacy)
   */
  cloud_llm_provider?: (string | null);
  /**
   * Cloud provider for VLM: 'dashscope' | 'toapi' (legacy)
   */
  cloud_vlm_provider?: (string | null);
  /**
   * Cloud provider for image: 'dashscope' | 'toapi' (legacy)
   */
  cloud_image_provider?: (string | null);
  /**
   * Cloud provider for video: 'dashscope' | 'toapi' (legacy)
   */
  cloud_video_provider?: (string | null);
  /**
   * ToAPIs LLM model ID (legacy)
   */
  toapi_llm_model?: (string | null);
  /**
   * ToAPIs image model ID (legacy)
   */
  toapi_image_model?: (string | null);
  /**
   * ToAPIs video model ID (legacy)
   */
  toapi_video_model?: (string | null);
  /**
   * ToAPIs API key (legacy; shared by LLM/Image/Video)
   */
  toapi_llm_api_key?: (string | null);
  /**
   * User-defined cloud provider registry
   */
  providers?: null;
};

