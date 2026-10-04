/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $FrameResult = {
  properties: {
    frameId: {
      type: 'string',
      isRequired: true,
    },
    frameIndex: {
      type: 'number',
      isRequired: true,
    },
    frameType: {
      type: 'any-of',
      contains: [{
        type: 'Enum',
      }, {
        type: 'null',
      }],
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
    vlmScene: {
      type: 'any-of',
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    vlmClasses: {
      type: 'any-of',
      contains: [{
        type: 'array',
        contains: {
          type: 'string',
        },
      }, {
        type: 'null',
      }],
    },
  },
} as const;
