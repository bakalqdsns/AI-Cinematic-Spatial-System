/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $CheckpointRequest = {
  properties: {
    phase: {
      type: 'string',
      isRequired: true,
    },
    startedAt: {
      type: 'string',
      isRequired: true,
    },
    finishedAt: {
      type: 'string',
      isRequired: true,
    },
    durationMs: {
      type: 'number',
      isRequired: true,
    },
  },
} as const;
