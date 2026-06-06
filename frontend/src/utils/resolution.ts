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

// 根据宽高比和像素级别推算最终图像尺寸。
// 逻辑：取 PIXELS[tier] 作为"较长边"的像素数，短边由比例换算得出：
//   - 1:1 正方形：长宽均为 base（1024 或 2048）
//   - 16:9 横屏：base 为宽度，height = base * 9/16（像素数不变，面积更小）
//   - 9:16 竖屏：base 为高度，height = base * 16/9
// 注意：这里 base 始终是较长边，与某些"将 base 作为宽度"的惯例不同，
// 因此 9:16 竖屏时返回的 width 会大于 height。
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
