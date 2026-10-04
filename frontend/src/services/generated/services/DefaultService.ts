/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CancelablePromise } from '../core/CancelablePromise';
import type { BaseHttpRequest } from '../core/BaseHttpRequest';
export class DefaultService {
  constructor(public readonly httpRequest: BaseHttpRequest) {}
  /**
   * Health
   * @returns any Successful Response
   * @throws ApiError
   */
  public healthHealthGet(): CancelablePromise<any> {
    return this.httpRequest.request({
      method: 'GET',
      url: '/health',
    });
  }
  /**
   * Health Models
   * Detailed per-model availability check.
   *
   * Returns whether each model file/weight is present on disk so the frontend
   * can warn the user (and the dev can diagnose 5xx errors) before triggering
   * expensive inference. Lazy-loaded models also report whether they are
   * currently resident in GPU memory.
   *
   * The response shape is stable — frontend code can rely on these keys:
   * - `models`     : per-model {available, path, ...} details
   * - `missing`    : list of {model, path, download_hint} for unavailable models
   * - `all_ready`  : True iff every required model is available
   * - `device`     : cuda / cpu
   * - `lazy_load`  : whether models are loaded on first use
   * @returns any Successful Response
   * @throws ApiError
   */
  public healthModelsHealthModelsGet(): CancelablePromise<any> {
    return this.httpRequest.request({
      method: 'GET',
      url: '/health/models',
    });
  }
  /**
   * Root
   * @returns any Successful Response
   * @throws ApiError
   */
  public rootGet(): CancelablePromise<any> {
    return this.httpRequest.request({
      method: 'GET',
      url: '/',
    });
  }
}
