// ─────────────────────────────────────────────────────────────────────────────
// AICSS Timeline Store — Zustand
// Manages the multi-track timeline state for the compose pipeline (T03):
//   - video track: ordered list of ShotClips (drag to reorder)
//   - audio tracks: BGM / SFX / voiceover layered on top
//   - transition kind + duration applied between adjacent clips
//   - compose progress + output URL
//
// The compose action calls `composeService.compose(projectId, ...)` and stores
// the returned `outputPath` as `outputUrl`. The backend currently returns
// synchronously, so we use a simple `isComposing` flag + a faux progress bar
// driver; when the backend adds a job/poll endpoint later, swap the body of
// `compose` for a real polling loop without touching the rest of the UI.
// ─────────────────────────────────────────────────────────────────────────────
import { create } from 'zustand';
import type { Shot } from '../types/script';
import {
  compose as composeApi,
  outputPathToPlaybackUrl,
  type AudioTrack,
  type ColorGrade,
  type ComposeRequest,
  type ComposeResponse,
  type TransitionKind,
} from '../services/composeService';

export type { AudioTrack, ColorGrade, TransitionKind } from '../services/composeService';

export interface ShotClip {
  /** Stable frontend id (not the backend shot id). */
  id: string;
  /** Backend shot id this clip refers to. */
  shotId: string;
  /** Absolute path to the source MP4 for this shot. */
  clipPath: string;
  /** Duration in seconds. */
  durationSec: number;
  /** Short label for the card (e.g. "S01 / Dolly In"). */
  label: string;
  /** Optional per-clip incoming transition override (defaults to global). */
  transitionIn?: TransitionKind;
}

interface TimelineState {
  // ─── Tracks ──────────────────────────────────────────────────────────────────
  tracks: ShotClip[];
  audioTracks: AudioTrack[];

  // ─── Global transition settings ─────────────────────────────────────────────
  transition: TransitionKind;
  transitionDuration: number;

  // ─── Selection ───────────────────────────────────────────────────────────────
  selectedClipId: string | null;

  // ─── Compose state ────────────────────────────────────────────────────────────
  isComposing: boolean;
  /** 0..1 progress for the loading bar. */
  composeProgress: number;
  outputUrl: string | null;
  lastComposeResponse: ComposeResponse | null;
  error: string | null;

  // ─── Actions ─────────────────────────────────────────────────────────────────
  setTracks: (clips: ShotClip[]) => void;
  /** Build tracks from `useScriptStore.shots` (idempotent). */
  setTracksFromShots: (shots: Shot[], clipPathFor?: (shot: Shot) => string) => void;
  moveClip: (fromIdx: number, toIdx: number) => void;
  removeClip: (id: string) => void;
  setTransition: (kind: TransitionKind) => void;
  setTransitionDuration: (sec: number) => void;
  addAudioTrack: (track: AudioTrack) => void;
  removeAudioTrack: (id: string) => void;
  setSelectedClip: (id: string | null) => void;
  compose: (projectId: string, colorGrade?: ColorGrade | null) => Promise<void>;
  reset: () => void;
}

const initialState = {
  tracks: [] as ShotClip[],
  audioTracks: [] as AudioTrack[],
  transition: 'cut' as TransitionKind,
  transitionDuration: 0.5,
  selectedClipId: null as string | null,
  isComposing: false,
  composeProgress: 0,
  outputUrl: null as string | null,
  lastComposeResponse: null as ComposeResponse | null,
  error: null as string | null,
};

let _clipIdCounter = 0;
function nextClipId(): string {
  _clipIdCounter += 1;
  return `clip_${Date.now().toString(36)}_${_clipIdCounter}`;
}

let _audioIdCounter = 0;
function nextAudioId(): string {
  _audioIdCounter += 1;
  return `aud_${Date.now().toString(36)}_${_audioIdCounter}`;
}

/** Default clip path resolver: placeholder that points at a per-shot render. */
function defaultClipPath(shot: Shot): string {
  // The real clip path comes from the render-queue output (T07) or the shot
  // archive. Until that's wired in, we emit a conventional placeholder so the
  // compose call shape is correct; the backend will reject with 500 if the
  // file is missing — which is the expected behaviour during integration.
  return `projects/<project_id>/renders/${shot.id}.mp4`;
}

export const useTimelineStore = create<TimelineState>((set, get) => ({
  ...initialState,

  setTracks: (clips) => set({ tracks: clips }),

  setTracksFromShots: (shots, clipPathFor) => {
    const resolver = clipPathFor ?? defaultClipPath;
    const clips: ShotClip[] = shots.map((s, idx) => ({
      id: `clip_${s.id}_${idx}`,
      shotId: s.id,
      clipPath: resolver(s),
      durationSec: s.durationSeconds,
      label: `S${String(s.shotNumber).padStart(2, '0')} · ${s.cameraMovement}`,
    }));
    set({ tracks: clips });
  },

  moveClip: (fromIdx, toIdx) => {
    const { tracks } = get();
    if (
      fromIdx === toIdx ||
      fromIdx < 0 || fromIdx >= tracks.length ||
      toIdx < 0 || toIdx >= tracks.length
    ) {
      return;
    }
    const next = tracks.slice();
    const [moved] = next.splice(fromIdx, 1);
    next.splice(toIdx, 0, moved);
    set({ tracks: next });
  },

  removeClip: (id) => {
    const { tracks, selectedClipId } = get();
    set({
      tracks: tracks.filter((c) => c.id !== id),
      selectedClipId: selectedClipId === id ? null : selectedClipId,
    });
  },

  setTransition: (kind) => set({ transition: kind }),
  setTransitionDuration: (sec) =>
    set({ transitionDuration: Math.max(0, Math.min(5, sec)) }),

  addAudioTrack: (track) => {
    const withId: AudioTrack = { ...track, id: track.id || nextAudioId() };
    set({ audioTracks: [...get().audioTracks, withId] });
  },

  removeAudioTrack: (id) =>
    set({ audioTracks: get().audioTracks.filter((t) => t.id !== id) }),

  setSelectedClip: (id) => set({ selectedClipId: id }),

  compose: async (projectId, colorGrade = null) => {
    const { tracks, audioTracks, transition, transitionDuration } = get();
    if (tracks.length === 0) {
      set({ error: 'No clips on the timeline to compose.' });
      return;
    }
    if (!projectId) {
      set({ error: 'Missing project id.' });
      return;
    }

    set({
      isComposing: true,
      composeProgress: 0,
      error: null,
      outputUrl: null,
      lastComposeResponse: null,
    });

    // Faux progress driver: the backend is synchronous, so we tick the bar
    // gently while the request is in flight so the user sees a loading state.
    let tick = 0;
    const interval = window.setInterval(() => {
      tick += 1;
      // Asymptotically approach 90% while waiting — never reaches 100 until
      // the response arrives.
      const next = Math.min(0.9, 0.1 + tick * 0.03);
      set({ composeProgress: next });
    }, 300);

    try {
      const req: ComposeRequest = {
        clipPaths: tracks.map((c) => c.clipPath),
        durations: tracks.map((c) => c.durationSec),
        transition,
        transitionDuration,
        audioTracks: audioTracks.length > 0 ? audioTracks : null,
        colorGrade,
      };
      const resp = await composeApi(projectId, req);
      set({
        isComposing: false,
        composeProgress: 1,
        outputUrl: outputPathToPlaybackUrl(resp.outputPath, projectId),
        lastComposeResponse: resp,
      });
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : typeof err === 'string'
            ? err
            : 'Compose failed';
      set({
        isComposing: false,
        composeProgress: 0,
        error: message,
      });
    } finally {
      window.clearInterval(interval);
    }
  },

  reset: () => set({ ...initialState }),
}));

// Re-export id generators for components that build tracks imperatively.
export { nextClipId, nextAudioId };
