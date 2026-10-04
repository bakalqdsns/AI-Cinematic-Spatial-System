/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $ShotResponse = {
  properties: {
    shotId: {
      type: 'string',
      isRequired: true,
    },
    projectId: {
      type: 'string',
      isRequired: true,
    },
    createdAt: {
      type: 'string',
      isRequired: true,
    },
    updatedAt: {
      type: 'string',
      isRequired: true,
    },
    status: {
      type: 'string',
      isRequired: true,
    },
    frameCount: {
      type: 'number',
      isRequired: true,
    },
    description: {
      type: 'any-of',
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    sceneType: {
      type: 'any-of',
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
  },
} as const;
