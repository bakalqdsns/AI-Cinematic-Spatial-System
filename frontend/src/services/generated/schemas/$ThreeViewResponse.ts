/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $ThreeViewResponse = {
  properties: {
    character_id: {
      type: 'string',
      isRequired: true,
    },
    visual_prompt: {
      type: 'string',
      isRequired: true,
    },
    three_view_images: {
      type: 'dictionary',
      contains: {
        type: 'any-of',
        contains: [{
          type: 'string',
        }, {
          type: 'null',
        }],
      },
      isRequired: true,
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
