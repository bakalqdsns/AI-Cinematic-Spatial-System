/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ObjectAppearanceDetail } from './ObjectAppearanceDetail';
export type CrossFrameObjectDetail = {
  globalId: string;
  classLabel: string;
  totalAppearances: number;
  appearances: Array<ObjectAppearanceDetail>;
  trajectory: Record<string, any>;
  layerHistory: Array<Record<string, any>>;
};

