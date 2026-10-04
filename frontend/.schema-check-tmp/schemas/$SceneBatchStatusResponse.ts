/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $SceneBatchStatusResponse = {
  properties: {
    project_id: {
      type: 'string',
      isRequired: true,
    },
    scenes: {
      type: 'dictionary',
      contains: {
        type: 'SceneBatchStatusEntry',
      },
      isRequired: true,
    },
    summary: {
      type: 'dictionary',
      contains: {
        properties: {
        },
      },
      isRequired: true,
    },
  },
} as const;
