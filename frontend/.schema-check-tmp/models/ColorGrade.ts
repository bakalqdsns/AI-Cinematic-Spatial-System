/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Optional color grade applied as the final composition step.
 */
export type ColorGrade = {
  /**
   * Path to a .cube LUT file. When set, lut3d is applied first.
   */
  lut_path?: (string | null);
  /**
   * eq brightness.
   */
  brightness?: number;
  /**
   * eq contrast (1.0 = unity).
   */
  contrast?: number;
  /**
   * eq saturation (1.0 = unity).
   */
  saturation?: number;
};

