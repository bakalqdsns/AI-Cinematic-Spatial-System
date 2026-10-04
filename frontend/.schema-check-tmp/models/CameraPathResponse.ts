/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CameraKeyframeDTO } from './CameraKeyframeDTO';
/**
 * Response — 1 or 2 keyframes (Phase 1: linear start/end interpolation).
 */
export type CameraPathResponse = {
  movement: string;
  shotSize: string;
  durationSeconds: number;
  keyframes: Array<CameraKeyframeDTO>;
};

