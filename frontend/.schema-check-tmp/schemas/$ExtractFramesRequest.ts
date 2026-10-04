/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $ExtractFramesRequest = {
  properties: {
    video_path: {
      type: 'string',
      isRequired: true,
    },
    output_dir: {
      type: 'any-of',
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    fps: {
      type: 'number',
    },
    max_frames: {
      type: 'number',
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
