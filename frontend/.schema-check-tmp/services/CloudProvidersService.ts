/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PingRequest } from '../models/PingRequest';
import type { CancelablePromise } from '../core/CancelablePromise';
import type { BaseHttpRequest } from '../core/BaseHttpRequest';
export class CloudProvidersService {
  constructor(public readonly httpRequest: BaseHttpRequest) {}
  /**
   * Get Provider Types
   * Return metadata for all registered provider types (DashScope, OpenAI-compat, ...).
   * @returns any Successful Response
   * @throws ApiError
   */
  public getProviderTypesApiAicssProvidersTypesGet(): CancelablePromise<Array<Record<string, any>>> {
    return this.httpRequest.request({
      method: 'GET',
      url: '/api/aicss/providers/types',
    });
  }
  /**
   * Ping Provider
   * Health-check the active cloud provider for the given component.
   * @returns any Successful Response
   * @throws ApiError
   */
  public pingProviderApiAicssProvidersPingPost({
    requestBody,
  }: {
    requestBody: PingRequest,
  }): CancelablePromise<Record<string, any>> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/providers/ping',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
}
