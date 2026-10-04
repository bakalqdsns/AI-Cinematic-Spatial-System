/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $MultifaceRequest = {
  properties: {
    imageUrl: {
      type: 'string',
      isRequired: true,
    },
    objectId: {
      type: 'string',
      isRequired: true,
    },
    boundingBox: {
      type: 'dictionary',
      contains: {
        properties: {
        },
      },
      isRequired: true,
    },
    polygon: {
      type: 'array',
      contains: {
        type: 'array',
        contains: {
          type: 'number',
        },
      },
    },
    projectId: {
      type: 'any-of',
      description: `Optional project ID — when set, 6 face textures are persisted`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
  },
} as const;
