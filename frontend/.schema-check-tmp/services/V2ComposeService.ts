/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ComposeRequest } from '../models/ComposeRequest';
import type { ComposeResponse } from '../models/ComposeResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import type { BaseHttpRequest } from '../core/BaseHttpRequest';
export class V2ComposeService {
  constructor(public readonly httpRequest: BaseHttpRequest) {}
  /**
   * Api Compose
   * Compose a list of shot MP4 clips into a single 1080p H.264 MP4.
   *
   * Pipeline (all async, ffmpeg via ``asyncio.create_subprocess_exec``):
   * 1. Normalise every clip to 1080p yuv420p H.264.
   * 2. Pairwise apply transitions (cut / dissolve / fade / wipe).
   * 3. (Optional) mix audio tracks (BGM / SFX / voiceover) with loudnorm.
   * 4. (Optional) apply color grade (.cube LUT or eq brightness/contrast/saturation).
   *
   * Error mapping:
   * - ``FFMPEG_MISSING`` → 503
   * - Any other ``RuntimeError`` from the composer → 500
   * @returns ComposeResponse Successful Response
   * @throws ApiError
   */
  public apiComposeApiAicssV2ProjectsProjectIdComposePost({
    projectId,
    requestBody,
  }: {
    projectId: string,
    requestBody: ComposeRequest,
  }): CancelablePromise<ComposeResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/v2/projects/{project_id}/compose',
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
}
