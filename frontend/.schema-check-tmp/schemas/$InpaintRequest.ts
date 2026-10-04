/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $InpaintRequest = {
  properties: {
    imageUrl: {
      type: 'string',
      description: `Image to inpaint, base64 or URL`,
      isRequired: true,
    },
    maskDataUrl: {
      type: 'string',
      description: `Mask (RGBA), white (alpha=255)=area to inpaint, black (alpha=0)=keep`,
      isRequired: true,
    },
    prompt: {
      type: 'string',
      description: `Inpainting prompt (for compatibility; LaMa performs blind inpainting)`,
      isRequired: true,
    },
    projectId: {
      type: 'any-of',
      description: `Optional project ID — when set, inpaint result is persisted`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
  },
} as const;
