/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { LayerExportRequest } from '../models/LayerExportRequest';
import type { LayerExportResponse } from '../models/LayerExportResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import type { BaseHttpRequest } from '../core/BaseHttpRequest';
export class LayersService {
  constructor(public readonly httpRequest: BaseHttpRequest) {}
  /**
   * Export depth-layer RGBA PNGs (+ per-object assets) from a scene image
   * Takes the original scene image (and optionally a depth map) and returns one RGBA PNG per depth layer (sky / background / midground / foreground / ground). Each PNG keeps the original RGB on its layer's pixels and is fully transparent elsewhere. With autoAnchor=True the endpoint also runs GroundingDINO + SAM2 to slice every detected object into its own RGBA cutout, and fits a RANSAC plane to the ground region. The response also includes the Z-axis offset table the Blender plugin reads to position the layers.
   * @returns LayerExportResponse Successful Response
   * @throws ApiError
   */
  public layersExportApiAicssLayersExportPost({
    requestBody,
  }: {
    requestBody: LayerExportRequest,
  }): CancelablePromise<LayerExportResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/layers/export',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
}
