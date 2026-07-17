// ─────────────────────────────────────────────────────────────────────────────
// AICSS Script Service — v2 API client for the script splitting pipeline.
// Wraps the backend script_parser / shot_generator / character_generator /
// motion_extractor endpoints.
// ─────────────────────────────────────────────────────────────────────────────
import axios from 'axios';
import type {
  ScriptData, Shot, SceneTransition, CharacterActionSequence,
  CharacterAsset, MotionResponse,
  ParseScriptRequest, ParseScriptResponse,
  GenerateShotsRequest, GenerateShotsResponse,
  ThreeViewRequest, ThreeViewResponse,
  GenerateMotionRequest, ScenePrompt,
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
  const { data } = await api.post<ParseScriptResponse>('/v2/scripts/parse', {
    raw_text: request.rawText,
    language: request.language,
    project_id: request.projectId,
    dashscope_api_key: request.dashscopeApiKey || undefined,
  });
  return data;
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