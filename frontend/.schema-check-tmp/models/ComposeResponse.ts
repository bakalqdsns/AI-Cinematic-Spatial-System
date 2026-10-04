/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Response for POST /projects/{project_id}/compose.
 */
export type ComposeResponse = {
  /**
   * Absolute path to the composed MP4.
   */
  outputPath: string;
  /**
   * Total duration of the output in seconds.
   */
  durationSeconds: number;
  /**
   * Output container format.
   */
  format?: string;
};

