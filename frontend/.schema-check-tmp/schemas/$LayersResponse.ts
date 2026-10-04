/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $LayersResponse = {
  description: `\`POST /api/aicss/layers\` response.`,
  properties: {
    layers: {
      type: 'array',
      contains: {
        type: 'dictionary',
        contains: {
          properties: {
          },
        },
      },
      isRequired: true,
    },
    width: {
      type: 'number',
      isRequired: true,
    },
    height: {
      type: 'number',
      isRequired: true,
    },
    savedFiles: {
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
  },
} as const;
