/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $MotionResponse = {
  properties: {
    shot_id: {
      type: 'string',
      isRequired: true,
    },
    character_id: {
      type: 'string',
      isRequired: true,
    },
    status: {
      type: 'string',
      isRequired: true,
    },
    video_path: {
      type: 'any-of',
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    frame_count: {
      type: 'number',
    },
    segmented_frames: {
      type: 'array',
      contains: {
        type: 'dictionary',
        contains: {
          properties: {
          },
        },
      },
    },
    project_id: {
      type: 'any-of',
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
  },
} as const;
