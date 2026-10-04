/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $OcclusionHolesResponse = {
  properties: {
    holes: {
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
    mergedMaskDataUrl: {
      type: 'any-of',
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    mode: {
      type: 'string',
      isRequired: true,
    },
    count: {
      type: 'number',
      isRequired: true,
    },
  },
} as const;
