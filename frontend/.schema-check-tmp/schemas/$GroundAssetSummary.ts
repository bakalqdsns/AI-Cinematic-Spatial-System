/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $GroundAssetSummary = {
  properties: {
    object_id: {
      type: 'string',
    },
    plane: {
      type: 'dictionary',
      contains: {
        properties: {
        },
      },
      isRequired: true,
    },
    plane_normal: {
      type: 'array',
      contains: {
        type: 'number',
      },
      isRequired: true,
    },
    centroid: {
      type: 'array',
      contains: {
        type: 'number',
      },
      isRequired: true,
    },
    bbox: {
      type: 'array',
      contains: {
        type: 'number',
      },
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
    depth_correction_data_uri: {
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
