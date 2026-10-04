/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $ObjectAssetSummary = {
  properties: {
    object_id: {
      type: 'string',
      isRequired: true,
    },
    label: {
      type: 'string',
      isRequired: true,
    },
    score: {
      type: 'number',
      isRequired: true,
    },
    bbox: {
      type: 'array',
      contains: {
        type: 'number',
      },
      isRequired: true,
    },
    depth_mean: {
      type: 'number',
      isRequired: true,
    },
    depth_min: {
      type: 'number',
      isRequired: true,
    },
    depth_max: {
      type: 'number',
      isRequired: true,
    },
    layer_hint: {
      type: 'string',
      isRequired: true,
    },
    z_offset: {
      type: 'number',
      isRequired: true,
    },
    cutout_data_uri: {
      type: 'string',
      isRequired: true,
    },
    meta: {
      type: 'dictionary',
      contains: {
        properties: {
        },
      },
      isRequired: true,
    },
  },
} as const;
