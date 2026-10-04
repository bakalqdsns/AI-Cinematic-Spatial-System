/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type FrameLink = {
  sourceFrameId: string;
  targetFrameId: string;
  linkType: 'same_scene' | 'same_character' | 'continuity' | 'contrast';
  confidence: number;
  sharedObjects?: (Array<string> | null);
  sharedClasses?: (Array<string> | null);
};

