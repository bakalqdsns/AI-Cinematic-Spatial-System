/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type PaperDioramaRequest = {
  /**
   * Full image URL or base64 data URL
   */
  imageUrl: string;
  /**
   * Object mask base64 PNG, 255=object, 0=background
   */
  maskDataUrl: string;
  /**
   * Min paper thickness in mm
   */
  thicknessMin?: number;
  /**
   * Max paper thickness in mm
   */
  thicknessMax?: number;
  /**
   * Paper-cut outline width in pixels
   */
  outlineWidth?: number;
  /**
   * Colour quantisation levels
   */
  colorLevels?: number;
  /**
   * Style smoothing strength
   */
  styleStrength?: number;
  /**
   * Optional project ID — when set, 5 paper textures are persisted
   */
  projectId?: (string | null);
};

