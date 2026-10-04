/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GenerateMotionRequest = {
  shot_id: string;
  character_id: string;
  character_name: string;
  action_prompt: string;
  /**
   * Base64 start frame
   */
  start_image?: (string | null);
  /**
   * Base64 end frame
   */
  end_image?: (string | null);
  duration_seconds?: number;
  /**
   * Video provider: dashscope | local_wan | svd
   */
  video_provider?: string;
  /**
   * Render the action video against a flat green-screen background and apply a chroma-key pass during segmentation.
   */
  greenscreen?: boolean;
  /**
   * Snap SAM2 masks to nearby Canny edges to soften character silhouettes.
   */
  feather_edges?: boolean;
  project_id?: (string | null);
};

