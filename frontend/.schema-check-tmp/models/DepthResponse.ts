/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * `POST /api/aicss/depth` response.
 */
export type DepthResponse = {
  /**
   * Base64 data URI of the depth map PNG (grayscale)
   */
  depthMapUrl: string;
  /**
   * Depth map width in pixels
   */
  width: number;
  /**
   * Depth map height in pixels
   */
  height: number;
  /**
   * Minimum depth value (meters)
   */
  minDepth: number;
  /**
   * Maximum depth value (meters)
   */
  maxDepth: number;
  /**
   * Filenames persisted under the project's `depth/` dir (when projectId was provided)
   */
  savedFiles?: (Array<string> | null);
};

