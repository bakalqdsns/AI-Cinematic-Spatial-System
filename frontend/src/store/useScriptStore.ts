// ─────────────────────────────────────────────────────────────────────────────
// AICSS Script Store — Zustand
// Manages: raw script input, parsed ScriptData, generated shots, scene
// transitions, character action sequences, character assets, motion sequences.
// ─────────────────────────────────────────────────────────────────────────────
import { create } from 'zustand';
import type {
  ScriptData, Shot, SceneTransition, CharacterActionSequence,
  CharacterAsset, MotionSequence, ScriptLanguage,
} from '../types/script';
import * as scriptService from '../services/scriptService';
import { useAppStore } from './useAppStore';

interface ScriptStore {
  // ─── Input state ───────────────────────────────────────────────────────────
  rawScript: string;
  language: ScriptLanguage;

  // ─── Parsed state ──────────────────────────────────────────────────────────
  parsedScript: ScriptData | null;
  normalizedScript: string;

  // ─── Shot generation ───────────────────────────────────────────────────────
  shots: Shot[];
  sceneTransitions: SceneTransition[];
  characterActionSequences: CharacterActionSequence[];

  // ─── Character / motion ────────────────────────────────────────────────────
  characterAssets: Record<string, CharacterAsset>;
  motionSequences: Record<string, MotionSequence>;

  // ─── Loading flags ─────────────────────────────────────────────────────────
  isParsing: boolean;
  isGeneratingShots: boolean;
  isGeneratingCharacter: Record<string, boolean>;
  isGeneratingMotion: Record<string, boolean>;

  // ─── UI state ──────────────────────────────────────────────────────────────
  selectedShotId: string | null;
  selectedCharacterId: string | null;
  activeTab: 'script' | 'storyboard' | 'characters' | 'motion';

  // ─── Error state ───────────────────────────────────────────────────────────
  error: string | null;

  // ─── Actions ───────────────────────────────────────────────────────────────
  setRawScript: (text: string) => void;
  setLanguage: (lang: ScriptLanguage) => void;
  setActiveTab: (tab: ScriptStore['activeTab']) => void;
  selectShot: (shotId: string | null) => void;
  selectCharacter: (charId: string | null) => void;

  parseScript: (projectId?: string) => Promise<void>;
  generateShots: (projectId?: string) => Promise<void>;

  generateCharacterThreeView: (charId: string, projectId?: string) => Promise<void>;
  generateCharacterVariation: (charId: string, prompt: string, projectId?: string) => Promise<void>;
  updateCharacterVisualPrompt: (charId: string, prompt: string) => void;

  generateMotion: (shotId: string, charId: string, projectId?: string) => Promise<void>;

  reset: () => void;
  loadFromProject: (data: {
    scriptData?: ScriptData;
    normalizedScript?: string;
    shots?: Shot[];
    sceneTransitions?: SceneTransition[];
    characterActionSequences?: CharacterActionSequence[];
    characterAssets?: Record<string, CharacterAsset>;
  }) => void;
}

const initialState = {
  rawScript: '',
  language: 'chinese' as ScriptLanguage,
  parsedScript: null as ScriptData | null,
  normalizedScript: '',
  shots: [] as Shot[],
  sceneTransitions: [] as SceneTransition[],
  characterActionSequences: [] as CharacterActionSequence[],
  characterAssets: {} as Record<string, CharacterAsset>,
  motionSequences: {} as Record<string, MotionSequence>,
  isParsing: false,
  isGeneratingShots: false,
  isGeneratingCharacter: {} as Record<string, boolean>,
  isGeneratingMotion: {} as Record<string, boolean>,
  selectedShotId: null as string | null,
  selectedCharacterId: null as string | null,
  activeTab: 'script' as const,
  error: null as string | null,
};

export const useScriptStore = create<ScriptStore>((set, get) => ({
  ...initialState,

  setRawScript: (text) => set({ rawScript: text, error: null }),
  setLanguage: (lang) => set({ language: lang }),
  setActiveTab: (tab) => set({ activeTab: tab }),
  selectShot: (shotId) => set({ selectedShotId: shotId }),
  selectCharacter: (charId) => set({ selectedCharacterId: charId }),

  // ─── Pass 1+2: parse raw script into structured ScriptData ────────────────
  parseScript: async (projectId) => {
    const { rawScript, language } = get();
    if (!rawScript.trim()) {
      set({ error: 'Please enter a script' });
      return;
    }

    const dashscopeApiKey = useAppStore.getState().dashscopeApiKey;
    set({ isParsing: true, error: null });
    try {
      const response = await scriptService.parseScript({
        rawText: rawScript,
        language,
        projectId,
        dashscopeApiKey: dashscopeApiKey || undefined,
      });

      set({
        normalizedScript: response.normalizedScript,
        parsedScript: response.scriptData,
        isParsing: false,
      });
    } catch (err) {
      set({
        isParsing: false,
        error: err instanceof Error ? err.message : 'Script parsing failed',
      });
    }
  },

  // ─── Pass 3: derive per-scene shots + transitions + character sequences ───
  generateShots: async (projectId) => {
    const { parsedScript } = get();
    if (!parsedScript) {
      set({ error: 'Please parse the script first' });
      return;
    }

    set({ isGeneratingShots: true, error: null });
    try {
      const response = await scriptService.generateShots({
        scriptData: parsedScript,
        shotsPerScene: 6,
        language: parsedScript.language,
        projectId,
      });

      set({
        shots: response.shots,
        sceneTransitions: response.sceneTransitions,
        characterActionSequences: response.characterActionSequences,
        isGeneratingShots: false,
      });
    } catch (err) {
      set({
        isGeneratingShots: false,
        error: err instanceof Error ? err.message : 'Shot generation failed',
      });
    }
  },

  // ─── Character asset generation (3-view turnaround) ───────────────────────
  generateCharacterThreeView: async (charId, projectId) => {
    const { parsedScript, characterAssets } = get();
    if (!parsedScript) return;

    const char = parsedScript.characters.find(c => c.id === charId);
    if (!char) return;

    set(state => ({
      isGeneratingCharacter: {
        ...state.isGeneratingCharacter,
        [charId]: true,
      },
      error: null,
    }));

    try {
      const response = await scriptService.generateThreeView({
        characterId: char.id,
        characterName: char.name,
        characterGender: char.gender,
        characterAge: char.age,
        characterPersonality: char.personality,
        visualPrompt: char.visualPrompt,
        projectId,
      });

      const asset: CharacterAsset = {
        characterId: char.id,
        visualPrompt: response.visualPrompt,
        referenceImage: response.referenceImage,
        threeViewImages: response.threeViewImages,
        variations: characterAssets[charId]?.variations || [],
      };

      set(state => ({
        characterAssets: {
          ...state.characterAssets,
          [charId]: asset,
        },
        isGeneratingCharacter: {
          ...state.isGeneratingCharacter,
          [charId]: false,
        },
      }));
    } catch (err) {
      set(state => ({
        isGeneratingCharacter: {
          ...state.isGeneratingCharacter,
          [charId]: false,
        },
        error: err instanceof Error ? err.message : 'Character generation failed',
      }));
    }
  },

  // ─── Character variation (costumes / expressions) ──────────────────────────
  generateCharacterVariation: async (charId, prompt, projectId) => {
    const { characterAssets } = get();
    const asset = characterAssets[charId];

    set(state => ({
      isGeneratingCharacter: {
        ...state.isGeneratingCharacter,
        [charId]: true,
      },
      error: null,
    }));

    try {
      const response = await scriptService.generateVariation(
        charId,
        prompt,
        asset?.referenceImage,
        projectId,
      );

      const variation = {
        id: response.variationId,
        name: prompt.slice(0, 50),
        visualPrompt: prompt,
        image: response.image,
      };

      set(state => {
        const existing = state.characterAssets[charId];
        return {
          characterAssets: {
            ...state.characterAssets,
            [charId]: {
              ...(existing || {
                characterId: charId,
                visualPrompt: '',
                threeViewImages: {},
                variations: [],
              }),
              variations: [...(existing?.variations || []), variation],
            },
          },
          isGeneratingCharacter: {
            ...state.isGeneratingCharacter,
            [charId]: false,
          },
        };
      });
    } catch (err) {
      set(state => ({
        isGeneratingCharacter: {
          ...state.isGeneratingCharacter,
          [charId]: false,
        },
        error: err instanceof Error ? err.message : 'Variation generation failed',
      }));
    }
  },

  // ─── Local mutation (no API call) — keeps parsedScript as the source of truth
  updateCharacterVisualPrompt: (charId, prompt) => {
    const { parsedScript } = get();
    if (!parsedScript) return;

    set(state => {
      if (!state.parsedScript) return state;
      return {
        parsedScript: {
          ...state.parsedScript,
          characters: state.parsedScript.characters.map(c =>
            c.id === charId ? { ...c, visualPrompt: prompt } : c,
          ),
        },
      };
    });
  },

  // ─── Motion generation: text→video + frame extraction + segmentation ──────
  generateMotion: async (shotId, charId, projectId) => {
    const { shots, parsedScript, characterAssets } = get();
    const shot = shots.find(s => s.id === shotId);
    const char = parsedScript?.characters.find(c => c.id === charId);
    const asset = characterAssets[charId];

    if (!shot || !char) return;

    // Composite key shot×character — a single shot can spawn multiple motions
    // if more than one character appears in it.
    const key = `${shotId}_${charId}`;
    set(state => ({
      isGeneratingMotion: {
        ...state.isGeneratingMotion,
        [key]: true,
      },
      motionSequences: {
        ...state.motionSequences,
        [key]: {
          shotId,
          characterId: charId,
          characterName: char.name,
          actionDescription: shot.visualPrompts.actionPrompt,
          status: 'generating',
          frameCount: 0,
        },
      },
      error: null,
    }));

    try {
      const response = await scriptService.generateMotion({
        shotId,
        characterId: charId,
        characterName: char.name,
        actionPrompt: shot.visualPrompts.actionPrompt,
        startImage: asset?.threeViewImages?.front,
        endImage: asset?.threeViewImages?.back,
        projectId,
      });

      set(state => ({
        motionSequences: {
          ...state.motionSequences,
          [key]: {
            ...(state.motionSequences[key] || {
              shotId,
              characterId: charId,
              characterName: char.name,
              actionDescription: shot.visualPrompts.actionPrompt,
              frameCount: 0,
            }),
            status: response.status,
            videoPath: response.videoPath,
            frameCount: response.frameCount,
          },
        },
        isGeneratingMotion: {
          ...state.isGeneratingMotion,
          [key]: false,
        },
      }));
    } catch (err) {
      set(state => ({
        motionSequences: {
          ...state.motionSequences,
          [key]: {
            ...(state.motionSequences[key] || {
              shotId,
              characterId: charId,
              characterName: char.name,
              actionDescription: shot.visualPrompts.actionPrompt,
              frameCount: 0,
            }),
            status: 'error',
            error: err instanceof Error ? err.message : 'Motion generation failed',
          },
        },
        isGeneratingMotion: {
          ...state.isGeneratingMotion,
          [key]: false,
        },
      }));
    }
  },

  reset: () => set({ ...initialState }),

  // Bulk-load state from a persisted project. Useful when reopening a session
  // that already had a script parsed and shots generated.
  loadFromProject: (data) => set({
    parsedScript: data.scriptData || null,
    normalizedScript: data.normalizedScript || '',
    shots: data.shots || [],
    sceneTransitions: data.sceneTransitions || [],
    characterActionSequences: data.characterActionSequences || [],
    characterAssets: data.characterAssets || {},
  }),
}));