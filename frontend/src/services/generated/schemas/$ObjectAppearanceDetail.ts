/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $ObjectAppearanceDetail = {
  properties: {
    frameId: {
      type: 'string',
      isRequired: true,
    },
    frameIndex: {
      type: 'number',
      isRequired: true,
    },
    localId: {
      type: 'string',
      isRequired: true,
    },
    bbox: {
      type: 'BoundingBox',
      isRequired: true,
    },
    depth: {
      type: 'number',
      isRequired: true,
    },
    matchConfidence: {
      type: 'number',
      isRequired: true,
    },
    layer: {
      type: 'any-of',
      contains: [{
        type: 'Enum',
      }, {
        type: 'null',
      }],
    },
  },
} as const;
