/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $SegmentFramesRequest = {
  properties: {
    frame_paths: {
      type: 'array',
      contains: {
        type: 'string',
      },
      isRequired: true,
    },
    character_name: {
      type: 'string',
      isRequired: true,
    },
    action_name: {
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
