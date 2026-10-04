/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $VariationResponse = {
  properties: {
    character_id: {
      type: 'string',
      isRequired: true,
    },
    variation_id: {
      type: 'string',
      isRequired: true,
    },
    variation_prompt: {
      type: 'string',
      isRequired: true,
    },
    image: {
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
