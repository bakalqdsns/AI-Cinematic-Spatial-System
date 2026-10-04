/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $LayersRequest = {
  properties: {
    depthMap: {
      type: 'string',
      description: `Base64-encoded depth PNG`,
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
    imageWidth: {
      type: 'number',
    },
    imageHeight: {
      type: 'number',
    },
    projectId: {
      type: 'any-of',
      description: `Optional project ID — when set, layer images are persisted`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
  },
} as const;
