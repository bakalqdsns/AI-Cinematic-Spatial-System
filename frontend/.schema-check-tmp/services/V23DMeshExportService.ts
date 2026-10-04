/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BlenderCheckResponse } from '../models/BlenderCheckResponse';
import type { ExportLayersRequest } from '../models/ExportLayersRequest';
import type { ExportObjectsRequest } from '../models/ExportObjectsRequest';
import type { ExportSceneRequest } from '../models/ExportSceneRequest';
import type { MeshExportResponse } from '../models/MeshExportResponse';
import type { MeshListResponse } from '../models/MeshListResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import type { BaseHttpRequest } from '../core/BaseHttpRequest';
export class V23DMeshExportService {
  constructor(public readonly httpRequest: BaseHttpRequest) {}
  /**
   * Api Export Objects
   * 将检测到的物体导出为 3D mesh 文件。
   *
   * 支持按 object_ids 过滤，也支持传入 object_assets 以包含纹理。
   * Blender Headless 在后台完成 mesh 构建和导出。
   * @returns MeshExportResponse Successful Response
   * @throws ApiError
   */
  public apiExportObjectsApiAicssV2MeshesExportObjectsPost({
    requestBody,
  }: {
    requestBody: ExportObjectsRequest,
  }): CancelablePromise<MeshExportResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/v2/meshes/export-objects',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Api Export Layers
   * 将深度分层导出为 3D mesh 文件。
   *
   * 每个有纹理的层（foreground/midground/background/sky）单独导出为一个 mesh，
   * 包含 BoxGeometry 和 paper diorama 纹理。
   * @returns MeshExportResponse Successful Response
   * @throws ApiError
   */
  public apiExportLayersApiAicssV2MeshesExportLayersPost({
    requestBody,
  }: {
    requestBody: ExportLayersRequest,
  }): CancelablePromise<MeshExportResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/v2/meshes/export-layers',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Api Export Scene
   * 导出完整场景（所有深度层 + 所有物体 + 可选 strip-stack billboards + 背景平面）。
   *
   * 生成一个包含所有 paper diorama 元素的组合 GLB/FBX 文件。
   * 当 request.strip_stack 非空时，每条 StripStep 会作为一个 PlaneGeometry billboard
   * 贴在对应 depthLayer 位置，最后一条 step 的 inpaintResultUrl 作为 BackgroundPlane。
   * 当 request.regions 非空时，每个 LayerRegion 也会导出为 PlaneGeometry（按 depthValue 精细 Z）。
   * @returns MeshExportResponse Successful Response
   * @throws ApiError
   */
  public apiExportSceneApiAicssV2MeshesExportScenePost({
    requestBody,
  }: {
    requestBody: ExportSceneRequest,
  }): CancelablePromise<MeshExportResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/v2/meshes/export-scene',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Api List Meshes
   * 列出项目中所有已导出的 mesh 文件。
   *
   * 支持 ?scope=object|layer|scene 过滤。
   * @returns MeshListResponse Successful Response
   * @throws ApiError
   */
  public apiListMeshesApiAicssV2MeshesListGet({
    projectId,
  }: {
    projectId: string,
  }): CancelablePromise<MeshListResponse> {
    return this.httpRequest.request({
      method: 'GET',
      url: '/api/aicss/v2/meshes/list',
      query: {
        'project_id': projectId,
      },
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Api Mesh Info
   * 获取单个 mesh 导出的元数据。
   * @returns any Successful Response
   * @throws ApiError
   */
  public apiMeshInfoApiAicssV2MeshesMeshIdInfoGet({
    meshId,
    projectId,
  }: {
    meshId: string,
    projectId: string,
  }): CancelablePromise<any> {
    return this.httpRequest.request({
      method: 'GET',
      url: '/api/aicss/v2/meshes/{mesh_id}/info',
      path: {
        'mesh_id': meshId,
      },
      query: {
        'project_id': projectId,
      },
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Api Download Mesh
   * 下载指定的 mesh 文件。
   *
   * 支持 GLB 和 FBX 格式。
   * @returns any Successful Response
   * @throws ApiError
   */
  public apiDownloadMeshApiAicssV2MeshesMeshIdDownloadGet({
    meshId,
    projectId,
  }: {
    meshId: string,
    projectId: string,
  }): CancelablePromise<any> {
    return this.httpRequest.request({
      method: 'GET',
      url: '/api/aicss/v2/meshes/{mesh_id}/download',
      path: {
        'mesh_id': meshId,
      },
      query: {
        'project_id': projectId,
      },
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Api Delete Mesh
   * 删除指定的 mesh 导出条目和文件。
   * @returns any Successful Response
   * @throws ApiError
   */
  public apiDeleteMeshApiAicssV2MeshesMeshIdDelete({
    meshId,
    projectId,
  }: {
    meshId: string,
    projectId: string,
  }): CancelablePromise<any> {
    return this.httpRequest.request({
      method: 'DELETE',
      url: '/api/aicss/v2/meshes/{mesh_id}',
      path: {
        'mesh_id': meshId,
      },
      query: {
        'project_id': projectId,
      },
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Api Check Blender
   * 检查 Blender 是否可用于 3D mesh 导出。
   *
   * 返回 Blender 路径、版本号和可用性状态。
   * @returns BlenderCheckResponse Successful Response
   * @throws ApiError
   */
  public apiCheckBlenderApiAicssV2MeshesCheckGet(): CancelablePromise<BlenderCheckResponse> {
    return this.httpRequest.request({
      method: 'GET',
      url: '/api/aicss/v2/meshes/check',
    });
  }
}
