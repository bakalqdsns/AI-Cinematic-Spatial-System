/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $ComposeRequest = {
  description: `Request body for POST /projects/{project_id}/compose.`,
  properties: {
    clipPaths: {
      type: 'array',
      contains: {
        type: 'string',
      },
      isRequired: true,
    },
    durations: {
      type: 'array',
      contains: {
        type: 'number',
      },
    },
    transition: {
      type: 'Enum',
    },
    transitionDuration: {
      type: 'number',
      description: `Transition duration in seconds.`,
      maximum: 5,
    },
    audioTracks: {
      type: 'any-of',
      description: `Optional audio tracks mixed onto the final video (T04).`,
      contains: [{
        type: 'array',
        contains: {
          type: 'AudioTrack',
        },
      }, {
        type: 'null',
      }],
    },
    colorGrade: {
      type: 'any-of',
      description: `Optional color grade applied as the last step (T05).`,
      contains: [{
        type: 'ColorGrade',
      }, {
        type: 'null',
      }],
    },
  },
} as const;
