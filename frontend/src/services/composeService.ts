// ─────────────────────────────────────────────────────────────────────────────
// AICSS Compose Service — v2 API client for the FFmpeg video composition
// pipeline (Module 11, T01/T02/T04/T05).
//
// Thin wrapper around the generated OpenAPI client (`generated/v2Compose`).
// The backend `ComposeRequest` Pydantic model uses **camelCase** for the
// top-level fields (`clipPaths`, `transitionDuration`, `audioTracks`,
// `colorGrade`), but its nested `AudioTrack` / `ColorGrade` models use
// snake_case for some fields:
//   - `AudioTrack.kind`        (frontend `type`, with `voice` → `voiceover`)
//   - `AudioTrack.start_at`    (frontend `startSeconds`)
//   - `ColorGrade.lut_path`    (frontend `lutPath`)
// The wrappers below convert the frontend camelCase types to the backend wire
// shape at the API boundary so the rest of the frontend can use idiomatic
// camelCase. `outputPathToPlaybackUrl` stays a pure URL builder (no HTTP).
// ─────────────────────────────────────────────────────────────────────────────
import { generatedClient, DEFAULT_BACKEND } from './generatedClient';

// ─── Frontend (camelCase) types ──────────────────────────────────────────────

export type TransitionKind = 'cut' | 'dissolve' | 'fade' | 'wipe';

export type AudioTrackType = 'bgm' | 'sfx' | 'voice';

export interface AudioTrack {
  /** Frontend-only stable id (for React keys / store ops). Not sent to backend. */
  id: string;
  type: AudioTrackType;
  path: string;
  /** Seconds offset into the final timeline where this track begins. */
  startSeconds: number;
  /** Volume multiplier (0–2, 1.0 = unity). */
  volume: number;
}

export interface ColorGrade {
  /** Path to a .cube LUT file. Optional. */
  lutPath?: string;
  /** eq brightness (-1..1). */
  brightness?: number;
  /** eq contrast (0..10, 1.0 = unity). */
  contrast?: number;
  /** eq saturation (0..3, 1.0 = unity). */
  saturation?: number;
}

export interface ComposeRequest {
  clipPaths: string[];
  durations: number[];
  transition: TransitionKind;
  transitionDuration: number;
  audioTracks: AudioTrack[] | null;
  colorGrade: ColorGrade | null;
}

export interface ComposeResponse {
  outputPath: string;
  durationSeconds: number;
  format: string;
}

// ─── Backend (wire) types ─────────────────────────────────────────────────────

type BackendAudioKind = 'bgm' | 'sfx' | 'voiceover';

interface BackendAudioTrack {
  kind: BackendAudioKind;
  path: string;
  volume: number;
  start_at: number;
}

interface BackendColorGrade {
  lut_path?: string | null;
  brightness?: number;
  contrast?: number;
  saturation?: number;
}

interface BackendComposeRequest {
  clipPaths: string[];
  durations: number[];
  transition: TransitionKind;
  transitionDuration: number;
  audioTracks?: BackendAudioTrack[] | null;
  colorGrade?: BackendColorGrade | null;
}

interface BackendComposeResponse {
  outputPath: string;
  durationSeconds: number;
  format: string;
}

// ─── Conversion helpers ───────────────────────────────────────────────────────

function toBackendAudioKind(type: AudioTrackType): BackendAudioKind {
  // Frontend uses `voice` for the voiceover track; backend uses `voiceover`.
  return type === 'voice' ? 'voiceover' : type;
}

function toBackendAudioTrack(track: AudioTrack): BackendAudioTrack {
  return {
    kind: toBackendAudioKind(track.type),
    path: track.path,
    volume: track.volume,
    start_at: track.startSeconds,
  };
}

function toBackendColorGrade(grade: ColorGrade | null): BackendColorGrade | null {
  if (!grade) return null;
  return {
    lut_path: grade.lutPath ?? null,
    brightness: grade.brightness ?? 0,
    contrast: grade.contrast ?? 1,
    saturation: grade.saturation ?? 1,
  };
}

function toBackendRequest(req: ComposeRequest): BackendComposeRequest {
  return {
    clipPaths: req.clipPaths,
    durations: req.durations,
    transition: req.transition,
    transitionDuration: req.transitionDuration,
    audioTracks: req.audioTracks ? req.audioTracks.map(toBackendAudioTrack) : null,
    colorGrade: toBackendColorGrade(req.colorGrade),
  };
}

// ─── Public API ──────────────────────────────────────────────────────────────

/**
 * Call `POST /api/aicss/v2/projects/{project_id}/compose`.
 *
 * The backend currently returns synchronously (no job id / polling endpoint
 * yet), so this promise resolves when the composed MP4 is ready. The caller
 * should drive a UI loading state independently while awaiting.
 */
export async function compose(
  projectId: string,
  req: ComposeRequest,
): Promise<ComposeResponse> {
  const body = toBackendRequest(req);
  const data = await generatedClient.v2Compose.apiComposeApiAicssV2ProjectsProjectIdComposePost({
    projectId,
    requestBody: body as any,
  }) as BackendComposeResponse;
  return {
    outputPath: data.outputPath,
    durationSeconds: data.durationSeconds,
    format: data.format,
  };
}

/**
 * Convert a backend `outputPath` (absolute filesystem path returned by
 * `POST /compose`) into a playback URL that the `<video>` tag can stream.
 *
 * The backend exposes `GET /api/aicss/v2/projects/{pid}/compose/{filename}`
 * (a `FileResponse` endpoint added alongside the compose pipeline) which
 * streams the MP4 with the correct `video/mp4` MIME type and supports HTTP
 * Range requests for seeking.
 *
 * This helper strips the directory portion of `outputPath` and rebuilds the
 * URL against the same backend origin used by `compose()`. Works on both
 * POSIX (`/`) and Windows (`\`) path separators.
 */
export function outputPathToPlaybackUrl(
  outputPath: string,
  projectId: string,
): string {
  const filename = outputPath.split(/[\\/]/).pop();
  if (!filename) {
    throw new Error(`Invalid outputPath: ${outputPath}`);
  }
  return `${DEFAULT_BACKEND}/api/aicss/v2/projects/${projectId}/compose/${filename}`;
}
