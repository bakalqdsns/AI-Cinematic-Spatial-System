/**
 * Camera Animation — Three.js camera path keyframe generator.
 *
 * Phase 1.3 deliverable (Implementation Plan §1.3.1). Maps the 13
 * `CameraMovement` enum values from `types/script.ts` to Three.js camera
 * keyframe arrays so the Viewer's PerspectiveCamera can interpolate along
 * a path automatically when a shot is selected.
 *
 * Each movement type produces 2 keyframes (start + end). Linear interpolation
 * is used by the Viewer — the spec table in the implementation plan notes
 * that ARC uses a Bézier curve, but Phase 1 ships with linear interpolation
 * for simplicity (matches the existing Viewer3D orbit behaviour).
 *
 * Coordinate convention (matches Blender + Three.js right-handed):
 *   +X = right, +Y = up, +Z = toward camera (so closer layers have -Z)
 */

import * as THREE from 'three';
import type { CameraMovement, ShotSize } from '../types/script';

/**
 * One keyframe in a camera path.
 *
 * `time` is in [0, 1] (0 = start of shot, 1 = end). `position` and
 * `target` are world-space Vector3s. `fov` is the camera vertical FOV
 * in degrees.
 */
export interface CameraKeyframe {
  time: number;
  position: THREE.Vector3;
  target: THREE.Vector3;
  fov: number;
}

/**
 * Base camera position per shot size. These are starting points the
 * movements then perturb. Roughly maps to canonical cinematography
 * distances (in world units, where 1 BU ≈ 1 m):
 *
 *   Extreme Wide   — 30m back
 *   Wide           — 20m back
 *   Medium Wide    — 14m back
 *   Medium Shot    — 10m back
 *   Medium Close   — 6m back
 *   Close-up       — 3m back
 *   Extreme Close  — 1.5m back
 *   OTS / POV / Two-Shot — use medium framing
 */
const BASE_DISTANCE: Record<ShotSize, number> = {
  'Extreme Close-up': 1.5,
  'Close-up': 3.0,
  'Medium Close-up': 5.0,
  'Medium Shot': 8.0,
  'Medium Wide': 12.0,
  'Wide Shot': 16.0,
  'Extreme Wide': 22.0,
  'Over-the-Shoulder': 5.0,
  'POV': 5.0,
  'Two-Shot': 8.0,
};

const BASE_FOV: Record<ShotSize, number> = {
  'Extreme Close-up': 85,
  'Close-up': 65,
  'Medium Close-up': 55,
  'Medium Shot': 45,
  'Medium Wide': 38,
  'Wide Shot': 32,
  'Extreme Wide': 28,
  'Over-the-Shoulder': 55,
  'POV': 60,
  'Two-Shot': 45,
};

/**
 * Generate camera keyframes for a shot.
 *
 * The path always starts at a position derived from the shot size and
 * moves to a movement-specific end position. `duration` (seconds) is
 * unused at the keyframe level — the caller interpolates `time` from 0→1
 * at whatever playback rate they want.
 *
 * @param movement - 13-value `CameraMovement` enum.
 * @param shotSize - 10-value `ShotSize` enum (drives base distance + FOV).
 * @param duration - Shot duration in seconds (informational; not used here).
 */
export function buildCameraPath(
  movement: CameraMovement,
  shotSize: ShotSize,
  duration: number,
): CameraKeyframe[] {
  const startFov = BASE_FOV[shotSize] ?? 45;
  const baseDist = BASE_DISTANCE[shotSize] ?? 8.0;
  const target = new THREE.Vector3(0, 0, 0);

  const start: CameraKeyframe = {
    time: 0,
    position: new THREE.Vector3(0, 0, baseDist),
    target,
    fov: startFov,
  };
  const end: CameraKeyframe = {
    time: 1,
    position: new THREE.Vector3(0, 0, baseDist),
    target,
    fov: startFov,
  };

  switch (movement) {
    case 'Static': {
      // Single keyframe — no movement. The Viewer treats this as a static
      // camera (no interpolation needed).
      return [start];
    }

    case 'Pan Right':
      end.position.set(-baseDist * 0.3, 0, baseDist);
      end.target.set(baseDist * 0.3, 0, 0);
      return [start, end];

    case 'Pan Left':
      end.position.set(baseDist * 0.3, 0, baseDist);
      end.target.set(-baseDist * 0.3, 0, 0);
      return [start, end];

    case 'Tilt Up':
      end.position.set(0, -baseDist * 0.2, baseDist);
      end.target.set(0, baseDist * 0.3, 0);
      return [start, end];

    case 'Tilt Down':
      end.position.set(0, baseDist * 0.2, baseDist);
      end.target.set(0, -baseDist * 0.3, 0);
      return [start, end];

    case 'Dolly In':
      // Move closer (z decreases toward target at origin)
      end.position.set(0, 0, baseDist * 0.5);
      end.fov = startFov + 5;
      return [start, end];

    case 'Dolly Out':
      end.position.set(0, 0, baseDist * 1.5);
      end.fov = Math.max(startFov - 5, 25);
      return [start, end];

    case 'Zoom In':
      // Camera stays put — only FOV changes
      end.fov = Math.min(startFov * 1.5, 90);
      return [start, end];

    case 'Zoom Out':
      end.fov = Math.max(startFov * 0.65, 20);
      return [start, end];

    case 'Tracking':
      // Move horizontally while keeping the target centered
      end.position.set(baseDist * 0.6, 0, baseDist * 0.9);
      return [start, end];

    case 'Crane Up':
      // Arc upward — end position is higher and slightly closer
      end.position.set(0, baseDist * 0.5, baseDist * 0.85);
      return [start, end];

    case 'Crane Down':
      end.position.set(0, -baseDist * 0.3, baseDist * 1.1);
      return [start, end];

    case 'Handheld':
      // Slight drift on both position and FOV for the handheld "shake"
      end.position.set(
        baseDist * 0.08,
        baseDist * 0.05,
        baseDist * (1.0 + 0.05),
      );
      end.fov = startFov + 2;
      return [start, end];

    default: {
      // Defensive fallback — unknown movement (forward-compat).
      return [start];
    }
  }
}

/**
 * Linearly interpolate between two camera keyframes.
 *
 * Used by the Viewer's animation loop to advance the camera each frame.
 * For multi-keyframe paths (Phase 2 will add Bezier arcs) the caller
 * first finds the segment containing the current time then interpolates
 * between that segment's endpoints.
 */
export function interpolateCameraPath(
  kf0: CameraKeyframe,
  kf1: CameraKeyframe,
  t: number,
): { position: THREE.Vector3; target: THREE.Vector3; fov: number } {
  const clamped = Math.max(0, Math.min(1, t));
  const position = new THREE.Vector3().lerpVectors(kf0.position, kf1.position, clamped);
  const target = new THREE.Vector3().lerpVectors(kf0.target, kf1.target, clamped);
  const fov = kf0.fov + (kf1.fov - kf0.fov) * clamped;
  return { position, target, fov };
}

/**
 * Apply a camera keyframe (position + lookAt + FOV) to a Three.js camera.
 *
 * `camera.fov` is in degrees, but Three.js's PerspectiveCamera stores it
 * in degrees too — the conversion to internal units happens during
 * `camera.updateProjectionMatrix()` which we call here so the change
 * is visible immediately.
 */
export function applyCameraKeyframe(
  camera: THREE.PerspectiveCamera,
  kf: CameraKeyframe,
): void {
  camera.position.copy(kf.position);
  camera.lookAt(kf.target);
  if (camera.fov !== kf.fov) {
    camera.fov = kf.fov;
    camera.updateProjectionMatrix();
  }
}
