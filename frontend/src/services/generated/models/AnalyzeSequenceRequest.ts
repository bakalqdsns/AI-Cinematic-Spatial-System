/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Analyze an image sequence (multiple frames from the same shot).
 */
export type AnalyzeSequenceRequest = {
  /**
   * Shot ID
   */
  shotId: string;
  /**
   * Frame IDs in order
   */
  frameIds: Array<string>;
  /**
   * Image URLs corresponding to each frame
   */
  imageUrls: Array<string>;
  /**
   * Optional project ID for persistence
   */
  projectId?: (string | null);
  /**
   * Enable cross-frame object tracking
   */
  enableTracking?: boolean;
  /**
   * Tracking mode
   */
  trackingMode?: 'vlm' | 'semantic' | 'iou' | 'hybrid';
  /**
   * Optional per-frame types (same length as frameIds)
   */
  frameTypes?: (Array<'wide_shot' | 'medium_shot' | 'close_up' | 'extreme_close_up' | 'over_shoulder' | 'pov' | 'establishing'> | null);
  /**
   * Optional per-frame descriptions
   */
  frameDescriptions?: (Array<string> | null);
  /**
   * Matching threshold
   */
  matchingThreshold?: number;
  /**
   * Max tracking candidates
   */
  maxCandidatesPerObject?: number;
};

