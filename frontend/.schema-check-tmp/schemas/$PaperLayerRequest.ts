/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $PaperLayerRequest = {
  description: `Generate paper-diorama texture for a full depth layer (not just one object).
  与 PaperDioramaRequest 的区别：
  - PaperDiorama：切割单个物体的 mask，将物体转为纸模纹理（逐 object）
  - PaperLayer  ：对整层图像应用纸模效果，可选叠加 layerMask（逐 depth layer）`,
  properties: {
    layerImageUrl: {
      type: 'string',
      description: `Layer image URL or base64 data URL (RGBA PNG)`,
      isRequired: true,
    },
    layerMaskUrl: {
      type: 'any-of',
      description: `Optional layer mask base64 PNG`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    thicknessMin: {
      type: 'number',
      maximum: 20,
      minimum: 0.1,
    },
    thicknessMax: {
      type: 'number',
      maximum: 20,
      minimum: 0.1,
    },
    outlineWidth: {
      type: 'number',
      maximum: 20,
    },
    colorLevels: {
      type: 'number',
      maximum: 30,
      minimum: 3,
    },
    styleStrength: {
      type: 'number',
      maximum: 1,
    },
    projectId: {
      type: 'any-of',
      description: `Optional project ID — when set, 5 paper textures are persisted`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    layerKey: {
      type: 'any-of',
      description: `Optional depth layer key (foreground/midground/background/sky) — used for organising saved files`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
  },
} as const;
