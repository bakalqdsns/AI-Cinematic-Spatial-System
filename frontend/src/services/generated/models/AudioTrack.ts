/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * A single audio track layered onto the final video.
 */
export type AudioTrack = {
  /**
   * bgm loops to video length; sfx/voiceover are delayed to start_at.
   */
  kind: 'bgm' | 'sfx' | 'voiceover';
  /**
   * Absolute path to the audio file (mp3/wav/aac).
   */
  path: string;
  /**
   * Volume multiplier applied to this track (1.0 = unity).
   */
  volume?: number;
  /**
   * Seconds offset into the final timeline where this track begins.
   */
  start_at?: number;
};

