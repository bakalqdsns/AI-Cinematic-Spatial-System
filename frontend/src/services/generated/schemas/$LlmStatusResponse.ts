/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $LlmStatusResponse = {
  properties: {
    running: {
      type: 'boolean',
      isRequired: true,
    },
    port: {
      type: 'number',
      isRequired: true,
    },
    model: {
      type: 'any-of',
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
      isRequired: true,
    },
    model_found: {
      type: 'boolean',
      isRequired: true,
    },
  },
} as const;
