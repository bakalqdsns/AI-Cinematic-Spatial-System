/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $LayerExportResponse = {
  properties: {
    width: {
      type: 'number',
      description: `Image width in pixels`,
      isRequired: true,
    },
    height: {
      type: 'number',
      description: `Image height in pixels`,
      isRequired: true,
    },
    layers: {
      type: 'dictionary',
      contains: {
        type: 'LayerDataUri',
      },
      isRequired: true,
    },
    zOffsets: {
      type: 'array',
      contains: {
        type: 'LayerZOffset',
      },
      isRequired: true,
    },
    objects: {
      type: 'array',
      contains: {
        type: 'ObjectAssetSummary',
      },
    },
    ground: {
      type: 'any-of',
      description: `Reconstructed ground plane asset (Phase 2)`,
      contains: [{
        type: 'GroundAssetSummary',
      }, {
        type: 'null',
      }],
    },
    layer_assignment: {
      type: 'dictionary',
      contains: {
        type: 'array',
        contains: {
          type: 'string',
        },
      },
    },
  },
} as const;
