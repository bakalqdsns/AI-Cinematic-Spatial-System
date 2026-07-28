// ─────────────────────────────────────────────────────────────────────────────
// Depth utilities — sampling, layer assignment, Z-position calculation
// Used by: PolygonDrawTool, SplitControls (inpaint), Viewer3D (Z layout)
// ─────────────────────────────────────────────────────────────────────────────
import type { DepthLayerKey, LayerRegion, PolygonPoint } from '../types';
import { DEPTH_LAYER_THRESHOLDS, DEPTH_LAYER_Z } from '../types';

// ─── Depth map loading ─────────────────────────────────────────────────────

/**
 * Load a depth map URL as an ImageData object.
 * The depth map is a grayscale PNG (brightness = distance: white=near, black=far).
 */
export async function loadDepthMapImageData(
  depthMapUrl: string,
): Promise<ImageData> {
  const img = new Image();
  img.crossOrigin = 'anonymous';
  await new Promise<void>((resolve, reject) => {
    img.onload = () => resolve();
    img.onerror = () => reject(new Error(`Failed to load depth map: ${depthMapUrl.slice(0, 64)}`));
    img.src = depthMapUrl;
  });

  const canvas = document.createElement('canvas');
  canvas.width = img.naturalWidth;
  canvas.height = img.naturalHeight;
  const ctx = canvas.getContext('2d')!;
  ctx.drawImage(img, 0, 0);
  return ctx.getImageData(0, 0, canvas.width, canvas.height);
}

// ─── Geometry helpers ──────────────────────────────────────────────────────

/**
 * Ray-casting point-in-polygon test.
 * Returns true if the normalized point (px, py) lies inside the polygon.
 */
export function isPointInPolygon(
  px: number,
  py: number,
  polygon: PolygonPoint[],
): boolean {
  let inside = false;
  const n = polygon.length;
  for (let i = 0, j = n - 1; i < n; j = i++) {
    const [xi, yi] = polygon[i];
    const [xj, yj] = polygon[j];
    const intersect =
      yi > py !== yj > py &&
      px < ((xj - xi) * (py - yi)) / (yj - yi) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

// ─── Depth sampling ────────────────────────────────────────────────────────

/**
 * Sample the median depth value of all pixels inside a polygon.
 * depthMapData: raw ImageData from loadDepthMapImageData
 * imageWidth, imageHeight: dimensions of the original image (for coordinate conversion)
 *
 * Returns a value in [0, 255] — the median brightness of polygon pixels.
 * A higher value = the region is closer to the camera (foreground).
 */
export function sampleDepthAtPolygon(
  depthMapData: ImageData,
  polygon: PolygonPoint[],
  imageWidth: number,
  imageHeight: number,
): number {
  if (polygon.length < 3) return 128;

  const samples: number[] = [];
  const { data, width, height } = depthMapData;

  for (let py = 0; py < height; py++) {
    for (let px = 0; px < width; px++) {
      if (!isPointInPolygon(px / width, py / height, polygon)) continue;
      const idx = (py * width + px) * 4;
      samples.push(data[idx]); // R channel (all channels equal in grayscale)
    }
  }

  if (samples.length === 0) return 128;
  samples.sort((a, b) => a - b);
  return samples[Math.floor(samples.length / 2)];
}

// ─── Layer assignment ─────────────────────────────────────────────────────

/**
 * Map a depth brightness value (0-255) to a DepthLayerKey.
 * Uses the same thresholds as depthSplit.ts / DEPTH_LAYER_THRESHOLDS.
 */
export function autoAssignDepthLayer(brightness: number): DepthLayerKey {
  if (brightness >= DEPTH_LAYER_THRESHOLDS.foreground) return 'foreground';
  if (brightness >= DEPTH_LAYER_THRESHOLDS.midground) return 'midground';
  if (brightness >= DEPTH_LAYER_THRESHOLDS.background) return 'background';
  return 'sky';
}

// ─── Z-position calculation ────────────────────────────────────────────────

/**
 * Fine-grained Z offset within a depth layer.
 * Sub-pixel depth variation within the same layer gives a smooth depth gradient.
 */
const Z_PER_DEPTH_VALUE = 0.02; // 1 brightness step ≈ 0.02 world units

/**
 * Compute the world-space Z position for a LayerRegion.
 * Combines the coarse DEPTH_LAYER_Z offset with fine-grained depth value.
 */
export function zForRegion(region: LayerRegion): number {
  const base = DEPTH_LAYER_Z[region.depthLayer] ?? 0;
  const depthValue = region.depthValue ?? 128;
  // depthValue 128 = neutral, scale from there
  const normalized = (depthValue - 128) / 128; // -1 to +1
  return base + normalized * Z_PER_DEPTH_VALUE * 64;
}

/**
 * Sort regions from far to near (painter's algorithm: far first, near last).
 */
export function sortRegionsByDepth(regions: LayerRegion[]): LayerRegion[] {
  return [...regions].sort((a, b) => zForRegion(a) - zForRegion(b));
}
