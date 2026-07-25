// ─────────────────────────────────────────────────────────────────────────────
// AICSS Script Store — Zustand
// Manages: raw script input, parsed ScriptData, generated shots, scene
// transitions, character action sequences, character assets, motion sequences.
// ─────────────────────────────────────────────────────────────────────────────
import { create } from 'zustand';
import type {
  ScriptData, Shot, SceneTransition, CharacterActionSequence,
  CharacterAsset, Character, MotionSequence, ScriptLanguage,
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
  // Character-first pipeline: characters are identified up front (before the
  // full scene/paragraph parse) so the UI can render them while the rest of
  // the pipeline is still running.
  extractedCharacters: Character[];
  isExtractingCharacters: boolean;

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
  extractCharacters: (projectId?: string) => Promise<Character[]>;
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
  extractedCharacters: [] as Character[],
  isExtractingCharacters: false,
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

  // ─── Pass 1: extract characters only (independent fast step) ────────────────
  extractCharacters: async (projectId) => {
    const { rawScript, language } = get();
    if (!rawScript.trim()) {
      set({ error: 'Please enter a script' });
      return [];
    }
    set({ isExtractingCharacters: true, error: null });
    try {
      const response = await scriptService.extractCharacters({
        rawText: rawScript,
        language,
        projectId,
      });
      set({ extractedCharacters: response.characters, isExtractingCharacters: false });
      return response.characters;
    } catch (err) {
      console.error('[useScriptStore] extractCharacters error:', err);
      set({
        isExtractingCharacters: false,
        error: err instanceof Error ? err.message : 'Character extraction failed',
      });
      return [];
    }
  },

  // ─── Pass 1+2: parse raw script into structured ScriptData ────────────────
  // Character-first pipeline:
  //   1. Run extractCharacters first so the UI shows characters immediately
  //      while the heavier /parse is in flight.
  //   2. Run /parse, then merge: keep pre-extracted characters only if the
  //      parse response's characters list is empty (defence-in-depth — the
  //      backend's filter should already be reliable, but this guards
  //      against regressions).
  parseScript: async (projectId) => {
    const { rawScript, language } = get();
    console.log('[useScriptStore] parseScript called, rawScript length:', rawScript.length, 'language:', language);
    if (!rawScript.trim()) {
      const error = 'Please enter a script';
      console.log('[useScriptStore]', error);
      set({ error });
      return;
    }

    const dashscopeApiKey = useAppStore.getState().dashscopeApiKey;
    console.log('[useScriptStore] dashscopeApiKey:', dashscopeApiKey ? 'set' : 'not set');

    // Kick off character extraction in parallel with /parse. The store will
    // display characters as soon as the extraction call returns.
    const charPromise = get().extractCharacters(projectId).catch((err) => {
      console.warn('[useScriptStore] extractCharacters pre-step failed (non-fatal):', err);
      return [] as Character[];
    });

    set({ isParsing: true, error: null });
    try {
      console.log('[useScriptStore] Calling scriptService.parseScript...');
      const response = await scriptService.parseScript({
        rawText: rawScript,
        language,
        projectId,
        dashscopeApiKey: dashscopeApiKey || undefined,
      });

      // Make sure character extraction is settled before merging.
      const preChars = await charPromise;

      console.log('[useScriptStore] parseScript response received, parsedScript:', response.scriptData ? 'exists' : 'null');
      const finalChars = response.scriptData?.characters?.length
        ? response.scriptData.characters
        : (preChars.length ? preChars : response.scriptData?.characters || []);

      set({
        normalizedScript: response.normalizedScript,
        parsedScript: response.scriptData
          ? { ...response.scriptData, characters: finalChars }
          : null,
        extractedCharacters: finalChars,
        isParsing: false,
      });
    } catch (err) {
      console.error('[useScriptStore] parseScript error:', err);
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