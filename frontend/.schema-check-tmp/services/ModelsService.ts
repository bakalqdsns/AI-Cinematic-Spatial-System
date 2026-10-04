/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DownloadActionResponse } from '../models/DownloadActionResponse';
import type { ModelStatusResponse } from '../models/ModelStatusResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import type { BaseHttpRequest } from '../core/BaseHttpRequest';
export class ModelsService {
  constructor(public readonly httpRequest: BaseHttpRequest) {}
  /**
   * Models Status
   * Return the download status of all models that may need local downloading.
   *
   * In cloud mode, only Depth and SAM2 require local downloads.
   * In local mode, all models (Depth, SAM2, Grounding DINO, Qwen3-VL, LaMa,
   * Z-Image) may need to be downloaded.
   * @returns ModelStatusResponse Successful Response
   * @throws ApiError
   */
  public modelsStatusApiAicssModelsStatusGet(): CancelablePromise<ModelStatusResponse> {
    return this.httpRequest.request({
      method: 'GET',
      url: '/api/aicss/models/status',
    });
  }
  /**
   * Download Model
   * Trigger download of a specific model with built-in retry.
   *
   * Supported model_name values:
   * - depth
   * - grounding_dino
   * - sam2
   * - qwen3vl
   * - lama
   * - image
   *
   * Returns HTTP 202 Accepted immediately; the actual download happens in a
   * background thread. The endpoint-level retry wrapper re-invokes the loader
   * up to `AICSS_DOWNLOAD_RETRIES` times (default 3) with exponential back-off
   * if a transient failure occurs.
   *
   * To check download progress, poll GET /api/aicss/models/status.
   * @returns DownloadActionResponse Successful Response
   * @throws ApiError
   */
  public downloadModelApiAicssModelsDownloadModelNamePost({
    modelName,
  }: {
    modelName: string,
  }): CancelablePromise<DownloadActionResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/models/download/{model_name}',
      path: {
        'model_name': modelName,
      },
      errors: {
        422: `Validation Error`,
      },
    });
  }
}
