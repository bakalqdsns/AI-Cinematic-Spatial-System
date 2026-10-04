/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $FrameLink = {
  properties: {
    sourceFrameId: {
      type: 'string',
      isRequired: true,
    },
    targetFrameId: {
      type: 'string',
      isRequired: true,
    },
    linkType: {
      type: 'Enum',
      isRequired: true,
    },
    confidence: {
      type: 'number',
      isRequired: true,
    },
    sharedObjects: {
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
    sharedClasses: {
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
