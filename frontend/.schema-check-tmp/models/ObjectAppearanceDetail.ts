/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BoundingBox } from './BoundingBox';
export type ObjectAppearanceDetail = {
  frameId: string;
  frameIndex: number;
  localId: string;
  bbox: BoundingBox;
  depth: number;
  matchConfidence: number;
  layer?: ('foreground' | 'midground' | 'background' | 'sky' | null);
};

