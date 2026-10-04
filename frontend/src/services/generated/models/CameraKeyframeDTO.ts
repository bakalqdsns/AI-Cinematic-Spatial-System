/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * One keyframe in the camera path.
 */
export type CameraKeyframeDTO = {
  time: number;
  /**
   * [x, y, z] world position
   */
  position: Array<number>;
  /**
   * [x, y, z] look-at target
   */
  target: Array<number>;
  /**
   * Vertical FOV in degrees
   */
  fov: number;
};

