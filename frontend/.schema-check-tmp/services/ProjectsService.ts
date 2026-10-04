/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_create_project_api_aicss_projects_post } from '../models/Body_create_project_api_aicss_projects_post';
import type { CheckpointRequest } from '../models/CheckpointRequest';
import type { ProjectInfoResponse } from '../models/ProjectInfoResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import type { BaseHttpRequest } from '../core/BaseHttpRequest';
export class ProjectsService {
  constructor(public readonly httpRequest: BaseHttpRequest) {}
  /**
   * List Projects
   * 列出所有项目（仅 manifest summary），按 updated_at 降序。
   * @returns any Successful Response
   * @throws ApiError
   */
  public listProjectsApiAicssProjectsGet(): CancelablePromise<any> {
    return this.httpRequest.request({
      method: 'GET',
      url: '/api/aicss/projects',
    });
  }
  /**
   * Create Project
   * 创建一个新项目目录，并把上传的原始图写入 input/original.png。
   *
   * Accepts multipart/form-data:
   * - shotId:  e.g. "shot_001"
   * - image:   the original image (PNG/JPEG)
   * - imageWidth / imageHeight: optional, will be inferred from image if not provided
   * @returns ProjectInfoResponse Successful Response
   * @throws ApiError
   */
  public createProjectApiAicssProjectsPost({
    formData,
  }: {
    formData: Body_create_project_api_aicss_projects_post,
  }): CancelablePromise<ProjectInfoResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/projects',
      formData: formData,
      mediaType: 'multipart/form-data',
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Create Project Json
   * 接受 JSON 形式创建项目（用于前端发送 base64 data URL）。
   *
   * Body:
   * {
     * "shotId": "shot_001",
     * "imageBase64": "data:image/png;base64,...",
     * "imageWidth": 1920,
     * "imageHeight": 1080
     * }
     * @returns ProjectInfoResponse Successful Response
     * @throws ApiError
     */
    public createProjectJsonApiAicssProjectsJsonPost({
      requestBody,
    }: {
      requestBody: Record<string, any>,
    }): CancelablePromise<ProjectInfoResponse> {
      return this.httpRequest.request({
        method: 'POST',
        url: '/api/aicss/projects/json',
        body: requestBody,
        mediaType: 'application/json',
        errors: {
          422: `Validation Error`,
        },
      });
    }
    /**
     * Get Manifest
     * 读取指定项目的完整 manifest.json。
     * @returns any Successful Response
     * @throws ApiError
     */
    public getManifestApiAicssProjectsProjectIdManifestGet({
      projectId,
    }: {
      projectId: string,
    }): CancelablePromise<any> {
      return this.httpRequest.request({
        method: 'GET',
        url: '/api/aicss/projects/{project_id}/manifest',
        path: {
          'project_id': projectId,
        },
        errors: {
          422: `Validation Error`,
        },
      });
    }
    /**
     * Get Artifact
     * 拉取单个产物文件。JSON 文件自动以 application/json 返回。
     * @returns any Successful Response
     * @throws ApiError
     */
    public getArtifactApiAicssProjectsProjectIdArtifactsStepFilenameGet({
      projectId,
      step,
      filename,
    }: {
      projectId: string,
      step: string,
      filename: string,
    }): CancelablePromise<any> {
      return this.httpRequest.request({
        method: 'GET',
        url: '/api/aicss/projects/{project_id}/artifacts/{step}/{filename}',
        path: {
          'project_id': projectId,
          'step': step,
          'filename': filename,
        },
        errors: {
          422: `Validation Error`,
        },
      });
    }
    /**
     * Post Checkpoint
     * 记录一条断点 / 阶段完成事件到 manifest 的 timeline。
     * @returns any Successful Response
     * @throws ApiError
     */
    public postCheckpointApiAicssProjectsProjectIdCheckpointPost({
      projectId,
      requestBody,
    }: {
      projectId: string,
      requestBody: CheckpointRequest,
    }): CancelablePromise<any> {
      return this.httpRequest.request({
        method: 'POST',
        url: '/api/aicss/projects/{project_id}/checkpoint',
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
     * Delete Project
     * 删除整个项目目录（不可恢复）。
     * @returns any Successful Response
     * @throws ApiError
     */
    public deleteProjectApiAicssProjectsProjectIdDelete({
      projectId,
    }: {
      projectId: string,
    }): CancelablePromise<any> {
      return this.httpRequest.request({
        method: 'DELETE',
        url: '/api/aicss/projects/{project_id}',
        path: {
          'project_id': projectId,
        },
        errors: {
          422: `Validation Error`,
        },
      });
    }
  }
