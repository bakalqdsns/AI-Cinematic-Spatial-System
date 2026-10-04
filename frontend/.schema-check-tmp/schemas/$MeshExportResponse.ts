/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $MeshExportResponse = {
  description: `导出结果响应。`,
  properties: {
    mesh_id: {
      type: 'string',
      isRequired: true,
    },
    scope: {
      type: 'string',
      isRequired: true,
    },
    format: {
      type: 'string',
      isRequired: true,
    },
    file_name: {
      type: 'any-of',
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    file_size: {
      type: 'any-of',
      contains: [{
        type: 'number',
      }, {
        type: 'null',
      }],
    },
    file_sha256: {
      type: 'any-of',
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    object_count: {
      type: 'number',
      isRequired: true,
    },
    vertex_count: {
      type: 'number',
      isRequired: true,
    },
    face_count: {
      type: 'number',
      isRequired: true,
    },
    include_textures: {
      type: 'boolean',
      isRequired: true,
    },
    success: {
      type: 'boolean',
      isRequired: true,
    },
    error: {
      type: 'any-of',
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    blender_available: {
      type: 'boolean',
      isRequired: true,
    },
    project_id: {
      type: 'any-of',
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    download_url: {
      type: 'any-of',
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
  },
} as const;
