/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $ComposeResponse = {
  description: `Response for POST /projects/{project_id}/compose.`,
  properties: {
    outputPath: {
      type: 'string',
      description: `Absolute path to the composed MP4.`,
      isRequired: true,
    },
    durationSeconds: {
      type: 'number',
      description: `Total duration of the output in seconds.`,
      isRequired: true,
    },
    format: {
      type: 'string',
      description: `Output container format.`,
    },
  },
} as const;
