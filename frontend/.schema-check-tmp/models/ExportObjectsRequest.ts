/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 导出检测到的物体。
 */
export type ExportObjectsRequest = {
  /**
   * 项目 ID（可选，不提供则不持久化）
   */
  project_id?: (string | null);
  /**
   * AicssResult JSON（objects 字段必须）
   */
  analysis_result: Record<string, any>;
  /**
   * 要导出的物体 ID 列表（None = 全部）
   */
  object_ids?: (Array<string> | null);
  /**
   * objectDioramaAssets 字典 { objectId: asset }
   */
  object_assets?: Record<string, any>;
  /**
   * billboardOffsets 字典 { objectId: { offsetX, offsetZ } }
   */
  billboard_offsets?: Record<string, any>;
  /**
   * 导出格式: glb | fbx
   */
  format?: string;
  /**
   * 是否嵌入纹理
   */
  include_textures?: boolean;
};

