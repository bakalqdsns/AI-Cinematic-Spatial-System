/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 导出结果响应。
 */
export type MeshExportResponse = {
  mesh_id: string;
  scope: string;
  format: string;
  file_name?: (string | null);
  file_size?: (number | null);
  file_sha256?: (string | null);
  object_count: number;
  vertex_count: number;
  face_count: number;
  include_textures: boolean;
  success: boolean;
  error?: (string | null);
  blender_available: boolean;
  project_id?: (string | null);
  download_url?: (string | null);
};

