/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $GenerateSceneAssetRequest = {
  properties: {
    scene_id: {
      type: 'string',
      isRequired: true,
    },
    location: {
      type: 'string',
      isRequired: true,
    },
    time: {
      type: 'string',
    },
    atmosphere: {
      type: 'string',
    },
    visual_prompt: {
      type: 'any-of',
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    reference_image: {
      type: 'any-of',
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    project_id: {
      type: 'any-of',
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
  },
} as const;
