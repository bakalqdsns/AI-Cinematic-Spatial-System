/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $ScriptScene = {
  description: `A scene extracted from a script, used by from-script endpoint.`,
  properties: {
    sceneId: {
      type: 'string',
      isRequired: true,
    },
    frameId: {
      type: 'string',
      isRequired: true,
    },
    imageUrl: {
      type: 'string',
      isRequired: true,
    },
    sceneType: {
      type: 'any-of',
      contains: [{
        type: 'Enum',
      }, {
        type: 'null',
      }],
    },
    description: {
      type: 'any-of',
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    characters: {
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
    location: {
      type: 'any-of',
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    timeOfDay: {
      type: 'any-of',
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
  },
} as const;
