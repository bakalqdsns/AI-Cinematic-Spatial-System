/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $PaperStyleRequest = {
  properties: {
    imageUrl: {
      type: 'string',
      description: `Image URL or base64 data URL`,
      isRequired: true,
    },
    colorLevels: {
      type: 'number',
      description: `Colour quantisation levels (lower = flatter)`,
      maximum: 30,
      minimum: 3,
    },
    styleStrength: {
      type: 'number',
      description: `Bilateral filter strength`,
      maximum: 1,
    },
    edgeLow: {
      type: 'number',
      description: `Canny edge low threshold`,
      maximum: 255,
    },
    edgeHigh: {
      type: 'number',
      description: `Canny edge high threshold`,
      maximum: 255,
    },
    projectId: {
      type: 'any-of',
      description: `Optional project ID — when set, styled image is persisted`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
  },
} as const;
