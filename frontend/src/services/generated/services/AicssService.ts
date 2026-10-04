/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AnalyzeRequest } from '../models/AnalyzeRequest';
import type { AnalyzeResponse } from '../models/AnalyzeResponse';
import type { BillboardRequest } from '../models/BillboardRequest';
import type { BillboardResponse } from '../models/BillboardResponse';
import type { DepthRequest } from '../models/DepthRequest';
import type { DepthResponse } from '../models/DepthResponse';
import type { InpaintRequest } from '../models/InpaintRequest';
import type { InpaintResponse } from '../models/InpaintResponse';
import type { LayersRequest } from '../models/LayersRequest';
import type { LayersResponse } from '../models/LayersResponse';
import type { MultifaceRequest } from '../models/MultifaceRequest';
import type { MultifaceResponse } from '../models/MultifaceResponse';
import type { OcclusionHolesRequest } from '../models/OcclusionHolesRequest';
import type { OcclusionHolesResponse } from '../models/OcclusionHolesResponse';
import type { PaperDioramaRequest } from '../models/PaperDioramaRequest';
import type { PaperDioramaResponse } from '../models/PaperDioramaResponse';
import type { PaperLayerRequest } from '../models/PaperLayerRequest';
import type { PaperLayerResponse } from '../models/PaperLayerResponse';
import type { PaperStyleRequest } from '../models/PaperStyleRequest';
import type { PaperStyleResponse } from '../models/PaperStyleResponse';
import type { SceneGraphRequest } from '../models/SceneGraphRequest';
import type { SceneGraphResponse } from '../models/SceneGraphResponse';
import type { SegmentRequest } from '../models/SegmentRequest';
import type { SegmentResponse } from '../models/SegmentResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import type { BaseHttpRequest } from '../core/BaseHttpRequest';
export class AicssService {
  constructor(public readonly httpRequest: BaseHttpRequest) {}
  /**
   * Analyze
   * Full AICSS analysis pipeline.
   *
   * 1. Load image
   * 2. Run DepthAnything V2 → depth map
   * 3. Run Grounding DINO + SAM2 → object masks
   * 4. Assign objects to spatial layers
   * 5. Build scene graph
   * 6. Return all results
   * @returns AnalyzeResponse Successful Response
   * @throws ApiError
   */
  public analyzeApiAicssAnalyzePost({
    requestBody,
  }: {
    requestBody: AnalyzeRequest,
  }): CancelablePromise<AnalyzeResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/analyze',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Generate Depth
   * Generate a depth map from an image.
   * @returns DepthResponse Successful Response
   * @throws ApiError
   */
  public generateDepthApiAicssDepthPost({
    requestBody,
  }: {
    requestBody: DepthRequest,
  }): CancelablePromise<DepthResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/depth',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Segment Objects
   * Detect and segment objects using Grounding DINO + SAM2.
   * @returns SegmentResponse Successful Response
   * @throws ApiError
   */
  public segmentObjectsApiAicssSegmentPost({
    requestBody,
  }: {
    requestBody: SegmentRequest,
  }): CancelablePromise<SegmentResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/segment',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Build Layers
   * Build spatial layers from a depth map and object list.
   * @returns LayersResponse Successful Response
   * @throws ApiError
   */
  public buildLayersApiAicssLayersPost({
    requestBody,
  }: {
    requestBody: LayersRequest,
  }): CancelablePromise<LayersResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/layers',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Build Graph
   * Build spatial relationship graph from objects.
   * @returns SceneGraphResponse Successful Response
   * @throws ApiError
   */
  public buildGraphApiAicssSceneGraphPost({
    requestBody,
  }: {
    requestBody: SceneGraphRequest,
  }): CancelablePromise<SceneGraphResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/scene-graph',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Generate Billboard
   * Generate an RGBA billboard texture for a cropped object.
   * Uses the mask to cut out the subject and apply transparency.
   * @returns BillboardResponse Successful Response
   * @throws ApiError
   */
  public generateBillboardApiAicssBillboardPost({
    requestBody,
  }: {
    requestBody: BillboardRequest,
  }): CancelablePromise<BillboardResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/billboard',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Generate Multiface
   * Generate 6-face pseudo-3D textures for an object.
   * - front: original image (cropped)
   * - back: horizontal flip
   * - left: -90 deg rotation
   * - right: +90 deg rotation
   * - top: small crop from top edge
   * - bottom: small crop from bottom edge
   * @returns MultifaceResponse Successful Response
   * @throws ApiError
   */
  public generateMultifaceApiAicssMultifacePost({
    requestBody,
  }: {
    requestBody: MultifaceRequest,
  }): CancelablePromise<MultifaceResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/multiface',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Inpaint Image
   * Inpaint masked areas using local LaMa model (replaces DashScope wanx2.1-imageedit).
   *
   * maskDataUrl should be an RGBA PNG where:
   * - White (alpha=255): areas to inpaint
   * - Black (alpha=0):   areas to keep unchanged
   * @returns InpaintResponse Successful Response
   * @throws ApiError
   */
  public inpaintImageApiAicssInpaintPost({
    requestBody,
  }: {
    requestBody: InpaintRequest,
  }): CancelablePromise<InpaintResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/inpaint',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Occlusion Holes
   * 从 Analyze 物体列表自动生成遮挡空洞 mask（不跑 LaMa）。
   *
   * peel: 空洞 = 目标物体完整 SAM mask（适合逐层剥离）。
   * occluded_interior: 空洞 = 目标 ∩ 更近遮挡物；无重叠时回退 peel。
   * @returns OcclusionHolesResponse Successful Response
   * @throws ApiError
   */
  public occlusionHolesApiAicssOcclusionHolesPost({
    requestBody,
  }: {
    requestBody: OcclusionHolesRequest,
  }): CancelablePromise<OcclusionHolesResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/occlusion-holes',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Paper Style Transfer
   * Convert a photograph to paper-cut / illustration style.
   * Applies bilateral filtering + colour quantisation + edge detection.
   * @returns PaperStyleResponse Successful Response
   * @throws ApiError
   */
  public paperStyleTransferApiAicssPaperStylePost({
    requestBody,
  }: {
    requestBody: PaperStyleRequest,
  }): CancelablePromise<PaperStyleResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/paper-style',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Paper Diorama Generate
   * Generate a complete paper-diorama texture set for a single object:
   * - paper_style_url    : illustrated paper style image
   * - thickness_url      : thickness/height field (false-colour PNG)
   * - normal_map_url     : surface normal map
   * - outlined_url       : paper-style image with cut edges + shadow
   * - thickness_gray_url : thickness as grayscale PNG
   * @returns PaperDioramaResponse Successful Response
   * @throws ApiError
   */
  public paperDioramaGenerateApiAicssPaperDioramaPost({
    requestBody,
  }: {
    requestBody: PaperDioramaRequest,
  }): CancelablePromise<PaperDioramaResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/paper-diorama',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Paper Layer Generate
   * Generate paper-diorama texture for a full depth layer image.
   * Returns the same texture fields as /paper-diorama.
   * @returns PaperLayerResponse Successful Response
   * @throws ApiError
   */
  public paperLayerGenerateApiAicssPaperLayerPost({
    requestBody,
  }: {
    requestBody: PaperLayerRequest,
  }): CancelablePromise<PaperLayerResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/paper-layer',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
}
