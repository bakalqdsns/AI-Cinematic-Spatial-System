/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type FrameResult = {
  frameId: string;
  frameIndex: number;
  frameType?: ('wide_shot' | 'medium_shot' | 'close_up' | 'extreme_close_up' | 'over_shoulder' | 'pov' | 'establishing' | null);
  depthMapUrl: string;
  objects: Array<Record<string, any>>;
  layers: Array<Record<string, any>>;
  globalObjectIds: Record<string, string>;
  vlmScene?: (string | null);
  vlmClasses?: (Array<string> | null);
};

