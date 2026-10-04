/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $CreateShotRequest = {
  properties: {
    shotId: {
      type: 'string',
      description: `Shot ID`,
      isRequired: true,
    },
    description: {
      type: 'any-of',
      description: `Shot description`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    sceneType: {
      type: 'any-of',
      description: `Scene type (e.g. indoor, outdoor)`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
  },
} as const;
