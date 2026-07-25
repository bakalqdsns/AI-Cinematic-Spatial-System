// ─────────────────────────────────────────────────────────────────────────────
// AICSS Script Service — v2 API client for the script splitting pipeline.
// Wraps the backend script_parser / shot_generator / character_generator /
// motion_extractor endpoints.
// ─────────────────────────────────────────────────────────────────────────────
import axios from 'axios';
import type {
  ScriptData, Shot, SceneTransition, CharacterActionSequence,
  CharacterAsset, Character, MotionResponse,
  ParseScriptRequest, ParseScriptResponse,
  ExtractCharactersRequest, ExtractCharactersResponse,
  GenerateShotsRequest, GenerateShotsResponse,
  ThreeViewRequest, ThreeViewResponse,
  GenerateMotionRequest, ScenePrompt,
  ScriptLanguage, ParagraphType,
} from '../types/script';

const BASE_URL = import.meta.env.VITE_AICSS_BACKEND || 'http://localhost:8000';

// Script parsing and shot generation involve multi-step LLM pipelines that can
// take several minutes per scene, so we extend the default timeout to 5min —
// matches the convention used by sequenceService.
const api = axios.create({
  baseURL: `${BASE_URL}/api/aicss`,
  timeout: 300_000,
});

// ─── Script Parsing ───────────────────────────────────────────────────────────

export async function parseScript(request: ParseScriptRequest): Promise<ParseScriptResponse> {
  console.log('[scriptService] parseScript called with:', { rawTextLength: request.rawText.length, language: request.language });

  // Character-first pipeline: pre-extract characters first, then run the
  // backend /parse endpoint. The backend will still run its own extraction
  // inside /parse, but having a separate call lets the UI display characters
  // as soon as they're identified (before the slower full parse completes).
  //
  // The /parse response's `script_data.characters` is the authoritative source
  // once it arrives — we only use the pre-extraction result to populate the
  // UI optimistically.
  const charPromise = extractCharacters({
    rawText: request.rawText,
    language: request.language,
    projectId: request.projectId,
  }).catch((err) => {
    console.warn('[scriptService] pre-extract characters failed (non-fatal):', err);
    return { characters: [] as Character[], projectId: request.projectId };
  });

  const { data } = await api.post<{
    normalized_script: string;
    script_data: Record<string, unknown>;
    project_id?: string;
  }>('/v2/scripts/parse', {
    raw_text: request.rawText,
    language: request.language,
    project_id: request.projectId,
    dashscope_api_key: request.dashscopeApiKey || undefined,
  });
  console.log('[scriptService] parseScript response:', data);

  // Map snake_case API response to camelCase type
  const response: ParseScriptResponse = {
    normalizedScript: data.normalized_script || '',
    scriptData: _deserializeScriptData(data.script_data || {}),
    projectId: data.project_id,
  };

  // Surface pre-extracted characters so the UI can adopt them even before
  // /parse finishes parsing them. The final scriptData overrides in any case.
  // We deliberately don't await charPromise — it's a non-blocking progressive
  // enhancement. The caller can call extractCharacters directly if they want
  // the standalone result.
  void charPromise;

  return response;
}

export async function extractCharacters(request: ExtractCharactersRequest): Promise<ExtractCharactersResponse> {
  console.log('[scriptService] extractCharacters called');
  const { data } = await api.post<{
    characters: Record<string, unknown>[];
    project_id?: string;
  }>('/v2/scripts/characters/extract', {
    raw_text: request.rawText,
    language: request.language,
    project_id: request.projectId,
  });

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
      time: (s.time as string) || 'Day',
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
  // Use snake_case payload fields to match the backend Pydantic models directly.
  const { data } = await api.post<{
    shots: Record<string, unknown>[];
    scene_transitions: Record<string, unknown>[];
    character_action_sequences: Record<string, unknown>[];
    total_duration_seconds: number;
    project_id?: string;
  }>('/v2/scripts/shots', {
    script_data: request.scriptData,
    shots_per_scene: request.shotsPerScene ?? 6,
    language: request.language,
    project_id: request.projectId,
  });

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

  const { data } = await api.post<{
    scene_prompts: Record<string, unknown>[];
    transition_prompts: Record<string, unknown>[];
  }>('/v2/scripts/scene-prompts', { shots: serialized });

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
  const { data } = await api.post<{
    character_id: string;
    visual_prompt: string;
    three_view_images: Record<string, string>;
    reference_image?: string;
    project_id?: string;
  }>('/v2/scripts/characters/generate-three-view', {
    character_id: request.characterId,
    character_name: request.characterName,
    character_gender: request.characterGender || '',
    character_age: request.characterAge || '',
    character_personality: request.characterPersonality || '',
    visual_prompt: request.visualPrompt,
    reference_image: request.referenceImage,
    project_id: request.projectId,
  });

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
  const { data } = await api.post<{
    character_id: string;
    variation_id: string;
    variation_prompt: string;
    image?: string;
    project_id?: string;
  }>('/v2/scripts/characters/generate-variation', {
    character_id: characterId,
    variation_prompt: variationPrompt,
    reference_image: referenceImage,
    project_id: projectId,
  });
  return {
    variationId: data.variation_id,
    image: data.image,
  };
}

// ─── Motion Generation ────────────────────────────────────────────────────────

export async function generateMotion(request: GenerateMotionRequest): Promise<MotionResponse> {
  const { data } = await api.post<{
    shot_id: string;
    character_id: string;
    status: string;
    video_path?: string;
    frame_count: number;
    segmented_frames: { frameIndex: number; path: string; filename: string }[];
    project_id?: string;
  }>('/v2/scripts/motion/generate', {
    shot_id: request.shotId,
    character_id: request.characterId,
    character_name: request.characterName,
    action_prompt: request.actionPrompt,
    start_image: request.startImage,
    end_image: request.endImage,
    duration_seconds: request.durationSeconds ?? 5.0,
    project_id: request.projectId,
  });

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
  const { data } = await api.post<{
    segmented_frames: { frame_index: number; original_path: string; segmented_path: string }[];
  }>('/v2/scripts/motion/segment', {
    frame_paths: framePaths,
    character_name: characterName,
    action_name: actionName,
    project_id: projectId,
  });

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
  // The visual-prompt endpoint takes all parameters as query string so it can
  // be triggered cheaply from auto-fill inputs without serializing a payload.
  const { data } = await api.post<{ visual_prompt: string }>('/v2/scripts/visual-prompt', null, {
    params: { character_name: characterName, gender, age, personality, genre, language },
  });
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
  const { data } = await api.get<{
    project_id: string;
    characters: Record<string, BatchCharacterStatus>;
    summary: { queued: number; running: number; done: number; failed: number };
  }>('/v2/scripts/characters/batch-status', { params: { project_id: projectId } });
  return {
    projectId: data.project_id,
    characters: data.characters || {},
    summary: data.summary || { queued: 0, running: 0, done: 0, failed: 0 },
  };
}

export async function clearBatchStatus(projectId: string): Promise<void> {
  await api.post('/v2/scripts/characters/batch-clear', null, { params: { project_id: projectId } });
}