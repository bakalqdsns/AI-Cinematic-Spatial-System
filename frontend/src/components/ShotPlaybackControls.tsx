/**
 * ShotPlaybackControls — play / pause / stop + speed + progress UI for the
 * current shot's camera animation.
 *
 * Phase 1.3 deliverable (Implementation Plan §1.3.2). Sits next to the
 * 3D viewport (or wherever the host app wants) and forwards the user's
 * transport commands to the Viewer's camera-path animation loop via
 * a callback prop.
 */

import { useEffect, useState, useCallback } from 'react';
import type { CameraMovement } from '../types/script';

export type PlaybackState = 'idle' | 'playing' | 'paused' | 'finished';

export interface ShotPlaybackControlsProps {
  /** Current camera movement — displayed as a label. */
  movement: CameraMovement;
  /** Shot duration in seconds — drives the progress bar. */
  duration: number;
  /** Current playback state — controlled by parent (the Viewer). */
  state: PlaybackState;
  /** Current normalised playback progress in [0, 1]. */
  progress: number;
  /** Speed multiplier (0.5x / 1x / 2x). */
  speed: number;
  /** Called when user clicks play (or un-pauses). */
  onPlay: () => void;
  /** Called when user clicks pause. */
  onPause: () => void;
  /** Called when user clicks stop — resets progress to 0. */
  onStop: () => void;
  /** Called when user picks a new speed multiplier. */
  onSpeedChange: (speed: number) => void;
}

const SPEED_OPTIONS = [0.5, 1.0, 2.0];

export function ShotPlaybackControls({
  movement,
  duration,
  state,
  progress,
  speed,
  onPlay,
  onPause,
  onStop,
  onSpeedChange,
}: ShotPlaybackControlsProps) {
  const [progressPct, setProgressPct] = useState(0);

  // Update progress percentage when prop changes (parent controls).
  useEffect(() => {
    setProgressPct(Math.round(progress * 100));
  }, [progress]);

  const handlePlayPause = useCallback(() => {
    if (state === 'playing') {
      onPause();
    } else {
      onPlay();
    }
  }, [state, onPlay, onPause]);

  const handleProgressClick = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      // Click-to-seek on the progress bar — jump to that point.
      const rect = event.currentTarget.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const ratio = Math.max(0, Math.min(1, x / rect.width));
      // We expose the seek by simulating a "stop → play" cycle with the
      // host is expected to handle. For simplicity, just fire onStop then
      // onPlay — the parent can override the seek semantics if needed.
      // (Real seek support lives in the Viewer.)
      onStop();
      void ratio; // unused — the host decides how to seek
    },
    [onStop],
  );

  const playLabel = state === 'playing' ? 'Pause' : 'Play';
  const playIcon = state === 'playing' ? '⏸' : '▶';

  return (
    <div className="flex flex-col gap-2 p-3 bg-gray-900/80 rounded-lg text-white text-sm">
      {/* Header row: movement label + duration */}
      <div className="flex items-center justify-between">
        <span className="font-semibold text-amber-300">{movement}</span>
        <span className="text-xs text-gray-400">
          {duration.toFixed(1)}s
        </span>
      </div>

      {/* Progress bar */}
      <div
        className="relative h-2 bg-gray-700 rounded cursor-pointer overflow-hidden"
        onClick={handleProgressClick}
        role="slider"
        aria-label="Playback progress"
        aria-valuenow={progressPct}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className="absolute top-0 left-0 h-full bg-amber-500 transition-[width] duration-75"
          style={{ width: `${progressPct}%` }}
        />
      </div>

      {/* Transport controls */}
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={handlePlayPause}
          className="px-3 py-1 bg-amber-600 hover:bg-amber-500 rounded text-white font-semibold transition"
          aria-label={playLabel}
        >
          {playIcon} {playLabel}
        </button>
        <button
          type="button"
          onClick={onStop}
          className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded text-white transition"
          aria-label="Stop"
        >
          ⏹ Stop
        </button>

        <div className="flex-1" />

        {/* Speed selector */}
        <div className="flex items-center gap-1">
          <span className="text-xs text-gray-400">Speed</span>
          {SPEED_OPTIONS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => onSpeedChange(s)}
              className={`px-2 py-0.5 rounded text-xs transition ${
                s === speed
                  ? 'bg-amber-500 text-white font-bold'
                  : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
              aria-label={`${s}x speed`}
              aria-pressed={s === speed}
            >
              {s}x
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

export default ShotPlaybackControls;
