/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $GenerateShotsRequest = {
  properties: {
    script_data: {
      type: 'dictionary',
      contains: {
        properties: {
        },
      },
      isRequired: true,
    },
    shots_per_scene: {
      type: 'number',
      description: `Lower bound per scene. Total shot count is also driven by story_paragraph count — see /shots endpoint doc.`,
      maximum: 12,
      minimum: 1,
    },
    language: {
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
