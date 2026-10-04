/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 从 Analyze 物体列表自动生成遮挡空洞 mask（不跑 LaMa）。
 */
export type OcclusionHolesRequest = {
  /**
   * DetectedObject[]（需含 id / maskDataUrl / depth / polygon）
   */
  objects: Array<Record<string, any>>;
  imageWidth: number;
  imageHeight: number;
  /**
   * 仅对这些 objectId 生成空洞；省略则全部
   */
  targetObjectIds?: (Array<string> | null);
  /**
   * peel=整物体 mask；occluded_interior=仅被更近物体遮挡的重叠区
   */
  mode?: string;
};

