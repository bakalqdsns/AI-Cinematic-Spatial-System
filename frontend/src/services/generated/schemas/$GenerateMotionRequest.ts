/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $GenerateMotionRequest = {
  properties: {
    shot_id: {
      type: 'string',
      isRequired: true,
    },
    character_id: {
      type: 'string',
      isRequired: true,
    },
    character_name: {
      type: 'string',
      isRequired: true,
    },
    action_prompt: {
      type: 'string',
      isRequired: true,
    },
    start_image: {
      type: 'any-of',
      description: `Base64 start frame`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    end_image: {
      type: 'any-of',
      description: `Base64 end frame`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    duration_seconds: {
      type: 'number',
      maximum: 30,
      minimum: 1,
    },
    video_provider: {
      type: 'string',
      description: `Video provider: dashscope | local_wan | svd`,
    },
    greenscreen: {
      type: 'boolean',
      description: `Render the action video against a flat green-screen background and apply a chroma-key pass during segmentation.`,
    },
    feather_edges: {
      type: 'boolean',
      description: `Snap SAM2 masks to nearby Canny edges to soften character silhouettes.`,
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
