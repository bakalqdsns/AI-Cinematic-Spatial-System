/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $FrameResponse = {
  properties: {
    frameIndex: {
      type: 'number',
      isRequired: true,
    },
    frameId: {
      type: 'string',
      isRequired: true,
    },
    frameType: {
      type: 'any-of',
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    originalUrl: {
      type: 'string',
      isRequired: true,
    },
    depthMapUrl: {
      type: 'string',
      isRequired: true,
    },
    objects: {
      type: 'array',
      contains: {
        type: 'dictionary',
        contains: {
          properties: {
          },
        },
      },
      isRequired: true,
    },
    layers: {
      type: 'array',
      contains: {
        type: 'dictionary',
        contains: {
          properties: {
          },
        },
      },
      isRequired: true,
    },
    globalObjectIds: {
      type: 'dictionary',
      contains: {
        type: 'string',
      },
      isRequired: true,
    },
  },
} as const;
