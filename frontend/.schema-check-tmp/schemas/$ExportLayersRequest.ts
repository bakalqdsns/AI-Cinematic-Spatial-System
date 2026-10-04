/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $ExportLayersRequest = {
  description: `导出深度分层。`,
  properties: {
    project_id: {
      type: 'any-of',
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    layer_assets: {
      type: 'dictionary',
      contains: {
        properties: {
        },
      },
    },
    format: {
      type: 'string',
      description: `glb | fbx`,
    },
    include_textures: {
      type: 'boolean',
    },
  },
} as const;
