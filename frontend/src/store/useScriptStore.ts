// ─────────────────────────────────────────────────────────────────────────────
// AICSS Script Store — Zustand
// Manages: raw script input, parsed ScriptData, generated shots, scene
// transitions, character action sequences, character assets, motion sequences.
// ─────────────────────────────────────────────────────────────────────────────
import { create } from 'zustand';
import type {
  ScriptData, Shot, SceneTransition, CharacterActionSequence,
  CharacterAsset, Character, MotionSequence, ScriptLanguage,
  SceneAsset,
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

  // ─── Scene assets (auto-generated keyframe sets per scene) ────────────────
  sceneAssets: Record<string, SceneAsset>;
  isGeneratingSceneAsset: Record<string, boolean>;
  selectedSceneId: string | null;

  // ─── Loading flags ─────────────────────────────────────────────────────────
  isParsing: boolean;
  isGeneratingShots: boolean;
  isGeneratingCharacter: Record<string, boolean>;
  isGeneratingMotion: Record<string, boolean>;

  // ─── UI state ──────────────────────────────────────────────────────────────
  selectedShotId: string | null;
  selectedCharacterId: string | null;
  activeTab: 'script' | 'storyboard' | 'characters' | 'motion';

  // ─── Project context ───────────────────────────────────────────────────────
  projectId: string | null;

  // ─── Error state ───────────────────────────────────────────────────────────
  error: string | null;

  // ─── Actions ───────────────────────────────────────────────────────────────
  setRawScript: (text: string) => void;
  setLanguage: (lang: ScriptLanguage) => void;
  setActiveTab: (tab: ScriptStore['activeTab']) => void;
  selectShot: (shotId: string | null) => void;
  selectCharacter: (charId: string | null) => void;
  setProjectId: (id: string | null) => void;

  parseScript: (projectId?: string) => Promise<void>;
  extractCharacters: (projectId?: string) => Promise<Character[]>;
  generateShots: (projectId?: string) => Promise<void>;

  generateCharacterThreeView: (charId: string, projectId?: string) => Promise<void>;
  generateCharacterVariation: (charId: string, prompt: string, projectId?: string) => Promise<void>;
  updateCharacterVisualPrompt: (charId: string, prompt: string) => void;
  generateSceneAsset: (sceneId: string, location: string, time: string, atmosphere: string, visualPrompt: string, projectId?: string) => Promise<void>;
  selectScene: (sceneId: string | null) => void;

  // Auto-batch: triggered automatically after /parse completes. The backend
  // runs all character three-view generations in parallel; this method polls
  // the progress endpoint and ingests finished CharacterAssets into the store.
  pollAutoThreeView: (projectId: string, charIds: string[]) => Promise<void>;

  // Auto-batch: same idea, but for scene keyframes (wide / closeup / mood).
  pollAutoSceneAsset: (projectId: string, sceneIds: string[]) => Promise<void>;

  generateMotion: (shotId: string, charId: string, projectId?: string) => Promise<void>;

  // ─── Shot mutation (no API call) — keeps shots as the source of truth ──
  updateShot: (shotId: string, updates: Partial<Shot>) => void;

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
  sceneAssets: {} as Record<string, SceneAsset>,
  isParsing: false,
  isGeneratingShots: false,
  isGeneratingCharacter: {} as Record<string, boolean>,
  isGeneratingMotion: {} as Record<string, boolean>,
  isGeneratingSceneAsset: {} as Record<string, boolean>,
  selectedShotId: null as string | null,
  selectedCharacterId: null as string | null,
  selectedSceneId: null as string | null,
  activeTab: 'script' as const,
  projectId: null as string | null,
  error: null as string | null,
};

export const useScriptStore = create<ScriptStore>((set, get) => ({
  ...initialState,

  setRawScript: (text) => set({ rawScript: text, error: null }),
  setLanguage: (lang) => set({ language: lang }),
  setActiveTab: (tab) => set({ activeTab: tab }),
  selectShot: (shotId) => set({ selectedShotId: shotId }),
  selectCharacter: (charId) => set({ selectedCharacterId: charId }),
  selectScene: (sceneId) => set({ selectedSceneId: sceneId }),
  setProjectId: (id) => set({ projectId: id }),

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

      // Ensure we have a projectId for persistence (generate one if not provided)
      const resolvedProjectId = projectId || crypto.randomUUID();

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
        projectId: resolvedProjectId,
        isParsing: false,
      });

      // Auto-batch: kick off three-view generation for every detected
      // character (fire-and-forget on the backend). Poll status to update
      // characterAssets as they complete.
      if (resolvedProjectId && finalChars.length) {
        get().pollAutoThreeView(resolvedProjectId, finalChars.map(c => c.id));
      }

      // Auto-batch: scenes → keyframes (wide / closeup / mood).
      if (resolvedProjectId && response.scriptData?.scenes?.length) {
        get().pollAutoSceneAsset(
          resolvedProjectId,
          response.scriptData.scenes.map(s => s.id),
        );
      }
    } catch (err) {
      console.error('[useScriptStore] parseScript error:', err);
      set({
        isParsing: false,
        error: err instanceof Error ? err.message : 'Script parsing failed',
      });
    }
  },

  // ─── Auto three-view: poll backend status, ingest finished assets ──────────
  pollAutoThreeView: async (projectId, charIds) => {
    if (!projectId || !charIds?.length) return;
    console.log('[useScriptStore] pollAutoThreeView start', { projectId, n: charIds.length });

    // Mark all characters as initially "queued" so the UI can show pending badges.
    set(state => {
      const isGen = { ...state.isGeneratingCharacter };
      charIds.forEach(id => { isGen[id] = true; });
      return { isGeneratingCharacter: isGen };
    });

    // Generous timeout: Z-Image-Turbo + LLM prompt generation can take 20+ min
    // per character. 30 min gives enough headroom for all characters in a scene.
    const TIMEOUT_MS = 30 * 60 * 1000;
    const INITIAL_INTERVAL_MS = 4000;
    const MAX_INTERVAL_MS = 30000;
    const deadline = Date.now() + TIMEOUT_MS;
    let pollInterval = INITIAL_INTERVAL_MS;

    let stopped = false;
    const stop = () => { stopped = true; };

    while (!stopped && Date.now() < deadline) {
      try {
        const status = await scriptService.getBatchStatus(projectId);
        const { characters: chMap, summary } = status;

        // Ingest any newly-finished assets.
        const newAssets: Record<string, CharacterAsset> = {};
        const stillRunning: string[] = [];
        for (const id of charIds) {
          const entry = chMap[id];
          if (!entry) continue;
          if (entry.status === 'done' && entry.asset) {
            const a = entry.asset as unknown as CharacterAsset;
            newAssets[id] = {
              characterId: id,
              visualPrompt: a.visual_prompt || a.visualPrompt || entry.visual_prompt || '',
              referenceImage: a.reference_image || a.referenceImage,
              threeViewImages: a.three_view_images || a.threeViewImages || {},
              variations: a.variations || [],
            };
          } else if (entry.status === 'queued' || entry.status === 'running') {
            stillRunning.push(id);
          }
          // 'failed' falls through — leave isGeneratingCharacter[id] = false below.
        }

        if (Object.keys(newAssets).length) {
          set(state => ({
            characterAssets: { ...state.characterAssets, ...newAssets },
          }));
        }

        // Clear isGeneratingCharacter for finished/failed characters.
        const finishedIds = charIds.filter(id => {
          const e = chMap[id];
          return e && (e.status === 'done' || e.status === 'failed');
        });
        if (finishedIds.length) {
          set(state => {
            const isGen = { ...state.isGeneratingCharacter };
            finishedIds.forEach(id => { isGen[id] = false; });
            return { isGeneratingCharacter: isGen };
          });
        }

        // Stop polling when everything is settled.
        if (stillRunning.length === 0) {
          console.log('[useScriptStore] pollAutoThreeView all settled', summary);
          break;
        }
      } catch (err) {
        console.warn('[useScriptStore] getBatchStatus failed:', err);
        // On error, back off as well to avoid hammering a failing endpoint
        pollInterval = Math.min(pollInterval * 1.5, MAX_INTERVAL_MS);
      }
      // Exponential backoff: 4s → 6s → 9s → ... → 30s max
      pollInterval = Math.min(pollInterval * 1.5, MAX_INTERVAL_MS);
      await new Promise(r => setTimeout(r, pollInterval));
    }

    // Final cleanup: make sure no character is stuck in "generating" state.
    set(state => {
      const isGen = { ...state.isGeneratingCharacter };
      charIds.forEach(id => { isGen[id] = false; });
      return { isGeneratingCharacter: isGen };
    });
    void stop;
  },

  // ─── Auto scene keyframes: poll backend status, ingest finished assets ─────
  pollAutoSceneAsset: async (projectId, sceneIds) => {
    if (!projectId || !sceneIds?.length) return;
    console.log('[useScriptStore] pollAutoSceneAsset start', { projectId, n: sceneIds.length });

    set(state => {
      const isGen = { ...state.isGeneratingSceneAsset };
      sceneIds.forEach(id => { isGen[id] = true; });
      return { isGeneratingSceneAsset: isGen };
    });

    // Generous timeout: scene keyframe generation involves LLM + image synthesis.
    const TIMEOUT_MS = 30 * 60 * 1000;
    const INITIAL_INTERVAL_MS = 4000;
    const MAX_INTERVAL_MS = 30000;
    const deadline = Date.now() + TIMEOUT_MS;
    let pollInterval = INITIAL_INTERVAL_MS;
    let stopped = false;

    while (!stopped && Date.now() < deadline) {
      try {
        const status = await scriptService.getSceneBatchStatus(projectId);
        const { scenes: sceneMap, summary } = status;

        const newAssets: Record<string, SceneAsset> = {};
        const stillRunning: string[] = [];
        for (const id of sceneIds) {
          const entry = sceneMap[id];
          if (!entry) continue;
          if (entry.status === 'done' && entry.asset) {
            const a = entry.asset as unknown as SceneAsset;
            newAssets[id] = {
              sceneId: id,
              visualPrompt: a.visual_prompt || a.visualPrompt || entry.visual_prompt || '',
              keyframeImages: a.keyframe_images || a.keyframeImages || {},
              variations: a.variations || [],
            };
          } else if (entry.status === 'queued' || entry.status === 'running') {
            stillRunning.push(id);
          }
        }

        if (Object.keys(newAssets).length) {
          set(state => ({
            sceneAssets: { ...state.sceneAssets, ...newAssets },
          }));
        }

        const finishedIds = sceneIds.filter(id => {
          const e = sceneMap[id];
          return e && (e.status === 'done' || e.status === 'failed');
        });
        if (finishedIds.length) {
          set(state => {
            const isGen = { ...state.isGeneratingSceneAsset };
            finishedIds.forEach(id => { isGen[id] = false; });
            return { isGeneratingSceneAsset: isGen };
          });
        }

        if (stillRunning.length === 0) {
          console.log('[useScriptStore] pollAutoSceneAsset all settled', summary);
          break;
        }
      } catch (err) {
        console.warn('[useScriptStore] getSceneBatchStatus failed:', err);
        pollInterval = Math.min(pollInterval * 1.5, MAX_INTERVAL_MS);
      }
      pollInterval = Math.min(pollInterval * 1.5, MAX_INTERVAL_MS);
      await new Promise(r => setTimeout(r, pollInterval));
    }

    set(state => {
      const isGen = { ...state.isGeneratingSceneAsset };
      sceneIds.forEach(id => { isGen[id] = false; });
      return { isGeneratingSceneAsset: isGen };
    });
    void stopped;
  },

  // ─── Pass 3: derive per-scene shots + transitions + character sequences ───
  generateShots: async (projectId) => {
    const { parsedScript, projectId: storedProjectId } = get();
    if (!parsedScript) {
      set({ error: 'Please parse the script first' });
      return;
    }
    // Prefer explicitly passed projectId, fall back to stored
    const resolvedProjectId = projectId || storedProjectId;

    set({ isGeneratingShots: true, error: null });
    try {
      const response = await scriptService.generateShots({
        scriptData: parsedScript,
        shotsPerScene: 6,
        language: parsedScript.language,
        projectId: resolvedProjectId,
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

  // ─── Scene keyframe generation ──────────────────────────────────────────────
  generateSceneAsset: async (sceneId, location, time, atmosphere, visualPrompt, projectId) => {
    set(state => ({
      isGeneratingSceneAsset: { ...state.isGeneratingSceneAsset, [sceneId]: true },
    }));
    try {
      const asset = await scriptService.generateSceneAsset({
        sceneId,
        location,
        time,
        atmosphere,
        visualPrompt,
        projectId,
      });
      set(state => ({
        sceneAssets: { ...state.sceneAssets, [sceneId]: asset },
        isGeneratingSceneAsset: { ...state.isGeneratingSceneAsset, [sceneId]: false },
      }));
    } catch (err) {
      console.error('[useScriptStore] generateSceneAsset error:', err);
      set(state => ({
        isGeneratingSceneAsset: { ...state.isGeneratingSceneAsset, [sceneId]: false },
        error: err instanceof Error ? err.message : 'Scene keyframe generation failed',
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

  // ─── Local mutation (no API call) — keeps shots as the source of truth
  updateShot: (shotId, updates) => {
    set(state => ({
      shots: state.shots.map(s =>
        s.id === shotId ? { ...s, ...updates } : s,
      ),
    }));
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