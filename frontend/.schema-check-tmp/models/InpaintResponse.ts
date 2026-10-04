/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * `POST /api/aicss/inpaint` response.
 */
export type InpaintResponse = {
  /**
   * Base64 data URI of the inpainted PNG
   */
  imageUrl: string;
  /**
   * Alias of imageUrl, kept for backward compat
   */
  inpaintResultUrl?: (string | null);
  width: number;
  height: number;
  /**
   * Model identifier used for inpainting
   */
  model?: (string | null);
  /**
   * Ratio of white pixels in the mask
   */
  maskWhiteRatio?: (number | null);
  warnings?: null;
  savedArtifacts?: (Array<string> | null);
  /**
   * True when the call fell back from cloud to local LaMa.
   */
  usedFallback?: boolean;
  savedFiles?: (Array<string> | null);
};

