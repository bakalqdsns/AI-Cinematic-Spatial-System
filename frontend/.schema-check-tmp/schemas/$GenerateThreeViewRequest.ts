/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $GenerateThreeViewRequest = {
  properties: {
    character_id: {
      type: 'string',
      isRequired: true,
    },
    character_name: {
      type: 'string',
      isRequired: true,
    },
    character_gender: {
      type: 'string',
    },
    character_age: {
      type: 'string',
    },
    character_personality: {
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
      description: `Base64 or URL`,
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
