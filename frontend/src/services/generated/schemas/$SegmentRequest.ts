/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $SegmentRequest = {
  properties: {
    imageUrl: {
      type: 'string',
      isRequired: true,
    },
    projectId: {
      type: 'any-of',
      description: `Optional project ID — when set, masks are persisted`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
  },
} as const;
