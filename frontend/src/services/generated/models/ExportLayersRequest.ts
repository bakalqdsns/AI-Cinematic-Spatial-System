/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 导出深度分层。
 */
export type ExportLayersRequest = {
  project_id?: (string | null);
  /**
   * depthLayerDioramaAssets 字典
   */
  layer_assets?: Record<string, any>;
  /**
   * glb | fbx
   */
  format?: string;
  include_textures?: boolean;
};

