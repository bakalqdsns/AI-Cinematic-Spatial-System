/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ScriptScene } from './ScriptScene';
/**
 * Analyze frames defined by script scenes.
 */
export type AnalyzeFromScriptRequest = {
  shotId: string;
  scenes: Array<ScriptScene>;
  projectId?: (string | null);
  enableTracking?: boolean;
  trackingMode?: 'vlm' | 'semantic' | 'iou' | 'hybrid';
};

