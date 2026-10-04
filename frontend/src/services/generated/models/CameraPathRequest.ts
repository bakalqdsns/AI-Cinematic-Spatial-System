/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Request body for the camera-path generator.
 */
export type CameraPathRequest = {
  /**
   * One of the 13 CameraMovement values (Static, Dolly In, …)
   */
  cameraMovement: string;
  /**
   * One of the 10 ShotSize values (Wide Shot, Close-up, …)
   */
  shotSize: string;
  /**
   * Shot duration in seconds. Drives nothing in the keyframes themselves but is echoed back so the client can sanity-check.
   */
  durationSeconds?: number;
};

