/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $ExportSceneRequest = {
  description: `导出完整场景。`,
  properties: {
    project_id: {
      type: 'any-of',
      description: `项目 ID（可选，不提供则不持久化）`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    analysis_result: {
      type: 'dictionary',
      contains: {
        properties: {
        },
      },
    },
    depth_split_result: {
      type: 'dictionary',
      contains: {
        properties: {
        },
      },
    },
    layer_assets: {
      type: 'dictionary',
      contains: {
        properties: {
        },
      },
    },
    object_assets: {
      type: 'dictionary',
      contains: {
        properties: {
        },
      },
    },
    billboard_offsets: {
      type: 'dictionary',
      contains: {
        properties: {
        },
      },
    },
    regions: {
      type: 'array',
      contains: {
        type: 'dictionary',
        contains: {
          properties: {
          },
        },
      },
    },
    strip_stack: {
      type: 'array',
      contains: {
        type: 'dictionary',
        contains: {
          properties: {
          },
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
