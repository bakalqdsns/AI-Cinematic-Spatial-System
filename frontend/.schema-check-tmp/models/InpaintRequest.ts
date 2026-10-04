/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type InpaintRequest = {
  /**
   * Image to inpaint, base64 or URL
   */
  imageUrl: string;
  /**
   * Mask (RGBA), white (alpha=255)=area to inpaint, black (alpha=0)=keep
   */
  maskDataUrl: string;
  /**
   * Inpainting prompt (for compatibility; LaMa performs blind inpainting)
   */
  prompt: string;
  /**
   * Optional project ID — when set, inpaint result is persisted
   */
  projectId?: (string | null);
};

