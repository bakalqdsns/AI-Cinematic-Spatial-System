/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $ShotListResponse = {
  properties: {
    count: {
      type: 'number',
      isRequired: true,
    },
    shots: {
      type: 'array',
      contains: {
        type: 'ShotResponse',
      },
      isRequired: true,
    },
  },
} as const;
