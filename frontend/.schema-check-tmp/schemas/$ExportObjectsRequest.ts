/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $ExportObjectsRequest = {
  description: `导出检测到的物体。`,
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
      isRequired: true,
    },
    object_ids: {
      type: 'any-of',
      description: `要导出的物体 ID 列表（None = 全部）`,
      contains: [{
        type: 'array',
        contains: {
          type: 'string',
        },
      }, {
        type: 'null',
      }],
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
    format: {
      type: 'string',
      description: `导出格式: glb | fbx`,
    },
    include_textures: {
      type: 'boolean',
      description: `是否嵌入纹理`,
    },
  },
} as const;
