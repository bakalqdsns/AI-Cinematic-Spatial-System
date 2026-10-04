/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type LayersRequest = {
  /**
   * Base64-encoded depth PNG
   */
  depthMap: string;
  /**
   * List of SpatialObject dicts
   */
  objects: Array<Record<string, any>>;
  imageWidth?: number;
  imageHeight?: number;
  /**
   * Optional project ID — when set, layer images are persisted
   */
  projectId?: (string | null);
};

