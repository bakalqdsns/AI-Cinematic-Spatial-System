/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $BatchStatusEntry = {
  properties: {
    name: {
      type: 'string',
      isRequired: true,
    },
    status: {
      type: 'string',
      isRequired: true,
    },
    started_at: {
      type: 'number',
    },
    finished_at: {
      type: 'any-of',
      contains: [{
        type: 'number',
      }, {
        type: 'null',
      }],
    },
    error: {
      type: 'any-of',
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    visual_prompt: {
      type: 'any-of',
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    asset: {
      type: 'any-of',
      contains: [{
        type: 'dictionary',
        contains: {
          properties: {
          },
        },
      }, {
        type: 'null',
      }],
    },
  },
} as const;
