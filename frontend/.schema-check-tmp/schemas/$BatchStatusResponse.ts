/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $BatchStatusResponse = {
  properties: {
    project_id: {
      type: 'string',
      isRequired: true,
    },
    characters: {
      type: 'dictionary',
      contains: {
        type: 'BatchStatusEntry',
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
