/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $PaperDioramaRequest = {
  properties: {
    imageUrl: {
      type: 'string',
      description: `Full image URL or base64 data URL`,
      isRequired: true,
    },
    maskDataUrl: {
      type: 'string',
      description: `Object mask base64 PNG, 255=object, 0=background`,
      isRequired: true,
    },
    thicknessMin: {
      type: 'number',
      description: `Min paper thickness in mm`,
      maximum: 20,
      minimum: 0.1,
    },
    thicknessMax: {
      type: 'number',
      description: `Max paper thickness in mm`,
      maximum: 20,
      minimum: 0.1,
    },
    outlineWidth: {
      type: 'number',
      description: `Paper-cut outline width in pixels`,
      maximum: 20,
    },
    colorLevels: {
      type: 'number',
      description: `Colour quantisation levels`,
      maximum: 30,
      minimum: 3,
    },
    styleStrength: {
      type: 'number',
      description: `Style smoothing strength`,
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
  },
} as const;
