/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $SceneAssetResponse = {
  properties: {
    scene_id: {
      type: 'string',
      isRequired: true,
    },
    visual_prompt: {
      type: 'string',
      isRequired: true,
    },
    keyframe_images: {
      type: 'dictionary',
      contains: {
        type: 'string',
      },
      isRequired: true,
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
