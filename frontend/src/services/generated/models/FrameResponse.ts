/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type FrameResponse = {
  frameIndex: number;
  frameId: string;
  frameType?: (string | null);
  originalUrl: string;
  depthMapUrl: string;
  objects: Array<Record<string, any>>;
  layers: Array<Record<string, any>>;
  globalObjectIds: Record<string, string>;
};

