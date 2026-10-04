/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ActionSequencesRequest } from '../models/ActionSequencesRequest';
import type { ActionSequencesResponse } from '../models/ActionSequencesResponse';
import type { BatchStatusResponse } from '../models/BatchStatusResponse';
import type { CameraPathRequest } from '../models/CameraPathRequest';
import type { CameraPathResponse } from '../models/CameraPathResponse';
import type { ExtractCharactersRequest } from '../models/ExtractCharactersRequest';
import type { ExtractCharactersResponse } from '../models/ExtractCharactersResponse';
import type { ExtractFramesRequest } from '../models/ExtractFramesRequest';
import type { ExtractFramesResponse } from '../models/ExtractFramesResponse';
import type { GenerateMotionRequest } from '../models/GenerateMotionRequest';
import type { GenerateSceneAssetRequest } from '../models/GenerateSceneAssetRequest';
import type { GenerateShotsRequest } from '../models/GenerateShotsRequest';
import type { GenerateShotsResponse } from '../models/GenerateShotsResponse';
import type { GenerateThreeViewRequest } from '../models/GenerateThreeViewRequest';
import type { GenerateVariationRequest } from '../models/GenerateVariationRequest';
import type { MotionResponse } from '../models/MotionResponse';
import type { ParseScriptRequest } from '../models/ParseScriptRequest';
import type { ParseScriptResponse } from '../models/ParseScriptResponse';
import type { SceneAssetResponse } from '../models/SceneAssetResponse';
import type { SceneBatchStatusResponse } from '../models/SceneBatchStatusResponse';
import type { ScenePromptsRequest } from '../models/ScenePromptsRequest';
import type { ScenePromptsResponse } from '../models/ScenePromptsResponse';
import type { SegmentFramesRequest } from '../models/SegmentFramesRequest';
import type { SegmentFramesResponse } from '../models/SegmentFramesResponse';
import type { ThreeViewResponse } from '../models/ThreeViewResponse';
import type { VariationResponse } from '../models/VariationResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import type { BaseHttpRequest } from '../core/BaseHttpRequest';
export class ScriptMotionService {
  constructor(public readonly httpRequest: BaseHttpRequest) {}
  /**
   * Api Normalize And Parse
   * Script processing with optional normalize + parallel parse.
   *
   * The /parse endpoint used to be a strict 2-pass flow (always normalize
   * first, then parse). For scripts that already follow standard screenplay
   * conventions ("内景 X - 时间", "EXT. X - TIME" headings), the normalize
   * step is now skipped — the regex-based skip check looks at the first 200
   * non-empty lines for at least one recognised scene heading.
   *
   * Pass 2 (parse) runs FOUR LLM calls in parallel:
   * - header   (title / genre / logline)
   * - scenes   (scene list)
   * - characters (via existing Pass 1.5)
   * - paragraphs (depends on scene_count, runs after scenes)
   * Any sub-task failure only degrades that field; the rest stay populated.
   * @returns ParseScriptResponse Successful Response
   * @throws ApiError
   */
  public apiNormalizeAndParseApiAicssV2ScriptsParsePost({
    requestBody,
  }: {
    requestBody: ParseScriptRequest,
  }): CancelablePromise<ParseScriptResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/v2/scripts/parse',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Api Extract Characters
   * Character-first extraction: identify all real human characters in the script.
   *
   * This is Pass 1.5 of the character-first pipeline. Runs an LLM call
   * focused exclusively on character identification (no scenes, no paragraphs),
   * then falls back to heuristic bracket/dialogue detection when the LLM is
   * unavailable.
   *
   * The returned characters can be passed back into the shot generation
   * pipeline as a curated, character-grounded input — preventing scene/shot
   * generators from inheriting pseudo-character noise ("特写", "异常出现", etc.).
   * @returns ExtractCharactersResponse Successful Response
   * @throws ApiError
   */
  public apiExtractCharactersApiAicssV2ScriptsCharactersExtractPost({
    requestBody,
  }: {
    requestBody: ExtractCharactersRequest,
  }): CancelablePromise<ExtractCharactersResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/v2/scripts/characters/extract',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Api Generate Shots
   * Generate shot storyboard from parsed script data.
   *
   * Produces Shot objects with camera movement, shot size, visual prompts and
   * per-character action sequences. Saves to the project store when a
   * project_id is provided.
   * @returns GenerateShotsResponse Successful Response
   * @throws ApiError
   */
  public apiGenerateShotsApiAicssV2ScriptsShotsPost({
    requestBody,
  }: {
    requestBody: GenerateShotsRequest,
  }): CancelablePromise<GenerateShotsResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/v2/scripts/shots',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Api Get Scene Prompts
   * Get structured scene and transition prompts from a shot list.
   *
   * Useful when the frontend already has a shot list (e.g. from a previous
   * /shots call) but needs only the structured prompts to drive image
   * generation.
   * @returns ScenePromptsResponse Successful Response
   * @throws ApiError
   */
  public apiGetScenePromptsApiAicssV2ScriptsScenePromptsPost({
    requestBody,
  }: {
    requestBody: ScenePromptsRequest,
  }): CancelablePromise<ScenePromptsResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/v2/scripts/scene-prompts',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Api Get Action Sequences
   * Get character action sequences across all shots.
   *
   * Builds CharacterActionSequence objects describing each character's
   * shot-to-shot motion and an intensity curve.
   * @returns ActionSequencesResponse Successful Response
   * @throws ApiError
   */
  public apiGetActionSequencesApiAicssV2ScriptsActionSequencesPost({
    requestBody,
  }: {
    requestBody: ActionSequencesRequest,
  }): CancelablePromise<ActionSequencesResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/v2/scripts/action-sequences',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Api Generate Visual Prompt
   * Generate visual prompt for a character without producing images.
   *
   * Useful for previewing prompts before committing to expensive image
   * generation. Parameters are accepted as query string so the caller can
   * trigger this cheaply from auto-fill inputs (see
   * ``scriptService.generateVisualPrompt``).
   * @returns any Successful Response
   * @throws ApiError
   */
  public apiGenerateVisualPromptApiAicssV2ScriptsVisualPromptPost({
    characterName,
    gender = '',
    age = '',
    personality = '',
    genre = 'cinematic',
    language = 'chinese',
  }: {
    /**
     * Character name
     */
    characterName: string,
    /**
     * e.g. female / male
     */
    gender?: string,
    /**
     * e.g. 17 / middle-aged
     */
    age?: string,
    /**
     * Short trait description
     */
    personality?: string,
    /**
     * Visual style hint
     */
    genre?: string,
    /**
     * chinese / english / japanese
     */
    language?: string,
  }): CancelablePromise<any> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/v2/scripts/visual-prompt',
      query: {
        'character_name': characterName,
        'gender': gender,
        'age': age,
        'personality': personality,
        'genre': genre,
        'language': language,
      },
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Api Generate Three View
   * Generate three-view character reference images.
   *
   * Produces front / side / back images for character consistency across shots,
   * plus a base reference image. Saves a CharacterAsset JSON to the project
   * store when a project_id is provided.
   * @returns ThreeViewResponse Successful Response
   * @throws ApiError
   */
  public apiGenerateThreeViewApiAicssV2ScriptsCharactersGenerateThreeViewPost({
    requestBody,
  }: {
    requestBody: GenerateThreeViewRequest,
  }): CancelablePromise<ThreeViewResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/v2/scripts/characters/generate-three-view',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Api Generate Variation
   * Generate character wardrobe / outfit variation.
   *
   * Persists the variation to the project's characters/<id>.json store when a
   * project_id is provided.
   * @returns VariationResponse Successful Response
   * @throws ApiError
   */
  public apiGenerateVariationApiAicssV2ScriptsCharactersGenerateVariationPost({
    requestBody,
  }: {
    requestBody: GenerateVariationRequest,
  }): CancelablePromise<VariationResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/v2/scripts/characters/generate-variation',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Api Batch Status
   * Poll this from the frontend after /parse returns. Tells the UI which
   * characters have their three-view assets ready.
   * @returns BatchStatusResponse Successful Response
   * @throws ApiError
   */
  public apiBatchStatusApiAicssV2ScriptsCharactersBatchStatusGet({
    projectId,
  }: {
    projectId: string,
  }): CancelablePromise<BatchStatusResponse> {
    return this.httpRequest.request({
      method: 'GET',
      url: '/api/aicss/v2/scripts/characters/batch-status',
      query: {
        'project_id': projectId,
      },
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Api Batch Clear
   * Drop the in-memory progress table for a project (e.g. on project delete).
   * @returns any Successful Response
   * @throws ApiError
   */
  public apiBatchClearApiAicssV2ScriptsCharactersBatchClearPost({
    projectId,
  }: {
    projectId: string,
  }): CancelablePromise<Record<string, any>> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/v2/scripts/characters/batch-clear',
      query: {
        'project_id': projectId,
      },
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Api Generate Scene Asset
   * Manual single-scene asset generation (3 keyframes).
   * @returns SceneAssetResponse Successful Response
   * @throws ApiError
   */
  public apiGenerateSceneAssetApiAicssV2ScriptsScenesGenerateAssetPost({
    requestBody,
  }: {
    requestBody: GenerateSceneAssetRequest,
  }): CancelablePromise<SceneAssetResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/v2/scripts/scenes/generate-asset',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Api Scene Batch Status
   * @returns SceneBatchStatusResponse Successful Response
   * @throws ApiError
   */
  public apiSceneBatchStatusApiAicssV2ScriptsScenesBatchStatusGet({
    projectId,
  }: {
    projectId: string,
  }): CancelablePromise<SceneBatchStatusResponse> {
    return this.httpRequest.request({
      method: 'GET',
      url: '/api/aicss/v2/scripts/scenes/batch-status',
      query: {
        'project_id': projectId,
      },
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Api Scene Batch Clear
   * @returns any Successful Response
   * @throws ApiError
   */
  public apiSceneBatchClearApiAicssV2ScriptsScenesBatchClearPost({
    projectId,
  }: {
    projectId: string,
  }): CancelablePromise<Record<string, any>> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/v2/scripts/scenes/batch-clear',
      query: {
        'project_id': projectId,
      },
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Api Generate Motion
   * Full motion sequence pipeline.
   *
   * Steps:
   * 1. Generate action video via DashScope (or other provider)
   * 2. Extract PNG frames via ffmpeg
   * 3. Segment person from frames via SAM2 (if available)
   *
   * Persists the resulting MotionSequence JSON to <project>/motions/<shot_id>.json
   * when a project_id is provided.
   * @returns MotionResponse Successful Response
   * @throws ApiError
   */
  public apiGenerateMotionApiAicssV2ScriptsMotionGeneratePost({
    requestBody,
  }: {
    requestBody: GenerateMotionRequest,
  }): CancelablePromise<MotionResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/v2/scripts/motion/generate',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Api Extract Frames
   * Extract PNG frames from a video file using ffmpeg.
   * @returns ExtractFramesResponse Successful Response
   * @throws ApiError
   */
  public apiExtractFramesApiAicssV2ScriptsMotionExtractFramesPost({
    requestBody,
  }: {
    requestBody: ExtractFramesRequest,
  }): CancelablePromise<ExtractFramesResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/v2/scripts/motion/extract-frames',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Api Segment Frames
   * Segment the person from a list of frame paths using SAM2.
   * @returns SegmentFramesResponse Successful Response
   * @throws ApiError
   */
  public apiSegmentFramesApiAicssV2ScriptsMotionSegmentPost({
    requestBody,
  }: {
    requestBody: SegmentFramesRequest,
  }): CancelablePromise<SegmentFramesResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/v2/scripts/motion/segment',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Api Camera Path
   * Return the camera keyframes that Three.js should play for a given shot.
   *
   * The frontend's `utils/cameraAnimation.ts` is the canonical source of truth —
   * this endpoint exists so the Blender renderer and external test harnesses
   * can consume the same abstract path without going through the browser.
   * @returns CameraPathResponse Successful Response
   * @throws ApiError
   */
  public apiCameraPathApiAicssV2ScriptsCameraPathPost({
    requestBody,
  }: {
    requestBody: CameraPathRequest,
  }): CancelablePromise<CameraPathResponse> {
    return this.httpRequest.request({
      method: 'POST',
      url: '/api/aicss/v2/scripts/camera-path',
      body: requestBody,
      mediaType: 'application/json',
      errors: {
        422: `Validation Error`,
      },
    });
  }
}
