/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SettingsUpdate } from '../models/SettingsUpdate';
import type { CancelablePromise } from '../core/CancelablePromise';
import type { BaseHttpRequest } from '../core/BaseHttpRequest';
export class SettingsService {
  constructor(public readonly httpRequest: BaseHttpRequest) {}
  /**
   * Get Settings
   * Return the current runtime settings (sensitive fields masked).
   * @returns any Successful Response
   * @throws ApiError
   */
  public getSettingsApiAicssSettingsGet(): CancelablePromise<Record<string, any>> {
    return this.httpRequest.request({
      method: 'GET',
      url: '/api/aicss/settings/',
    });
  }
  /**
   * Post Settings
   * Apply a partial update and return the new settings snapshot.
   * @returns any Successful Response
   * @throws ApiError
   */
  public postSettingsApiAicssSettingsPost({
    requestBody,
  }: {
    requestBody: SettingsUpdate,
  }): CancelablePromise<Record<string, any>> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/settings/',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Get Settings
   * Return the current runtime settings (sensitive fields masked).
   * @returns any Successful Response
   * @throws ApiError
   */
  public getSettingsApiAicssSettingsGet1(): CancelablePromise<Record<string, any>> {
    return this.httpRequest.request({
      method: 'GET',
      url: '/api/aicss/settings',
    });
  }
  /**
   * Post Settings
   * Apply a partial update and return the new settings snapshot.
   * @returns any Successful Response
   * @throws ApiError
   */
  public postSettingsApiAicssSettingsPost1({
    requestBody,
  }: {
    requestBody: SettingsUpdate,
  }): CancelablePromise<Record<string, any>> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/settings',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Get Settings Store
   * Return the location of the on-disk settings store + override count.
   *
   * Used by the frontend to show "your preferences are persisted at …" and
   * to provide a "reset to defaults" button.
   * @returns any Successful Response
   * @throws ApiError
   */
  public getSettingsStoreApiAicssSettingsStoreGet(): CancelablePromise<Record<string, any>> {
    return this.httpRequest.request({
      method: 'GET',
      url: '/api/aicss/settings/store',
    });
  }
  /**
   * Reset Settings Store
   * Delete the persisted overrides file. Runtime settings are not changed
   * (use a settings update with explicit values to revert them).
   * @returns any Successful Response
   * @throws ApiError
   */
  public resetSettingsStoreApiAicssSettingsStoreDelete(): CancelablePromise<Record<string, any>> {
    return this.httpRequest.request({
      method: 'DELETE',
      url: '/api/aicss/settings/store',
    });
  }
}
