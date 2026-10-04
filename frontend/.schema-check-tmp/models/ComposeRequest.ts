/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AudioTrack } from './AudioTrack';
import type { ColorGrade } from './ColorGrade';
/**
 * Request body for POST /projects/{project_id}/compose.
 */
export type ComposeRequest = {
  /**
   * Ordered list of source MP4 clip paths.
   */
  clipPaths: Array<string>;
  /**
   * Per-clip target durations (seconds). Informational; used for transition clamping. When empty, durations are probed from the clips.
   */
  durations?: Array<number>;
  /**
   * Transition kind applied between adjacent clips.
   */
  transition?: 'cut' | 'dissolve' | 'fade' | 'wipe';
  /**
   * Transition duration in seconds.
   */
  transitionDuration?: number;
  /**
   * Optional audio tracks mixed onto the final video (T04).
   */
  audioTracks?: (Array<AudioTrack> | null);
  /**
   * Optional color grade applied as the last step (T05).
   */
  colorGrade?: (ColorGrade | null);
};

