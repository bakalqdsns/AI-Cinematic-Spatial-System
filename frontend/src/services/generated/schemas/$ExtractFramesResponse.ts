/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $ExtractFramesResponse = {
  properties: {
    frame_paths: {
      type: 'array',
      contains: {
        type: 'string',
      },
      isRequired: true,
    },
    frame_count: {
      type: 'number',
      isRequired: true,
    },
  },
} as const;
