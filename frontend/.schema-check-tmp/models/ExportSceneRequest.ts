/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 导出完整场景。
 */
export type ExportSceneRequest = {
  /**
   * 项目 ID（可选，不提供则不持久化）
   */
  project_id?: (string | null);
  /**
   * 完整 AicssResult（strip_stack 模式可为空）
   */
  analysis_result?: Record<string, any>;
  /**
   * 前端 splitDepthLayers() 结果
   */
  depth_split_result?: Record<string, any>;
  /**
   * depthLayerDioramaAssets 字典（strip_stack 模式可为空）
   */
  layer_assets?: Record<string, any>;
  /**
   * objectDioramaAssets 字典
   */
  object_assets?: Record<string, any>;
  /**
   * 物体 3D 偏移
   */
  billboard_offsets?: Record<string, any>;
  /**
   * 前端 LayerRegion[] 数组：用户自由选区，用于多面片3D重建导出
   */
  regions?: Array<Record<string, any>>;
  /**
   * 前端 stripStack 数组（逐层剥离流水线产物）。每项包含 regionId, baseImageDataUrl, inpaintResultUrl, billboardUrl, layerPolygon, depthLayer, depthValue, colorIndex。最后一项的 inpaintResultUrl 就是剥去所有层后剩下的纯背景纹理。
   */
  strip_stack?: Array<Record<string, any>>;
  /**
   * glb | fbx
   */
  format?: string;
  include_textures?: boolean;
};

