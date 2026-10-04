/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Generate paper-diorama texture for a full depth layer (not just one object).
 *
 * 与 PaperDioramaRequest 的区别：
 * - PaperDiorama：切割单个物体的 mask，将物体转为纸模纹理（逐 object）
 * - PaperLayer  ：对整层图像应用纸模效果，可选叠加 layerMask（逐 depth layer）
 */
export type PaperLayerRequest = {
  /**
   * Layer image URL or base64 data URL (RGBA PNG)
   */
  layerImageUrl: string;
  /**
   * Optional layer mask base64 PNG
   */
  layerMaskUrl?: (string | null);
  thicknessMin?: number;
  thicknessMax?: number;
  outlineWidth?: number;
  colorLevels?: number;
  styleStrength?: number;
  /**
   * Optional project ID — when set, 5 paper textures are persisted
   */
  projectId?: (string | null);
  /**
   * Optional depth layer key (foreground/midground/background/sky) — used for organising saved files
   */
  layerKey?: (string | null);
};

