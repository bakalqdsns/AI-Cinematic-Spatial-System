/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $AnalyzeRequest = {
  properties: {
    imageUrl: {
      type: 'string',
      isRequired: true,
    },
    shotId: {
      type: 'string',
      isRequired: true,
    },
    projectId: {
      type: 'any-of',
      description: `Optional project ID — when set, results are persisted to .workspace/projects/<id>/`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
  },
} as const;
