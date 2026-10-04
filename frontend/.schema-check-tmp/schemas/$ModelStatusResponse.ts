/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $ModelStatusResponse = {
  properties: {
    model_mode: {
      type: 'string',
      isRequired: true,
    },
    models: {
      type: 'dictionary',
      contains: {
        type: 'ModelDownloadItem',
      },
      isRequired: true,
    },
  },
} as const;
