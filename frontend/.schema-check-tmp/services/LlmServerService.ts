/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { LlmActionResponse } from '../models/LlmActionResponse';
import type { LlmStatusResponse } from '../models/LlmStatusResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import type { BaseHttpRequest } from '../core/BaseHttpRequest';
export class LlmServerService {
  constructor(public readonly httpRequest: BaseHttpRequest) {}
  /**
   * Llm Status
   * Get current llama-server status.
   * @returns LlmStatusResponse Successful Response
   * @throws ApiError
   */
  public llmStatusApiAicssLlmStatusGet(): CancelablePromise<LlmStatusResponse> {
    return this.httpRequest.request({
      method: 'GET',
      url: '/api/aicss/llm/status',
    });
  }
  /**
   * Llm Start
   * Start llama-server.
   * Uses batch script to run in system environment (bypasses venv CUDA issues).
   * @returns LlmActionResponse Successful Response
   * @throws ApiError
   */
  public llmStartApiAicssLlmStartPost(): CancelablePromise<LlmActionResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/llm/start',
    });
  }
  /**
   * Llm Stop
   * Stop llama-server gracefully.
   * @returns LlmActionResponse Successful Response
   * @throws ApiError
   */
  public llmStopApiAicssLlmStopPost(): CancelablePromise<LlmActionResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/llm/stop',
    });
  }
  /**
   * Llm Reload
   * Restart llama-server (stop then start).
   * @returns LlmActionResponse Successful Response
   * @throws ApiError
   */
  public llmReloadApiAicssLlmReloadPost(): CancelablePromise<LlmActionResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/llm/reload',
    });
  }
  /**
   * Llm Keep Alive
   * Reset the auto-unload idle timer.
   * Call this periodically from the frontend to prevent server from shutting down.
   * @returns any Successful Response
   * @throws ApiError
   */
  public llmKeepAliveApiAicssLlmKeepAlivePost(): CancelablePromise<any> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/llm/keep-alive',
    });
  }
}
