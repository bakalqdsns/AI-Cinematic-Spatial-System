// ─────────────────────────────────────────────────────────────────────────────
// AICSS Script Service — v2 API client for the script splitting pipeline.
//
// Thin wrapper around the generated OpenAPI client (`generated/scriptMotion`,
// `generated/layers`, `generated/v2Shots`). The v2 script endpoints speak
// snake_case on the wire (e.g. `raw_text`, `script_data`, `scene_transitions`),
// so the wrappers below convert the existing camelCase frontend types to the
// snake_case request bodies and back to the camelCase response types that
// `useScriptStore` consumes — keeping every exported signature identical so
// callers need no changes.
//
// Two functions stay fully handwritten:
//   - `archiveShot` — the OpenAPI snapshot's `archive_shot` operation doesn't
//     expose the `lighting_preset` query param, but T13 added it as a
//     forward-compatible query string that `ScriptEditor.tsx` passes through.
//     The generated client can't send undeclared query params, so we keep a
//     small axios call that appends `lighting_preset` when set.
//   - `downloadShotArchive` — downloads a binary ZIP blob; the generated
//     client returns parsed JSON, so it can't help here.
// ─────────────────────────────────────────────────────────────────────────────
import axios from 'axios';
import type {
  ScriptData, Shot, SceneTransition,
  CharacterAsset, Character, MotionResponse,
  ParseScriptRequest, ParseScriptResponse,
  ExtractCharactersRequest, ExtractCharactersResponse,
  GenerateShotsRequest, GenerateShotsResponse,
  ThreeViewRequest, ThreeViewResponse,
  GenerateMotionRequest, ScenePrompt,
  ScriptLanguage, ParagraphType, SceneAsset,
} from '../types/script';
import { generatedClient, DEFAULT_BACKEND } from './generatedClient';

// ─── Script Parsing ───────────────────────────────────────────────────────────

export async function parseScript(request: ParseScriptRequest): Promise<ParseScriptResponse> {
  console.log('[scriptService] parseScript called with:', { rawTextLength: request.rawText.length, language: request.language });

  const charPromise = extractCharacters({
    rawText: request.rawText,
    language: request.language,
    projectId: request.projectId,
  }).catch((err) => {
    console.warn('[scriptService] pre-extract characters failed (non-fatal):', err);
    return { characters: [] as Character[], projectId: request.projectId };
  });

  const data = await generatedClient.scriptMotion.apiNormalizeAndParseApiAicssV2ScriptsParsePost({
    requestBody: {
      raw_text: request.rawText,
      language: request.language,
      project_id: request.projectId,
      dashscope_api_key: request.dashscopeApiKey || undefined,
    } as any,
  }) as {
    normalized_script: string;
    script_data: Record<string, unknown>;
    project_id?: string;
  };
  console.log('[scriptService] parseScript response:', data);

  const response: ParseScriptResponse = {
    normalizedScript: data.normalized_script || '',
    scriptData: _deserializeScriptData(data.script_data || {}),
    projectId: data.project_id,
  };

  void charPromise;
  return response;
}

export async function extractCharacters(request: ExtractCharactersRequest): Promise<ExtractCharactersResponse> {
  console.log('[scriptService] extractCharacters called');
  const data = await generatedClient.scriptMotion.apiExtractCharactersApiAicssV2ScriptsCharactersExtractPost({
    requestBody: {
      raw_text: request.rawText,
      language: request.language,
      project_id: request.projectId,
    } as any,
  }) as {
    characters: Record<string, unknown>[];
    project_id?: string;
  };

  const characters: Character[] = (data.characters || []).map((c, i) => ({
    id: (c.id as string) || `char-${i + 1}`,
    name: (c.name as string) || '',
    gender: (c.gender as string) || '',
    age: (c.age as string) || '',
    personality: (c.personality as string) || '',
    visualPrompt: (c.visual_prompt as string) || (c.visualPrompt as string) || '',
    referenceImage: (c.reference_image as string) || (c.referenceImage as string),
    variations: (c.variations as CharacterAsset['variations']) || [],
  }));

  console.log('[scriptService] extractCharacters response: %d characters', characters.length);
  return { characters, projectId: data.project_id };
}

// ─── Internal helpers ──────────────────────────────────────────────────────────

function _deserializeScriptData(data: Record<string, unknown>): ScriptData {
  return {
    title: (data.title as string) || 'Untitled',
    genre: (data.genre as string) || '',
    logline: (data.logline as string) || '',
    language: (data.language as ScriptData['language']) || 'chinese',
    characters: ((data.characters as Record<string, unknown>[]) || []).map((c, i) => ({
      id: (c.id as string) || `char-${i + 1}`,
      name: (c.name as string) || '',
      gender: (c.gender as string) || '',
      age: (c.age as string) || '',
      personality: (c.personality as string) || '',
      visualPrompt: (c.visual_prompt as string) || (c.visualPrompt as string) || '',
      referenceImage: (c.reference_image as string) || (c.referenceImage as string),
      variations: (c.variations as CharacterAsset['variations']) || [],
    })),
    scenes: ((data.scenes as Record<string, unknown>[]) || []).map((s, i) => ({
      id: (s.id as string) || `scene-${i + 1}`,
      location: (s.location as string) || '',
      time: ((s.time as string) || 'Day') as ScriptData['scenes'][number]['time'],
      atmosphere: (s.atmosphere as string) || '',
      estimatedShots: ((s.estimated_shots as number) || (s.estimatedShots as number) || 0),
    })),
    storyParagraphs: ((data.story_paragraphs as Record<string, unknown>[]) || []).map((p, i) => ({
      id: (p.id as string) || `para-${i + 1}`,
      text: (p.text as string) || '',
      sceneRefId: (p.scene_ref_id as string) || (p.sceneRefId as string) || '',
      paragraphType: (((p.paragraph_type as string) || (p.paragraphType as string) || 'action') as ParagraphType),
      speakerId: (p.speaker_id as string) || (p.speakerId as string) || '',
      emotion: (p.emotion as string) || '',
      containsAction: (p.contains_action as boolean) !== undefined
        ? (p.contains_action as boolean)
        : (p.containsAction as boolean) !== undefined
        ? (p.containsAction as boolean)
        : true,
    })),
  };
}

// ─── Shot Generation ──────────────────────────────────────────────────────────

export async function generateShots(request: GenerateShotsRequest): Promise<GenerateShotsResponse> {
  const data = await generatedClient.scriptMotion.apiGenerateShotsApiAicssV2ScriptsShotsPost({
    requestBody: {
      script_data: request.scriptData,
      shots_per_scene: request.shotsPerScene ?? 6,
      language: request.language,
      project_id: request.projectId,
    } as any,
  }) as {
    shots: Record<string, unknown>[];
    scene_transitions: Record<string, unknown>[];
    character_action_sequences: Record<string, unknown>[];
    total_duration_seconds: number;
    project_id?: string;
  };

  return {
    shots: (data.shots || []).map(s => {
      const shot = s as Record<string, unknown>;
      const vp = (shot.visual_prompts as Record<string, unknown>) || {};
      return {
        id: (shot.id as string) || '',
        sceneId: (shot.scene_id as string) || '',
        shotNumber: (shot.shot_number as number) || 0,
        actionSummary: (shot.action_summary as string) || '',
        dialogue: (shot.dialogue as string) || '',
        cameraMovement: ((shot.camera_movement as string) || 'Static') as Shot['cameraMovement'],
        shotSize: ((shot.shot_size as string) || 'Medium Shot') as Shot['shotSize'],
        characters: (shot.characters as string[]) || [],
        visualPrompts: {
          scenePrompt: (vp.scene_prompt as string) || '',
          actionPrompt: (vp.action_prompt as string) || '',
          cameraPrompt: (vp.camera_prompt as string) || '',
          transitionPrompt: (vp.transition_prompt as string) || '',
        },
        durationSeconds: (shot.duration_seconds as number) || 3.0,
        keyframeStartPrompt: (shot.keyframe_start_prompt as string) || '',
        keyframeEndPrompt: (shot.keyframe_end_prompt as string) || '',
      };
    }),
    sceneTransitions: (data.scene_transitions || []).map(t => {
      const trans = t as Record<string, unknown>;
      return {
        fromSceneId: trans.from_scene_id as string,
        toSceneId: trans.to_scene_id as string,
        transitionType: trans.transition_type as SceneTransition['transitionType'],
        transitionPrompt: trans.transition_prompt as string,
      };
    }),
    characterActionSequences: (data.character_action_sequences || []).map(seq => {
      const s = seq as Record<string, unknown>;
      return {
        characterId: s.character_id as string,
        characterName: s.character_name as string,
        shots: (s.shots as string[]) || [],
        actionSequencePrompt: s.action_sequence_prompt as string,
        intensityCurve: (s.intensity_curve as number[]) || [],
      };
    }),
    totalDurationSeconds: data.total_duration_seconds || 0,
    projectId: data.project_id,
  };
}

// ─── Scene Prompts ────────────────────────────────────────────────────────────

export async function getScenePrompts(shots: Shot[]): Promise<{ scenePrompts: ScenePrompt[]; transitionPrompts: SceneTransition[] }> {
  const serialized = shots.map(s => ({
    id: s.id,
    scene_id: s.sceneId,
    shot_number: s.shotNumber,
    scene_prompt: s.visualPrompts.scenePrompt,
    action_prompt: s.visualPrompts.actionPrompt,
    camera_prompt: s.visualPrompts.cameraPrompt,
    transition_prompt: s.visualPrompts.transitionPrompt || '',
    duration_seconds: s.durationSeconds,
  }));

  const data = await generatedClient.scriptMotion.apiGetScenePromptsApiAicssV2ScriptsScenePromptsPost({
    requestBody: { shots: serialized } as any,
  }) as {
    scene_prompts: Record<string, unknown>[];
    transition_prompts: Record<string, unknown>[];
  };

  return {
    scenePrompts: (data.scene_prompts || []).map(p => ({
      shotId: (p.shot_id as string) || '',
      sceneId: (p.scene_id as string) || '',
      shotNumber: (p.shot_number as number) || 0,
      scenePrompt: (p.scene_prompt as string) || '',
      actionPrompt: (p.action_prompt as string) || '',
      cameraPrompt: (p.camera_prompt as string) || '',
      transitionPrompt: (p.transition_prompt as string) || '',
      durationSeconds: (p.duration_seconds as number) || 0,
    })),
    transitionPrompts: (data.transition_prompts || []).map(t => ({
      fromSceneId: (t.from_scene_id as string) || '',
      toSceneId: (t.to_scene_id as string) || '',
      transitionType: (t.transition_type as SceneTransition['transitionType']) || 'cut',
      transitionPrompt: (t.transition_prompt as string) || '',
    })),
  };
}

// ─── Character Generation ─────────────────────────────────────────────────────

export async function generateThreeView(request: ThreeViewRequest): Promise<ThreeViewResponse> {
  const data = await generatedClient.scriptMotion.apiGenerateThreeViewApiAicssV2ScriptsCharactersGenerateThreeViewPost({
    requestBody: {
      character_id: request.characterId,
      character_name: request.characterName,
      character_gender: request.characterGender || '',
      character_age: request.characterAge || '',
      character_personality: request.characterPersonality || '',
      visual_prompt: request.visualPrompt,
      reference_image: request.referenceImage,
      project_id: request.projectId,
    } as any,
  }) as {
    character_id: string;
    visual_prompt: string;
    three_view_images: Record<string, string>;
    reference_image?: string;
    project_id?: string;
  };

  return {
    characterId: data.character_id,
    visualPrompt: data.visual_prompt,
    threeViewImages: data.three_view_images,
    referenceImage: data.reference_image,
    projectId: data.project_id,
  };
}

export async function generateVariation(
  characterId: string,
  variationPrompt: string,
  referenceImage?: string,
  projectId?: string
): Promise<{ variationId: string; image?: string }> {
  const data = await generatedClient.scriptMotion.apiGenerateVariationApiAicssV2ScriptsCharactersGenerateVariationPost({
    requestBody: {
      character_id: characterId,
      variation_prompt: variationPrompt,
      reference_image: referenceImage,
      project_id: projectId,
    } as any,
  }) as {
    character_id: string;
    variation_id: string;
    variation_prompt: string;
    image?: string;
    project_id?: string;
  };
  return {
    variationId: data.variation_id,
    image: data.image,
  };
}

// ─── Motion Generation ────────────────────────────────────────────────────────

export async function generateMotion(request: GenerateMotionRequest): Promise<MotionResponse> {
  const data = await generatedClient.scriptMotion.apiGenerateMotionApiAicssV2ScriptsMotionGeneratePost({
    requestBody: {
      shot_id: request.shotId,
      character_id: request.characterId,
      character_name: request.characterName,
      action_prompt: request.actionPrompt,
      start_image: request.startImage,
      end_image: request.endImage,
      duration_seconds: request.durationSeconds ?? 5.0,
      project_id: request.projectId,
    } as any,
  }) as {
    shot_id: string;
    character_id: string;
    status: string;
    video_path?: string;
    frame_count: number;
    segmented_frames: { frameIndex: number; path: string; filename: string }[];
    project_id?: string;
  };

  return {
    shotId: data.shot_id,
    characterId: data.character_id,
    status: (data.status as MotionResponse['status']) || 'pending',
    videoPath: data.video_path,
    frameCount: data.frame_count,
    segmentedFrames: data.segmented_frames || [],
    projectId: data.project_id,
  };
}

export async function segmentFrames(
  framePaths: string[],
  characterName: string,
  actionName: string,
  projectId?: string
): Promise<MotionResponse> {
  const data = await generatedClient.scriptMotion.apiSegmentFramesApiAicssV2ScriptsMotionSegmentPost({
    requestBody: {
      frame_paths: framePaths,
      character_name: characterName,
      action_name: actionName,
      project_id: projectId,
    } as any,
  }) as {
    segmented_frames: { frame_index: number; original_path: string; segmented_path: string }[];
  };

  return {
    shotId: '',
    characterId: '',
    status: 'done',
    frameCount: (data.segmented_frames || []).length,
    segmentedFrames: (data.segmented_frames || []).map((f, i) => ({
      frameIndex: f.frame_index ?? i,
      path: f.segmented_path,
      filename: f.segmented_path.split('/').pop() || '',
    })),
  };
}

// ─── Visual Prompt Generation ─────────────────────────────────────────────────

export async function generateVisualPrompt(
  characterName: string,
  gender: string = '',
  age: string = '',
  personality: string = '',
  genre: string = 'cinematic',
  language: string = 'chinese'
): Promise<string> {
  const data = await generatedClient.scriptMotion.apiGenerateVisualPromptApiAicssV2ScriptsVisualPromptPost({
    characterName,
    gender,
    age,
    personality,
    genre,
    language,
  }) as { visual_prompt: string };
  return data.visual_prompt;
}

// ─── Auto Three-View Batch Status ─────────────────────────────────────────────

export interface BatchCharacterStatus {
  name: string;
  status: 'queued' | 'running' | 'done' | 'failed';
  started_at: number;
  finished_at: number | null;
  error: string | null;
  visual_prompt: string | null;
  asset: Record<string, unknown> | null;
}

export interface BatchStatusResponse {
  project_id: string;
  characters: Record<string, BatchCharacterStatus>;
  summary: { queued: number; running: number; done: number; failed: number };
}

export async function getBatchStatus(projectId: string): Promise<BatchStatusResponse> {
  const data = await generatedClient.scriptMotion.apiBatchStatusApiAicssV2ScriptsCharactersBatchStatusGet({
    projectId,
  }) as BatchStatusResponse;
  return {
    project_id: data.project_id,
    characters: data.characters || {},
    summary: data.summary || { queued: 0, running: 0, done: 0, failed: 0 },
  };
}

export async function clearBatchStatus(projectId: string): Promise<void> {
  await generatedClient.scriptMotion.apiBatchClearApiAicssV2ScriptsCharactersBatchClearPost({ projectId });
}

// ─── Scene Asset Batch Status ──────────────────────────────────────────────────

export interface SceneBatchCharacterStatus {
  name: string;
  status: 'queued' | 'running' | 'done' | 'failed';
  started_at: number;
  finished_at: number | null;
  error: string | null;
  visual_prompt: string | null;
  asset: Record<string, unknown> | null;
}

export interface SceneBatchStatusResponse {
  project_id: string;
  scenes: Record<string, SceneBatchCharacterStatus>;
  summary: { queued: number; running: number; done: number; failed: number };
}

export async function getSceneBatchStatus(projectId: string): Promise<SceneBatchStatusResponse> {
  const data = await generatedClient.scriptMotion.apiSceneBatchStatusApiAicssV2ScriptsScenesBatchStatusGet({
    projectId,
  }) as SceneBatchStatusResponse;
  return {
    project_id: data.project_id,
    scenes: data.scenes || {},
    summary: data.summary || { queued: 0, running: 0, done: 0, failed: 0 },
  };
}

export async function clearSceneBatchStatus(projectId: string): Promise<void> {
  await generatedClient.scriptMotion.apiSceneBatchClearApiAicssV2ScriptsScenesBatchClearPost({ projectId });
}

// ─── Manual Scene Asset (single scene) ────────────────────────────────────────

export interface SceneAssetRequest {
  sceneId: string;
  location: string;
  time: string;
  atmosphere?: string;
  visualPrompt?: string;
  referenceImage?: string;
  projectId?: string;
}

export async function generateSceneAsset(request: SceneAssetRequest): Promise<SceneAsset> {
  const data = await generatedClient.scriptMotion.apiGenerateSceneAssetApiAicssV2ScriptsScenesGenerateAssetPost({
    requestBody: {
      scene_id: request.sceneId,
      location: request.location,
      time: request.time,
      atmosphere: request.atmosphere || '',
      visual_prompt: request.visualPrompt,
      reference_image: request.referenceImage,
      project_id: request.projectId,
    } as any,
  }) as {
    scene_id: string;
    visual_prompt: string;
    keyframe_images: Record<string, string>;
    project_id?: string;
  };
  return {
    sceneId: data.scene_id,
    visualPrompt: data.visual_prompt,
    keyframeImages: data.keyframe_images || {},
  };
}

// ─── Scene Depth Layers (Module 3) ────────────────────────────────────────────
//
// Asynchronous endpoint approach: frontend fires `POST /api/aicss/layers/export`
// on user demand with one of the keyframe images as `imageUrl`. The backend
// runs DepthAnything → spatial bucketing → RGBA-per-layer PNG export, returns
// 4 data URIs + Z-offset table. No persistence — the caller decides whether to
// cache the result. See `useScriptStore.layerScene` for the wiring.

export interface SceneLayersRequest {
  // One of the keyframe images. Accepts plain base64 (no data: prefix needed).
  imageUrl: string;
  // Optional subset of layer names to export; defaults to all four.
  layers?: Array<'sky' | 'background' | 'midground' | 'foreground'>;
  featherPx?: number;
}

export interface SceneLayersResponse {
  width: number;
  height: number;
  layers: {
    sky?: { dataUri: string };
    background?: { dataUri: string };
    midground?: { dataUri: string };
    foreground?: { dataUri: string };
  };
  zOffsets: Array<{ layer: string; zOffset: number; zMin: number; zMax: number }>;
}

export async function exportSceneLayers(
  request: SceneLayersRequest,
  options?: { signal?: AbortSignal },
): Promise<SceneLayersResponse> {
  // The generated client returns a CancelablePromise; wire the caller's
  // AbortSignal to its cancel() so `useScriptStore` can abort in-flight layer
  // exports when a newer request supersedes the old one.
  const promise = generatedClient.layers.layersExportApiAicssLayersExportPost({
    requestBody: {
      imageUrl: request.imageUrl,
      layers: request.layers,
      featherPx: request.featherPx,
    } as any,
  }) as Promise<SceneLayersResponse>;

  if (options?.signal) {
    const signal = options.signal;
    const cancelable = promise as unknown as { cancel?: () => void };
    if (signal.aborted) {
      cancelable.cancel?.();
    } else {
      signal.addEventListener('abort', () => cancelable.cancel?.(), { once: true });
    }
  }

  return promise;
}

// ─── Shot archive (module 5) ──────────────────────────────────────────────────

export interface ArchiveShotResponse {
  projectId: string;
  shotId: string;
  fileName: string;
  fileSize: number;
  fileCount: number;
  downloadUrl: string;
  layerCount: number;
  meshCount: number;
}

/**
 * Pack shot assets into a Blender-ready ZIP and return metadata + download URL.
 *
 * Handwritten (not the generated `v2Shots.archiveShot...` method) because the
 * OpenAPI snapshot's `archive_shot` operation doesn't expose the
 * `lighting_preset` query param, but T13 added it as a forward-compatible
 * query string that `ScriptEditor.tsx`'s `handleArchiveShot` passes through
 * from `useAppStore.getState().lightingPreset`. The generated client can't
 * send undeclared query params, so we keep a small axios call here.
 */
export async function archiveShot(
  projectId: string,
  shotId: string,
  sceneId?: string,
  lightingPreset?: string | null,
): Promise<ArchiveShotResponse> {
  const api = axios.create({
    baseURL: `${DEFAULT_BACKEND}/api/aicss`,
    timeout: 30 * 60 * 1000,
  });
  const path =
    '/v2/projects/' +
    encodeURIComponent(projectId) +
    '/shots/' +
    encodeURIComponent(shotId) +
    '/archive';
  const params: Record<string, string> = {};
  if (sceneId) params.scene_id = sceneId;
  // T13: pass the lighting preset name so the backend can stamp it into the
  // shot archive manifest's `lightingPreset` field. The backend endpoint
  // currently ignores this query param (W2 owns backend wiring); sending it
  // is forward-compatible and satisfies the T13 frontend acceptance criterion.
  if (lightingPreset) params.lighting_preset = lightingPreset;
  const { data } = await api.post<ArchiveShotResponse>(
    path,
    null,
    { params: Object.keys(params).length ? params : undefined },
  );
  return data;
}

/** Trigger browser download of the shot archive ZIP. */
export async function downloadShotArchive(projectId: string, shotId: string, fileName?: string): Promise<void> {
  // Handwritten: the generated client returns parsed JSON, but this endpoint
  // streams a binary ZIP blob.
  const url =
    DEFAULT_BACKEND +
    '/api/aicss/v2/projects/' +
    encodeURIComponent(projectId) +
    '/shots/' +
    encodeURIComponent(shotId) +
    '/archive/download';
  const resp = await axios.get(url, { responseType: 'blob', timeout: 10 * 60 * 1000 });
  const blob = new Blob([resp.data], { type: 'application/zip' });
  const href = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = href;
  a.download = fileName || projectId + '_' + shotId + '_archive.zip';
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(href);
}
