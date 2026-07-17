// ─────────────────────────────────────────────────────────────────────────────
// AICSS Frontend — Script Splitting Types
// TypeScript mirrors of backend script_parser / shot_generator / character_generator /
// motion_extractor dataclasses. Use camelCase in the frontend and convert to
// snake_case at the API boundary via serializeScriptData / deserializeScriptData
// helpers below.
// ─────────────────────────────────────────────────────────────────────────────

export type ScriptLanguage = 'chinese' | 'english' | 'japanese';

export interface Character {
  id: string;
  name: string;
  gender: string;
  age: string;
  personality: string;
  visualPrompt?: string;
  referenceImage?: string;
  variations?: CharacterVariation[];
}

export interface CharacterVariation {
  id: string;
  name: string;
  visualPrompt: string;
  image?: string;
}

export interface Scene {
  id: string;
  location: string;
  time: 'Day' | 'Night' | 'Dawn' | 'Dusk' | 'Morning' | 'Evening';
  atmosphere: string;
}

export interface StoryParagraph {
  id: string;
  text: string;
  sceneRefId: string;
}

export interface ScriptData {
  title: string;
  genre: string;
  logline: string;
  characters: Character[];
  scenes: Scene[];
  storyParagraphs: StoryParagraph[];
  language: ScriptLanguage;
}

export type CameraMovement =
  | 'Dolly In' | 'Dolly Out' | 'Pan Right' | 'Pan Left'
  | 'Tilt Up' | 'Tilt Down' | 'Static' | 'Handheld'
  | 'Tracking' | 'Crane Up' | 'Crane Down' | 'Zoom In' | 'Zoom Out';

export type ShotSize =
  | 'Extreme Close-up' | 'Close-up' | 'Medium Close-up' | 'Medium Shot'
  | 'Medium Wide' | 'Wide Shot' | 'Extreme Wide'
  | 'Over-the-Shoulder' | 'POV' | 'Two-Shot';

export interface VisualPrompts {
  scenePrompt: string;
  actionPrompt: string;
  cameraPrompt: string;
  transitionPrompt?: string;
}

export interface Shot {
  id: string;
  sceneId: string;
  shotNumber: number;
  actionSummary: string;
  dialogue: string;
  cameraMovement: CameraMovement;
  shotSize: ShotSize;
  characters: string[];
  visualPrompts: VisualPrompts;
  durationSeconds: number;
  keyframeStartPrompt: string;
  keyframeEndPrompt: string;
}

export interface SceneTransition {
  fromSceneId: string;
  toSceneId: string;
  transitionType: 'cut' | 'dissolve' | 'fade' | 'wipe';
  transitionPrompt: string;
}

export interface CharacterActionSequence {
  characterId: string;
  characterName: string;
  shots: string[];
  actionSequencePrompt: string;
  intensityCurve: number[];
}

export interface ScenePrompt {
  shotId: string;
  sceneId: string;
  shotNumber: number;
  scenePrompt: string;
  actionPrompt: string;
  cameraPrompt: string;
  transitionPrompt: string;
  durationSeconds: number;
}

export interface CharacterAsset {
  characterId: string;
  visualPrompt: string;
  referenceImage?: string;
  threeViewImages: {
    front?: string;
    side?: string;
    back?: string;
  };
  variations: CharacterVariation[];
}

export type MotionStatus = 'pending' | 'generating' | 'extracting' | 'segmenting' | 'done' | 'error';

export interface MotionSequence {
  shotId: string;
  characterId: string;
  characterName: string;
  actionDescription: string;
  videoPath?: string;
  videoUrl?: string;
  frameCount: number;
  frameDir?: string;
  segmentedDir?: string;
  status: MotionStatus;
  error?: string;
}

export interface SegmentedFrame {
  frameIndex: number;
  originalPath: string;
  segmentedPath: string;
  characterName: string;
  actionName: string;
  success: boolean;
}

// ─── API Request / Response ───────────────────────────────────────────────────

export interface ParseScriptRequest {
  rawText: string;
  language: ScriptLanguage;
  projectId?: string;
  dashscopeApiKey?: string;
}

export interface ParseScriptResponse {
  normalizedScript: string;
  scriptData: ScriptData;
  projectId?: string;
}

export interface GenerateShotsRequest {
  scriptData: ScriptData;
  shotsPerScene?: number;
  language?: ScriptLanguage;
  projectId?: string;
}

export interface GenerateShotsResponse {
  shots: Shot[];
  sceneTransitions: SceneTransition[];
  characterActionSequences: CharacterActionSequence[];
  totalDurationSeconds: number;
  projectId?: string;
}

export interface ThreeViewRequest {
  characterId: string;
  characterName: string;
  characterGender?: string;
  characterAge?: string;
  characterPersonality?: string;
  visualPrompt?: string;
  referenceImage?: string;
  projectId?: string;
}

export interface ThreeViewResponse {
  characterId: string;
  visualPrompt: string;
  threeViewImages: { front?: string; side?: string; back?: string };
  referenceImage?: string;
  projectId?: string;
}

export interface GenerateMotionRequest {
  shotId: string;
  characterId: string;
  characterName: string;
  actionPrompt: string;
  startImage?: string;
  endImage?: string;
  durationSeconds?: number;
  projectId?: string;
}

export interface MotionResponse {
  shotId: string;
  characterId: string;
  status: MotionStatus;
  videoPath?: string;
  frameCount: number;
  segmentedFrames: { frameIndex: number; path: string; filename: string }[];
  projectId?: string;
}

// ─── Serialization helpers (camelCase ↔ snake_case) ──────────────────────────
// The backend serializes dataclasses with snake_case field names (e.g.
// visual_prompt, scene_ref_id). These helpers convert at the API boundary so
// the rest of the frontend can use idiomatic camelCase.

export function serializeScriptData(data: ScriptData): Record<string, unknown> {
  return {
    title: data.title,
    genre: data.genre,
    logline: data.logline,
    characters: data.characters.map(c => ({
      id: c.id,
      name: c.name,
      gender: c.gender,
      age: c.age,
      personality: c.personality,
      visual_prompt: c.visualPrompt || '',
      reference_image: c.referenceImage,
      variations: c.variations,
    })),
    scenes: data.scenes.map(s => ({
      id: s.id,
      location: s.location,
      time: s.time,
      atmosphere: s.atmosphere,
    })),
    story_paragraphs: data.storyParagraphs.map(p => ({
      id: p.id,
      text: p.text,
      scene_ref_id: p.sceneRefId,
    })),
    language: data.language,
  };
}

export function deserializeScriptData(data: Record<string, unknown>): ScriptData {
  return {
    title: (data.title as string) || '',
    genre: (data.genre as string) || '',
    logline: (data.logline as string) || '',
    characters: ((data.characters as Record<string, unknown>[]) || []).map(c => ({
      id: (c.id as string) || '',
      name: (c.name as string) || '',
      gender: (c.gender as string) || '',
      age: (c.age as string) || '',
      personality: (c.personality as string) || '',
      visualPrompt: (c.visual_prompt as string) || (c.visualPrompt as string) || '',
      referenceImage: (c.reference_image as string) || (c.referenceImage as string),
      variations: (c.variations as CharacterVariation[]) || [],
    })),
    scenes: ((data.scenes as Record<string, unknown>[]) || []).map(s => ({
      id: (s.id as string) || '',
      location: (s.location as string) || '',
      time: ((s.time as string) || 'Day') as Scene['time'],
      atmosphere: (s.atmosphere as string) || '',
    })),
    storyParagraphs: ((data.story_paragraphs as Record<string, unknown>[]) || []).map(p => ({
      id: (p.id as string) || '',
      text: (p.text as string) || '',
      sceneRefId: (p.scene_ref_id as string) || (p.sceneRefId as string) || '',
    })),
    language: ((data.language as string) || 'chinese') as ScriptLanguage,
  };
}

export function serializeShots(shots: Shot[]): Record<string, unknown>[] {
  return shots.map(s => ({
    id: s.id,
    scene_id: s.sceneId,
    shot_number: s.shotNumber,
    action_summary: s.actionSummary,
    dialogue: s.dialogue,
    camera_movement: s.cameraMovement,
    shot_size: s.shotSize,
    characters: s.characters,
    visual_prompts: {
      scene_prompt: s.visualPrompts.scenePrompt,
      action_prompt: s.visualPrompts.actionPrompt,
      camera_prompt: s.visualPrompts.cameraPrompt,
      transition_prompt: s.visualPrompts.transitionPrompt || '',
    },
    duration_seconds: s.durationSeconds,
    keyframe_start_prompt: s.keyframeStartPrompt,
    keyframe_end_prompt: s.keyframeEndPrompt,
  }));
}

export function deserializeShots(data: Record<string, unknown>[]): Shot[] {
  return (data || []).map((s: Record<string, unknown>) => {
    const vp = (s.visual_prompts as Record<string, unknown>) || {};
    return {
      id: (s.id as string) || '',
      sceneId: (s.scene_id as string) || (s.sceneId as string) || '',
      shotNumber: (s.shot_number as number) || (s.shotNumber as number) || 0,
      actionSummary: (s.action_summary as string) || (s.actionSummary as string) || '',
      dialogue: (s.dialogue as string) || '',
      cameraMovement: ((s.camera_movement as string) || 'Static') as CameraMovement,
      shotSize: ((s.shot_size as string) || 'Medium Shot') as ShotSize,
      characters: ((s.characters as string[]) || []),
      visualPrompts: {
        scenePrompt: (vp.scene_prompt as string) || (s.scene_prompt as string) || '',
        actionPrompt: (vp.action_prompt as string) || (s.action_prompt as string) || '',
        cameraPrompt: (vp.camera_prompt as string) || (s.camera_prompt as string) || '',
        transitionPrompt: (vp.transition_prompt as string) || (s.transition_prompt as string) || '',
      },
      durationSeconds: (s.duration_seconds as number) || (s.durationSeconds as number) || 3.0,
      keyframeStartPrompt: (s.keyframe_start_prompt as string) || (s.keyframeStartPrompt as string) || '',
      keyframeEndPrompt: (s.keyframe_end_prompt as string) || (s.keyframeEndPrompt as string) || '',
    };
  });
}