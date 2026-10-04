/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * `POST /api/aicss/multiface` response.
 *
 * Returns 6 RGBA PNGs — one per cube face. Useful for 3D viewers that
 * need a quick pseudo-3D representation of a 2D object without
 * running a full 3D reconstruction.
 */
export type MultifaceResponse = {
  /**
   * Map of face name (front/back/left/right/top/bottom) → data:image/png;base64,... URI
   */
  faces?: Record<string, string>;
  width?: number;
  height?: number;
  savedFiles?: (Array<string> | null);
};

