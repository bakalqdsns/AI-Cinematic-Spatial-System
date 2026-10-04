/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type PaperStyleRequest = {
  /**
   * Image URL or base64 data URL
   */
  imageUrl: string;
  /**
   * Colour quantisation levels (lower = flatter)
   */
  colorLevels?: number;
  /**
   * Bilateral filter strength
   */
  styleStrength?: number;
  /**
   * Canny edge low threshold
   */
  edgeLow?: number;
  /**
   * Canny edge high threshold
   */
  edgeHigh?: number;
  /**
   * Optional project ID — when set, styled image is persisted
   */
  projectId?: (string | null);
};

