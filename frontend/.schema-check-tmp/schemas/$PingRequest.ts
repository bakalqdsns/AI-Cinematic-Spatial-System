/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $PingRequest = {
  properties: {
    component: {
      type: 'string',
      description: `llm | vlm | image | video`,
      isRequired: true,
    },
    name: {
      type: 'any-of',
      description: `Provider name override (uses current active if omitted)`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
  },
} as const;
