// ─────────────────────────────────────────────────────────────────────────────
// Occlusion-aware inpaint mask generation
//
// Mask semantics (consistent with LaMa/backend API):
//   - alpha=255 (white)  → area to be inpainted (LaMa fills this)
//   - alpha=0   (black)  → keep area (preserve original pixels)
//
// Strategy:
//   1. White background = everything is a potential inpaint target
//   2. Draw all "closer than target" regions in black → these always preserve
//   3. Within the target polygon's interior pixels, compare depth:
//      - pixels that are deeper (darker in depth map) = behind foreground → inpaint
//      - pixels that are at foreground depth = part of the target object → keep
//      → This is the key: "inpaint the occluded parts, keep the occluder shape"
//
// Used by: SplitControls (handleSplitAndInpaint)
// ─────────────────────────────────────────────────────────────────────────────
import type { LayerRegion, DepthLayerKey, PolygonPoint } from '../types';
import { DEPTH_LAYER_THRESHOLDS } from '../types';
import { isPointInPolygon } from './depthUtils';

// Depth threshold margin for "same foreground depth" comparison.
// Pixels within ±MARGIN of the target depth are considered part of the target.
const DEPTH_MARGIN = 8; // brightness steps (~8/255 ≈ 3% of range)

const LAYER_DEPTH_RANK: Record<DepthLayerKey, number> = {
  sky: 0,
  background: 1,
  midground: 2,
  foreground: 3,
};

/**
 * Build a binary polygon mask (Uint8Array, 0=outside, 255=inside).
 * Returns a flat array of alpha values indexed by pixel offset.
 */
function buildPolygonMask(
  polygon: PolygonPoint[],
  width: number,
  height: number,
): Uint8Array {
  const mask = new Uint8Array(width * height);
  for (let py = 0; py < height; py++) {
    for (let px = 0; px < width; px++) {
      if (isPointInPolygon(px / width, py / height, polygon)) {
        mask[py * width + px] = 255;
      }
    }
  }
  return mask;
}

/**
 * Compute a mask that keeps the target object's shape
 * and inpaint only the occluded pixels behind it.
 *
 * regions: all regions, sorted from far to near (painter's order)
 * targetRegion: the region to inpaint (its occluded interior only)
 * depthMapData: raw ImageData from depthMapUrl (grayscale: brightness = depth)
 *
 * Returns an RGBA PNG data URL where:
 *   - alpha=255 → LaMa should fill (the occluded interior of target)
 *   - alpha=0   → preserve original image
 */
export function computeOcclusionAwareMask(
  targetRegion: LayerRegion,
  depthMapData: ImageData,
  imageWidth: number,
  imageHeight: number,
): string {
  const { data: depthData, width: dw, height: dh } = depthMapData;
  const polygon = targetRegion.polygon;

  // Build the target polygon mask at full resolution
  const polyMask = buildPolygonMask(polygon, dw, dh);

  // Median depth inside the polygon (reference for "the depth of this layer").
  const polygonDepths: number[] = [];
  for (let i = 0; i < polyMask.length; i++) {
    if (polyMask[i] === 0) continue;
    const d = depthData[i * 4]; // R channel
    polygonDepths.push(d);
  }
  polygonDepths.sort((a, b) => a - b);
  const medianDepth =
    polygonDepths.length > 0
      ? polygonDepths[Math.floor(polygonDepths.length / 2)]
      : 128;

  // Use DepthLayer of the target to determine the foreground depth band.
  // Pixels whose depth falls into [layerLow, 255] are considered "this layer
  // (or closer than it)" and are kept. Pixels in the polygon interior that
  // are deeper than this layer (i.e., behind it) are occluded and should be
  // inpainted.
  //
  // This is the correct semantics for the "peel a foreground layer off the
  // image" workflow:
  //   - Strip a foreground polygon → keep the foreground object, inpaint the
  //     pixels behind it that were occluded.
  //   - Strip a background polygon → keep the background, inpaint any closer
  //     pixels inside the polygon (rare; usually near=mid-foreground objects).
  //
  // layerLow is the *minimum* brightness this layer occupies, used as the
  // cutoff below which pixels are considered "behind this layer".
  const layerLow = DEPTH_LAYER_THRESHOLDS[targetRegion.depthLayer] ?? 0;

  // Create RGBA canvas.
  // Default: BLACK background = preserve everything (this is the inverse of
  // the previous bug, which filled the entire image as "inpaint" and made
  // LaMa hallucinate content in regions far outside the polygon).
  const canvas = document.createElement('canvas');
  canvas.width = dw;
  canvas.height = dh;
  const ctx = canvas.getContext('2d')!;
  ctx.fillStyle = 'black'; // black = keep
  ctx.fillRect(0, 0, dw, dh);

  // Walk only the polygon interior. Inside the polygon:
  //   - pixels at this layer's depth or shallower (foreground of this layer)
  //     → BLACK (keep, they ARE the layer we're peeling off).
  //   - pixels behind this layer (deeper / lower brightness) → WHITE (inpaint,
  //     they were occluded and we want the layer beneath to show through).
  ctx.fillStyle = 'white'; // white = inpaint target

  for (let py = 0; py < dh; py++) {
    for (let px = 0; px < dw; px++) {
      if (polyMask[py * dw + px] === 0) continue; // outside polygon: leave black (keep)
      const d = depthData[(py * dw + px) * 4];
      if (d < layerLow) {
        // Pixel is deeper (behind) the target layer → was occluded → inpaint.
        ctx.fillRect(px, py, 1, 1);
      }
      // else: pixel is at or shallower than the target layer → keep (already black).
    }
  }

  // NOTE on the previous implementation: it computed `Math.abs(d - medianDepth) <= MARGIN`
  // and kept those, inverting the desired semantics (it kept foreground pixels and
  // inpainted pixels with similar depth to the median — fine — BUT it also marked
  // ALL pixels outside the polygon as inpaint targets, which made LaMa hallucinate
  // the entire image). The default background has now been flipped to black, and
  // we keep the explicit DEPTH_MARGIN-style thresholding off in favor of a
  // per-layer threshold from DEPTH_LAYER_THRESHOLDS.
  void DEPTH_MARGIN; // kept exported implicitly; not used here anymore
  void medianDepth; // reserved for future fine-grained heuristics

  // Map grayscale canvas to RGBA alpha channel
  // black (keep) → alpha=0, white (inpaint) → alpha=255
  const imageData = ctx.getImageData(0, 0, dw, dh);
  const rgba = ctx.createImageData(dw, dh);
  for (let i = 0; i < imageData.data.length; i += 4) {
    const gray = imageData.data[i]; // 0 or 255
    rgba.data[i] = 255;
    rgba.data[i + 1] = 255;
    rgba.data[i + 2] = 255;
    rgba.data[i + 3] = gray; // 255=white=inpaint, 0=black=keep
  }
  ctx.putImageData(rgba, 0, 0);

  return canvas.toDataURL('image/png');
}

/**
 * Compute the standard "inverse mask" for a region.
 * white (alpha=255) → inpaint target, black (alpha=0) → keep original
 *
 * polygon interior = inpaint (LaMa fills), outside = keep
 */
export function computeSimpleMask(
  polygon: PolygonPoint[],
  imageWidth: number,
  imageHeight: number,
): string {
  const polyMask = buildPolygonMask(polygon, imageWidth, imageHeight);

  const canvas = document.createElement('canvas');
  canvas.width = imageWidth;
  canvas.height = imageHeight;
  const ctx = canvas.getContext('2d')!;

  // Black background = everything outside polygon is "keep"
  ctx.fillStyle = 'black';
  ctx.fillRect(0, 0, imageWidth, imageHeight);

  // Draw polygon interior in white = inpaint target
  ctx.fillStyle = 'white';
  for (let py = 0; py < imageHeight; py++) {
    for (let px = 0; px < imageWidth; px++) {
      if (polyMask[py * imageWidth + px] !== 0) {
        ctx.fillRect(px, py, 1, 1);
      }
    }
  }

  // Map to RGBA alpha: white → alpha=255 (inpaint), black → alpha=0 (keep)
  const imageData = ctx.getImageData(0, 0, imageWidth, imageHeight);
  const rgba = ctx.createImageData(imageWidth, imageHeight);
  for (let i = 0; i < imageData.data.length; i += 4) {
    const gray = imageData.data[i];
    rgba.data[i] = 255;
    rgba.data[i + 1] = 255;
    rgba.data[i + 2] = 255;
    rgba.data[i + 3] = gray;
  }
  ctx.putImageData(rgba, 0, 0);

  return canvas.toDataURL('image/png');
}

/**
 * After LaMa inpaint, estimate depth values for the newly inpainted region
 * by interpolating from nearby non-inpainted pixels.
 *
 * Returns a depth ImageData (grayscale) with interpolated values for inpainted pixels.
 */
export function interpolateDepthForInpaintResult(
  originalDepth: ImageData,
  inpaintMask: ImageData,
): ImageData {
  const { width, height } = originalDepth;
  // Deep copy so we don't mutate the original
  const result = new ImageData(
    new Uint8ClampedArray(originalDepth.data.buffer),
    width,
    height,
  );

  // For each inpainted pixel, sample from surrounding non-inpainted neighbors
  const searchRadius = 8;
  for (let py = 0; py < height; py++) {
    for (let px = 0; px < width; px++) {
      const idx = (py * width + px) * 4;
      if (inpaintMask.data[idx + 3] !== 255) continue; // not newly inpainted

      const neighbors: number[] = [];
      for (let dy = -searchRadius; dy <= searchRadius; dy++) {
        for (let dx = -searchRadius; dx <= searchRadius; dx++) {
          if (dx === 0 && dy === 0) continue;
          const nx = px + dx;
          const ny = py + dy;
          if (nx < 0 || nx >= width || ny < 0 || ny >= height) continue;
          const nIdx = (ny * width + nx) * 4;
          if (inpaintMask.data[nIdx + 3] === 255) continue;
          neighbors.push(originalDepth.data[nIdx]);
        }
      }

      if (neighbors.length > 0) {
        neighbors.sort((a, b) => a - b);
        const median = neighbors[Math.floor(neighbors.length / 2)];
        result.data[idx] = median;
        result.data[idx + 1] = median;
        result.data[idx + 2] = median;
        result.data[idx + 3] = 255;
      }
    }
  }

  return result;
}
