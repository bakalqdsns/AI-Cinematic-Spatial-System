// ─────────────────────────────────────────────────────────────────────────────
// Depth split utilities — derive coarse layer cutouts from depth map
// ─────────────────────────────────────────────────────────────────────────────
import type {
  DepthLayerKey,
  DepthSplitResult,
  DepthSplitThresholds,
} from '../types';

const LAYER_ORDER: DepthLayerKey[] = ['foreground', 'midground', 'background', 'sky'];

export const DEFAULT_DEPTH_SPLIT_THRESHOLDS: DepthSplitThresholds = {
  foregroundMin: 192,
  midgroundMin: 128,
  backgroundMin: 64,
};

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`Failed to load image: ${src.slice(0, 64)}`));
    img.src = src;
  });
}

function getLayerForBrightness(
  brightness: number,
  thresholds: DepthSplitThresholds,
): DepthLayerKey {
  if (brightness >= thresholds.foregroundMin) return 'foreground';
  if (brightness >= thresholds.midgroundMin) return 'midground';
  if (brightness >= thresholds.backgroundMin) return 'background';
  return 'sky';
}

export async function splitDepthLayers(
  depthMapUrl: string,
  originalImageUrl: string,
  thresholds: DepthSplitThresholds = DEFAULT_DEPTH_SPLIT_THRESHOLDS,
): Promise<DepthSplitResult> {
  const [depthImg, originalImg] = await Promise.all([
    loadImage(depthMapUrl),
    loadImage(originalImageUrl),
  ]);

  const width = originalImg.naturalWidth || depthImg.naturalWidth;
  const height = originalImg.naturalHeight || depthImg.naturalHeight;

  if (!width || !height) {
    throw new Error('Unable to determine image dimensions for depth split');
  }

  const depthCanvas = document.createElement('canvas');
  depthCanvas.width = width;
  depthCanvas.height = height;
  const depthCtx = depthCanvas.getContext('2d');
  if (!depthCtx) {
    throw new Error('Failed to create depth canvas context');
  }
  depthCtx.drawImage(depthImg, 0, 0, width, height);
  const depthPixels = depthCtx.getImageData(0, 0, width, height).data;

  const sourceCanvas = document.createElement('canvas');
  sourceCanvas.width = width;
  sourceCanvas.height = height;
  const sourceCtx = sourceCanvas.getContext('2d');
  if (!sourceCtx) {
    throw new Error('Failed to create source canvas context');
  }
  sourceCtx.drawImage(originalImg, 0, 0, width, height);
  const sourceImage = sourceCtx.getImageData(0, 0, width, height);
  const sourcePixels = sourceImage.data;

  const layerImageData = Object.fromEntries(
    LAYER_ORDER.map((layer) => [layer, new ImageData(width, height)]),
  ) as Record<DepthLayerKey, ImageData>;

  for (let i = 0; i < depthPixels.length; i += 4) {
    const brightness = depthPixels[i];
    const layer = getLayerForBrightness(brightness, thresholds);

    for (const candidate of LAYER_ORDER) {
      const target = layerImageData[candidate].data;
      if (candidate === layer) {
        target[i] = sourcePixels[i];
        target[i + 1] = sourcePixels[i + 1];
        target[i + 2] = sourcePixels[i + 2];
        target[i + 3] = 255;
      } else {
        target[i] = 0;
        target[i + 1] = 0;
        target[i + 2] = 0;
        target[i + 3] = 0;
      }
    }
  }

  const layerCanvas = document.createElement('canvas');
  layerCanvas.width = width;
  layerCanvas.height = height;
  const layerCtx = layerCanvas.getContext('2d');
  if (!layerCtx) {
    throw new Error('Failed to create layer canvas context');
  }

  const result = {} as DepthSplitResult;
  for (const layer of LAYER_ORDER) {
    layerCtx.clearRect(0, 0, width, height);
    layerCtx.putImageData(layerImageData[layer], 0, 0);
    result[layer] = layerCanvas.toDataURL('image/png');
  }

  return result;
}
