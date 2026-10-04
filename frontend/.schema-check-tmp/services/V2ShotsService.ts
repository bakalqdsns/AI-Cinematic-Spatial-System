/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ArchiveShotResponse } from '../models/ArchiveShotResponse';
import type { CreateShotRequest } from '../models/CreateShotRequest';
import type { FrameResponse } from '../models/FrameResponse';
import type { ShotListResponse } from '../models/ShotListResponse';
import type { ShotResponse } from '../models/ShotResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import type { BaseHttpRequest } from '../core/BaseHttpRequest';
export class V2ShotsService {
  constructor(public readonly httpRequest: BaseHttpRequest) {}
  /**
   * Create Shot
   * Create a new shot under a project.
   *
   * Creates the shot directory structure and initializes manifest.json.
   * @returns ShotResponse Successful Response
   * @throws ApiError
   */
  public createShotApiAicssV2ProjectsProjectIdShotsPost({
    projectId,
    requestBody,
  }: {
    projectId: string,
    requestBody: CreateShotRequest,
  }): CancelablePromise<ShotResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/v2/projects/{project_id}/shots',
      path: {
        'project_id': projectId,
      },
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * List Shots
   * List all shots under a project.
   * @returns ShotListResponse Successful Response
   * @throws ApiError
   */
  public listShotsApiAicssV2ProjectsProjectIdShotsGet({
    projectId,
  }: {
    projectId: string,
  }): CancelablePromise<ShotListResponse> {
    return this.httpRequest.request({
      method: 'GET',
      url: '/api/aicss/v2/projects/{project_id}/shots',
      path: {
        'project_id': projectId,
      },
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Get Shot
   * Get shot details including frame list.
   * @returns ShotResponse Successful Response
   * @throws ApiError
   */
  public getShotApiAicssV2ProjectsProjectIdShotsShotIdGet({
    projectId,
    shotId,
  }: {
    projectId: string,
    shotId: string,
  }): CancelablePromise<ShotResponse> {
    return this.httpRequest.request({
      method: 'GET',
      url: '/api/aicss/v2/projects/{project_id}/shots/{shot_id}',
      path: {
        'project_id': projectId,
        'shot_id': shotId,
      },
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Delete Shot
   * Delete a shot and all its frames.
   * @returns any Successful Response
   * @throws ApiError
   */
  public deleteShotApiAicssV2ProjectsProjectIdShotsShotIdDelete({
    projectId,
    shotId,
  }: {
    projectId: string,
    shotId: string,
  }): CancelablePromise<any> {
    return this.httpRequest.request({
      method: 'DELETE',
      url: '/api/aicss/v2/projects/{project_id}/shots/{shot_id}',
      path: {
        'project_id': projectId,
        'shot_id': shotId,
      },
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Get Frame
   * Get single frame analysis result.
   * @returns FrameResponse Successful Response
   * @throws ApiError
   */
  public getFrameApiAicssV2ProjectsProjectIdShotsShotIdFramesFrameIndexGet({
    projectId,
    shotId,
    frameIndex,
  }: {
    projectId: string,
    shotId: string,
    frameIndex: number,
  }): CancelablePromise<FrameResponse> {
    return this.httpRequest.request({
      method: 'GET',
      url: '/api/aicss/v2/projects/{project_id}/shots/{shot_id}/frames/{frame_index}',
      path: {
        'project_id': projectId,
        'shot_id': shotId,
        'frame_index': frameIndex,
      },
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Get Frame Image
   * Get frame image (original or depth map) as binary PNG.
   *
   * Args:
   * kind: "original" for raw frame, "depth" for depth map
   * @returns any Successful Response
   * @throws ApiError
   */
  public getFrameImageApiAicssV2ProjectsProjectIdShotsShotIdFramesFrameIndexImageGet({
    projectId,
    shotId,
    frameIndex,
    kind = 'original',
  }: {
    projectId: string,
    shotId: string,
    frameIndex: number,
    kind?: 'original' | 'depth',
  }): CancelablePromise<any> {
    return this.httpRequest.request({
      method: 'GET',
      url: '/api/aicss/v2/projects/{project_id}/shots/{shot_id}/frames/{frame_index}/image',
      path: {
        'project_id': projectId,
        'shot_id': shotId,
        'frame_index': frameIndex,
      },
      query: {
        'kind': kind,
      },
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Archive Shot
   * 将 shot 相关资产打包为 Blender 可导入的 ZIP（写入项目 archives/ 目录）。
   * @returns ArchiveShotResponse Successful Response
   * @throws ApiError
   */
  public archiveShotApiAicssV2ProjectsProjectIdShotsShotIdArchivePost({
    projectId,
    shotId,
    sceneId,
  }: {
    projectId: string,
    shotId: string,
    sceneId?: (string | null),
  }): CancelablePromise<ArchiveShotResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/v2/projects/{project_id}/shots/{shot_id}/archive',
      path: {
        'project_id': projectId,
        'shot_id': shotId,
      },
      query: {
        'scene_id': sceneId,
      },
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Download Shot Archive
   * 下载最近一次生成的 shot archive ZIP（若不存在则现场打包）。
   * @returns any Successful Response
   * @throws ApiError
   */
  public downloadShotArchiveApiAicssV2ProjectsProjectIdShotsShotIdArchiveDownloadGet({
    projectId,
    shotId,
  }: {
    projectId: string,
    shotId: string,
  }): CancelablePromise<any> {
    return this.httpRequest.request({
      method: 'GET',
      url: '/api/aicss/v2/projects/{project_id}/shots/{shot_id}/archive/download',
      path: {
        'project_id': projectId,
        'shot_id': shotId,
      },
      errors: {
        422: `Validation Error`,
      },
    });
  }
}
