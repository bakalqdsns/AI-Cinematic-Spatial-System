/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AnalyzeFromScriptRequest } from '../models/AnalyzeFromScriptRequest';
import type { AnalyzeSequenceRequest } from '../models/AnalyzeSequenceRequest';
import type { CrossFrameObjectDetail } from '../models/CrossFrameObjectDetail';
import type { SceneLinksResponse } from '../models/SceneLinksResponse';
import type { SequenceResult } from '../models/SequenceResult';
import type { CancelablePromise } from '../core/CancelablePromise';
import type { BaseHttpRequest } from '../core/BaseHttpRequest';
export class V2SequenceService {
  constructor(public readonly httpRequest: BaseHttpRequest) {}
  /**
   * Analyze Sequence
   * Analyze an image sequence.
   *
   * Processing pipeline:
   * 1. Validate request (frameIds and imageUrls must have the same length)
   * 2. For each frame, call _analyze_single_frame
   * 3. Use TemporalTracker for cross-frame object matching
   * 4. Build scene links
   * 5. Persist to project_store if projectId provided
   * 6. Return SequenceResult
   * @returns SequenceResult Successful Response
   * @throws ApiError
   */
  public analyzeSequenceApiAicssV2SequencesPost({
    requestBody,
  }: {
    requestBody: AnalyzeSequenceRequest,
  }): CancelablePromise<SequenceResult> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/v2/sequences',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Analyze From Script
   * Analyze frames defined by script scenes.
   * Converts ScriptScene items to the format expected by analyze_sequence.
   * @returns SequenceResult Successful Response
   * @throws ApiError
   */
  public analyzeFromScriptApiAicssV2SequencesFromScriptPost({
    requestBody,
  }: {
    requestBody: AnalyzeFromScriptRequest,
  }): CancelablePromise<SequenceResult> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/v2/sequences/from-script',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Get Sequence
   * Get sequence details by ID.
   * @returns SequenceResult Successful Response
   * @throws ApiError
   */
  public getSequenceApiAicssV2SequencesSequenceIdGet({
    sequenceId,
  }: {
    sequenceId: string,
  }): CancelablePromise<SequenceResult> {
    return this.httpRequest.request({
      method: 'GET',
      url: '/api/aicss/v2/sequences/{sequence_id}',
      path: {
        'sequence_id': sequenceId,
      },
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Get Scene Links
   * Get the scene association graph for a sequence.
   * Returns FrameLink list with shared objects and statistics.
   * @returns SceneLinksResponse Successful Response
   * @throws ApiError
   */
  public getSceneLinksApiAicssV2SequencesSequenceIdSceneLinksGet({
    sequenceId,
  }: {
    sequenceId: string,
  }): CancelablePromise<SceneLinksResponse> {
    return this.httpRequest.request({
      method: 'GET',
      url: '/api/aicss/v2/sequences/{sequence_id}/scene-links',
      path: {
        'sequence_id': sequenceId,
      },
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Get Cross Frame Object
   * Get detailed information about a cross-frame object.
   * Includes trajectory and layer history.
   * @returns CrossFrameObjectDetail Successful Response
   * @throws ApiError
   */
  public getCrossFrameObjectApiAicssV2SequencesSequenceIdObjectsGlobalIdGet({
    sequenceId,
    globalId,
  }: {
    sequenceId: string,
    globalId: string,
  }): CancelablePromise<CrossFrameObjectDetail> {
    return this.httpRequest.request({
      method: 'GET',
      url: '/api/aicss/v2/sequences/{sequence_id}/objects/{global_id}',
      path: {
        'sequence_id': sequenceId,
        'global_id': globalId,
      },
      errors: {
        422: `Validation Error`,
      },
    });
  }
}
