// ─────────────────────────────────────────────────────────────────────────────
// Resolution utilities
// ─────────────────────────────────────────────────────────────────────────────
import type { ImageSizePreset, ResolutionTier } from '../types';

const PIXELS: Record<ResolutionTier, number> = {
  '1K': 1024,
  '2K': 2048,
};

export const SIZE_PRESETS: ImageSizePreset[] = ['16:9', '1:1', '9:16'];
export const RESOLUTION_TIERS: ResolutionTier[] = ['1K', '2K'];

export interface ActualSize {
  width: number;
  height: number;
  sizeString: string;
}

export function computeActualSize(
  ratio: ImageSizePreset,
  tier: ResolutionTier,
): ActualSize {
  const base = PIXELS[tier];
  const height =
    ratio === '1:1' ? base
    : ratio === '16:9' ? Math.round(base * 9 / 16)
    : Math.round(base * 16 / 9);
  return {
    width: base,
    height,
    sizeString: `${base}*${height}`,
  };
}

export function computeCropFrameSize(
  containerWidth: number,
  containerHeight: number,
  ratio: ImageSizePreset,
): { width: number; height: number } {
  const containerRatio = containerWidth / containerHeight;
  const targetRatio =
    ratio === '1:1' ? 1
    : ratio === '16:9' ? 16 / 9
    : 9 / 16;

  if (containerRatio > targetRatio) {
    const height = containerHeight;
    const width = Math.round(height * targetRatio);
    return { width, height };
  } else {
    const width = containerWidth;
    const height = Math.round(width / targetRatio);
    return { width, height };
  }
}

export function describeSize(ratio: ImageSizePreset, tier: ResolutionTier): string {
  const { width, height } = computeActualSize(ratio, tier);
  return `${tier} · ${width}×${height}`;
}
