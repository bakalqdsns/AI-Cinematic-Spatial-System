/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * `POST /api/aicss/segment` response.
 */
export type SegmentResponse = {
  /**
   * Detected objects with `id`, `classLabel`, `boundingBox`, `mask`, etc.
   */
  objects: Array<Record<string, any>>;
  width: number;
  height: number;
  savedFiles?: (Array<string> | null);
};

