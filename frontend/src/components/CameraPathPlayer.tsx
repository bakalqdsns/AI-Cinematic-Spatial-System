/**
 * CameraPathPlayer — drives the Three.js PerspectiveCamera along the
 * keyframe path emitted by `utils/cameraAnimation.buildCameraPath`.
 *
 * Phase 1.3 deliverable (Implementation Plan §1.3.3). The component is
 * rendered as a child inside the Viewer's <Canvas> tree (uses `useThree`)
 * and consumes a `Shot | null` prop. When `shot` changes, a new path is
 * built and the camera animates from the start keyframe to the end at
 * the requested speed.
 *
 * The host app passes the `state`, `progress`, `speed` props down to a
 * `ShotPlaybackControls` UI element so users can pause / scrub.
 *
 * Design notes:
 *   - We DO NOT use GSAP. A simple rAF loop with linear interpolation is
 *     enough for Phase 1 (per the implementation plan, GSAP is optional).
 *   - When `shot` is null the camera is left untouched (so manual orbit
 *     controls keep working).
 *   - On shot switch, we snap to the start keyframe immediately — no
 *     cross-shot interpolation (the StoryboardTab UI handles shot-level
 *     transitions).
 */

import { useEffect, useRef } from 'react';
import { useThree, useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import type { Shot } from '../types/script';
import {
  buildCameraPath,
  interpolateCameraPath,
  applyCameraKeyframe,
  type CameraKeyframe,
} from '../utils/cameraAnimation';
import type { PlaybackState } from './ShotPlaybackControls';

export interface CameraPathPlayerProps {
  shot: Shot | null;
  state: PlaybackState;
  speed: number;
  /** Called on every progress update (used by ShotPlaybackControls). */
  onProgress?: (progress: number) => void;
  /** Called when the playback finishes naturally (state → finished). */
  onFinish?: () => void;
}

export function CameraPathPlayer({
  shot,
  state,
  speed,
  onProgress,
  onFinish,
}: CameraPathPlayerProps) {
  const { camera } = useThree();

  // Path + playback bookkeeping. We store these in refs so the rAF loop
  // can read them without forcing React re-renders every frame.
  const pathRef = useRef<CameraKeyframe[]>([]);
  const tRef = useRef(0);                    // normalised time [0, 1]
  const startedAtRef = useRef<number | null>(null);
  const lastReportedTRef = useRef(-1);

  // ── Build a new path whenever the shot changes ──────────────────────────
  useEffect(() => {
    if (!shot) {
      pathRef.current = [];
      tRef.current = 0;
      startedAtRef.current = null;
      return;
    }
    const newPath = buildCameraPath(
      shot.cameraMovement,
      shot.shotSize,
      shot.durationSeconds,
    );
    pathRef.current = newPath;
    tRef.current = 0;
    startedAtRef.current = null;

    // Snap camera to start keyframe
    if (newPath.length > 0) {
      applyCameraKeyframe(camera as THREE.PerspectiveCamera, newPath[0]);
    }
  }, [shot, camera]);

  // ── Reset the start time when state transitions to 'playing' ────────────
  useEffect(() => {
    if (state === 'playing') {
      startedAtRef.current = null;  // re-stamp on next frame
    } else if (state === 'idle' || state === 'finished') {
      tRef.current = 0;
      if (pathRef.current.length > 0) {
        applyCameraKeyframe(
          camera as THREE.PerspectiveCamera,
          pathRef.current[0],
        );
      }
      onProgress?.(0);
    }
  }, [state, camera, onProgress]);

  // ── Animation loop ──────────────────────────────────────────────────────
  useFrame((_, deltaSeconds) => {
    if (state !== 'playing') return;
    const path = pathRef.current;
    if (path.length === 0) return;

    // First frame: stamp the start time so progress is monotonic.
    if (startedAtRef.current === null) {
      startedAtRef.current = performance.now();
    }

    // Compute normalised t from elapsed wall time + speed multiplier
    const duration = shot ? shot.durationSeconds : 3.0;
    const elapsed = (performance.now() - startedAtRef.current) / 1000.0;
    const effectiveDuration = duration / Math.max(speed, 0.001);
    const t = Math.min(1, elapsed / effectiveDuration);

    tRef.current = t;

    // Interpolate. For paths with >2 keyframes (Phase 2) we'd pick the
    // segment here; Phase 1 only uses start + end so interpolation is direct.
    if (path.length === 1) {
      // Static shot — keep applying the single keyframe (no movement).
      applyCameraKeyframe(camera as THREE.PerspectiveCamera, path[0]);
    } else {
      const { position, target, fov } = interpolateCameraPath(
        path[0],
        path[path.length - 1],
        t,
      );
      const cam = camera as THREE.PerspectiveCamera;
      cam.position.copy(position);
      cam.lookAt(target);
      if (Math.abs(cam.fov - fov) > 0.01) {
        cam.fov = fov;
        cam.updateProjectionMatrix();
      }
    }

    // Throttle progress callback — only fire when the percentage changes
    const pct = Math.round(t * 100);
    if (pct !== lastReportedTRef.current) {
      lastReportedTRef.current = pct;
      onProgress?.(t);
    }

    if (t >= 1.0) {
      onFinish?.();
    }
  });

  return null;
}

export default CameraPathPlayer;
