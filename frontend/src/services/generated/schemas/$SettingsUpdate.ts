/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $SettingsUpdate = {
  description: `Partial update payload. Any omitted field is left unchanged.`,
  properties: {
    model_mode: {
      type: 'any-of',
      description: `Global model mode: 'cloud' | 'local'`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    vlm_mode: {
      type: 'any-of',
      description: `VLM mode: 'cloud' | 'local'`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    image_mode: {
      type: 'any-of',
      description: `Image generation mode: 'cloud' | 'local'`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    video_mode: {
      type: 'any-of',
      description: `Video generation mode: 'cloud' | 'local'`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    llm_base_url: {
      type: 'any-of',
      description: `OpenAI-compatible base URL for the local LLM server`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    llm_model: {
      type: 'any-of',
      description: `Local LLM model name (e.g. 'qwen2.5-7b-q4_k_m')`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    image_model_id: {
      type: 'any-of',
      description: `Diffusers model ID for local image generation`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    image_dtype: {
      type: 'any-of',
      description: `Dtype for image generation: 'float16' | 'bfloat16' | 'float32'`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    video_provider: {
      type: 'any-of',
      description: `Video provider: 'dashscope' | 'local_wan' | 'svd'`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    dashscope_api_key: {
      type: 'any-of',
      description: `[deprecated] Legacy single DashScope API key`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    dashscope_llm_api_key: {
      type: 'any-of',
      description: `DashScope API key for LLM calls`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    dashscope_vlm_api_key: {
      type: 'any-of',
      description: `DashScope API key for VLM (vision) calls`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    dashscope_image_api_key: {
      type: 'any-of',
      description: `DashScope API key for image generation`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    dashscope_video_api_key: {
      type: 'any-of',
      description: `DashScope API key for video generation`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    dashscope_llm_model: {
      type: 'any-of',
      description: `DashScope LLM model ID (e.g. 'qwen-plus')`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    dashscope_vlm_model: {
      type: 'any-of',
      description: `DashScope VLM model ID (e.g. 'qwen-vl-chat-v1')`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    dashscope_image_model: {
      type: 'any-of',
      description: `DashScope image model ID (e.g. 'wanx-v1')`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    cloud_llm_provider: {
      type: 'any-of',
      description: `Cloud provider for LLM: 'dashscope' | 'toapi' (legacy)`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    cloud_vlm_provider: {
      type: 'any-of',
      description: `Cloud provider for VLM: 'dashscope' | 'toapi' (legacy)`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    cloud_image_provider: {
      type: 'any-of',
      description: `Cloud provider for image: 'dashscope' | 'toapi' (legacy)`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    cloud_video_provider: {
      type: 'any-of',
      description: `Cloud provider for video: 'dashscope' | 'toapi' (legacy)`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    toapi_llm_model: {
      type: 'any-of',
      description: `ToAPIs LLM model ID (legacy)`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    toapi_image_model: {
      type: 'any-of',
      description: `ToAPIs image model ID (legacy)`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    toapi_video_model: {
      type: 'any-of',
      description: `ToAPIs video model ID (legacy)`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    toapi_llm_api_key: {
      type: 'any-of',
      description: `ToAPIs API key (legacy; shared by LLM/Image/Video)`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    providers: {
      type: 'any-of',
      description: `User-defined cloud provider registry`,
      contains: [{
        type: 'null',
      }],
    },
  },
} as const;
