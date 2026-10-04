/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * A scene extracted from a script, used by from-script endpoint.
 */
export type ScriptScene = {
  sceneId: string;
  frameId: string;
  imageUrl: string;
  sceneType?: ('wide_shot' | 'medium_shot' | 'close_up' | 'extreme_close_up' | 'over_shoulder' | 'pov' | 'establishing' | null);
  description?: (string | null);
  characters?: (Array<string> | null);
  location?: (string | null);
  timeOfDay?: (string | null);
};

