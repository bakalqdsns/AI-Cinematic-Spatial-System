import { useMemo, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { useScriptStore } from '../store/useScriptStore';
import { useShotWorkflowStore } from '../store/useShotWorkflowStore';
import { useAppStore } from '../store/useAppStore';
import { LayerSelector } from './LayerSelector';
import { analyzeImage, inpaintImage } from '../services/aicssService';
import { saveConfirmedLayers } from '../services/scriptService';
import {
  DEFAULT_DEPTH_SPLIT_THRESHOLDS,
  splitDepthLayers,
} from '../utils/depthSplit';
import type { DepthLayerKey, DepthSplitThresholds, DetectedObject } from '../types';

const BANDS: DepthLayerKey[] = ['foreground', 'midground', 'background', 'sky'];
const BAND_RANK: Record<DepthLayerKey, number> = {
  foreground: 0,
  midground: 10,
  background: 20,
  sky: 30,
};

interface LayerPng {
  name: string;
  dataUrl: string;
  nearRank: number;
}

function wideUrl(raw?: string): string {
  if (!raw) return '';
  if (raw.startsWith('data:') || raw.startsWith('http') || raw.startsWith('blob:')) return raw;
  return `data:image/png;base64,${raw}`;
}

function brightness(depth: number): number {
  if (depth <= 1.5) return depth * 255;
  return Math.max(0, Math.min(255, depth));
}

function bandFor(depth: number, thresholds: DepthSplitThresholds): DepthLayerKey {
  const value = brightness(depth);
  if (value >= thresholds.foregroundMin) return 'foreground';
  if (value >= thresholds.midgroundMin) return 'midground';
  if (value >= thresholds.backgroundMin) return 'background';
  return 'sky';
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error('图片加载失败'));
    img.src = src;
  });
}

function canvasOf(img: CanvasImageSource, w: number, h: number): HTMLCanvasElement {
  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  canvas.getContext('2d')!.drawImage(img, 0, 0, w, h);
  return canvas;
}

function paintPolygon(
  ctx: CanvasRenderingContext2D,
  polygon: [number, number][],
  w: number,
  h: number,
) {
  if (polygon.length < 3) return;
  ctx.beginPath();
  polygon.forEach(([x, y], i) => {
    const px = x * w;
    const py = y * h;
    if (i === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  });
  ctx.closePath();
  ctx.fill();
}

async function buildLayers(
  sourceUrl: string,
  bandUrls: Record<DepthLayerKey, string>,
  objects: DetectedObject[],
  assignments: Record<string, number>,
  thresholds: DepthSplitThresholds,
): Promise<LayerPng[]> {
  const source = await loadImage(sourceUrl);
  const w = source.naturalWidth;
  const h = source.naturalHeight;
  const bandImgs = await Promise.all(BANDS.map(async (band) => [band, await loadImage(bandUrls[band])] as const));

  const bandCanvas: Record<DepthLayerKey, HTMLCanvasElement> = {
    foreground: canvasOf(bandImgs[0][1], w, h),
    midground: canvasOf(bandImgs[1][1], w, h),
    background: canvasOf(bandImgs[2][1], w, h),
    sky: canvasOf(bandImgs[3][1], w, h),
  };

  const groups = new Map<number, DetectedObject[]>();
  for (const obj of objects) {
    const color = assignments[obj.id];
    if (color === undefined || color < 4) continue;
    const list = groups.get(color) ?? [];
    list.push(obj);
    groups.set(color, list);
    const home = bandFor(obj.depth, thresholds);
    const ctx = bandCanvas[home].getContext('2d')!;
    ctx.globalCompositeOperation = 'destination-out';
    ctx.fillStyle = '#000';
    paintPolygon(ctx, obj.polygon, w, h);
    ctx.globalCompositeOperation = 'source-over';
  }

  const layers: LayerPng[] = BANDS.map((band) => ({
    name: band,
    dataUrl: bandCanvas[band].toDataURL('image/png'),
    nearRank: BAND_RANK[band],
  }));

  for (const [color, objs] of groups) {
    const canvas = document.createElement('canvas');
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext('2d')!;
    ctx.drawImage(source, 0, 0, w, h);
    ctx.globalCompositeOperation = 'destination-in';
    ctx.fillStyle = '#000';
    for (const obj of objs) paintPolygon(ctx, obj.polygon, w, h);
    const parent = Math.min(...objs.map((obj) => BAND_RANK[bandFor(obj.depth, thresholds)]));
    layers.push({
      name: `object_${color}`,
      dataUrl: canvas.toDataURL('image/png'),
      nearRank: parent - 1 - (14 - color) * 0.01,
    });
  }

  layers.sort((a, b) => a.nearRank - b.nearRank);
  return layers;
}

async function alphaMask(dataUrl: string): Promise<Uint8ClampedArray> {
  const img = await loadImage(dataUrl);
  const canvas = canvasOf(img, img.naturalWidth, img.naturalHeight);
  return canvas.getContext('2d')!.getImageData(0, 0, canvas.width, canvas.height).data;
}

async function inpaintLayer(sourceUrl: string, layer: LayerPng, closer: LayerPng[]): Promise<string> {
  const base = await alphaMask(layer.dataUrl);
  const img = await loadImage(layer.dataUrl);
  const width = img.naturalWidth;
  const height = img.naturalHeight;
  const closerMasks = await Promise.all(closer.map((item) => alphaMask(item.dataUrl)));
  const mask = document.createElement('canvas');
  mask.width = width;
  mask.height = height;
  const mctx = mask.getContext('2d')!;
  const image = mctx.createImageData(width, height);
  let holes = 0;
  for (let i = 0; i < width * height; i++) {
    const own = base[i * 4 + 3] > 16;
    const covered = closerMasks.some((pixels) => pixels[i * 4 + 3] > 16);
    if (covered && !own) {
      image.data[i * 4] = 255;
      image.data[i * 4 + 1] = 255;
      image.data[i * 4 + 2] = 255;
      image.data[i * 4 + 3] = 255;
      holes += 1;
    }
  }
  if (holes < 16) return layer.dataUrl;
  mctx.putImageData(image, 0, 0);
  const filledUrl = await inpaintImage(sourceUrl, mask.toDataURL('image/png'), '补全被更近层挡住的区域');
  const filled = await loadImage(filledUrl);
  const out = canvasOf(img, width, height);
  const fctx = canvasOf(filled, width, height).getContext('2d')!;
  const octx = out.getContext('2d')!;
  const src = fctx.getImageData(0, 0, width, height);
  const dst = octx.getImageData(0, 0, width, height);
  for (let i = 0; i < width * height; i++) {
    if (image.data[i * 4 + 3] === 0) continue;
    dst.data[i * 4] = src.data[i * 4];
    dst.data[i * 4 + 1] = src.data[i * 4 + 1];
    dst.data[i * 4 + 2] = src.data[i * 4 + 2];
    dst.data[i * 4 + 3] = 255;
  }
  octx.putImageData(dst, 0, 0);
  return out.toDataURL('image/png');
}

export function SplitControls() {
  const shot = useScriptStore((s) => s.shots.find((item) => item.id === s.selectedShotId) ?? null);
  const sceneAsset = useScriptStore((s) => (shot ? s.sceneAssets[shot.sceneId] : undefined));
  const projectId = useScriptStore((s) => s.projectId);
  const patch = useShotWorkflowStore((s) => s.patch);
  const setAnalysisResult = useAppStore((s) => s.setAnalysisResult);
  const analysisResult = useAppStore((s) => s.analysisResult);

  const sourceUrl = wideUrl(sceneAsset?.keyframeImages?.wide);
  const [thresholds, setThresholds] = useState<DepthSplitThresholds>(DEFAULT_DEPTH_SPLIT_THRESHOLDS);
  const [bandUrls, setBandUrls] = useState<Record<DepthLayerKey, string> | null>(null);
  const [assignments, setAssignments] = useState<Record<string, number>>({});
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [selectedColor, setSelectedColor] = useState<number | null>(null);
  const [history, setHistory] = useState<{ thresholds: DepthSplitThresholds; assignments: Record<string, number> }[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState<LayerPng[] | null>(null);

  const objects = analysisResult?.objects ?? [];
  const counts = useMemo(() => {
    const map: Record<number, number> = {};
    for (const color of Object.values(assignments)) map[color] = (map[color] || 0) + 1;
    return map;
  }, [assignments]);

  const remember = () => {
    setHistory((stack) => [...stack, { thresholds, assignments }]);
  };

  const undo = () => {
    setHistory((stack) => {
      const prev = stack[stack.length - 1];
      if (!prev) return stack;
      setThresholds(prev.thresholds);
      setAssignments(prev.assignments);
      if (shot) patch(shot.id, { sceneDone: false });
      setConfirmed(null);
      return stack.slice(0, -1);
    });
  };

  if (!shot) {
    return <div className="h-full flex items-center justify-center text-gray-500">请在左侧选择一条分镜</div>;
  }
  if (!sourceUrl) {
    return <div className="h-full flex items-center justify-center text-gray-400 px-6 text-center">这条分镜还没有场景图。请先到场景资产生成 wide 关键帧。</div>;
  }

  const detect = async () => {
    setBusy('正在检测深度和物体…');
    setError(null);
    try {
      const result = await analyzeImage(sourceUrl, shot.id);
      setAnalysisResult(result);
      const split = await splitDepthLayers(result.depthMapUrl, sourceUrl, thresholds);
      setBandUrls(split);
      setAssignments({});
      setConfirmed(null);
      if (shot) patch(shot.id, { sceneDone: false });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  const refreshSplit = async (next: DepthSplitThresholds) => {
    if (!analysisResult?.depthMapUrl) return;
    const split = await splitDepthLayers(analysisResult.depthMapUrl, sourceUrl, next);
    setBandUrls(split);
    setConfirmed(null);
    patch(shot.id, { sceneDone: false });
  };

  const assignSelected = (color: number) => {
    if (selectedIds.length === 0) {
      setSelectedColor(color);
      return;
    }
    remember();
    setAssignments((prev) => {
      const next = { ...prev };
      for (const id of selectedIds) next[id] = color;
      return next;
    });
    setSelectedColor(color);
    setConfirmed(null);
    patch(shot.id, { sceneDone: false });
  };

  const confirm = async () => {
    if (!bandUrls || !projectId) {
      setError(projectId ? '请先检测' : '请先解析剧本以建立项目');
      return;
    }
    setBusy('正在按实际深度补全…');
    setError(null);
    try {
      const built = await buildLayers(sourceUrl, bandUrls, objects, assignments, thresholds);
      const filled: LayerPng[] = [];
      for (let i = 0; i < built.length; i++) {
        if (i === 0) {
          filled.push(built[i]);
          continue;
        }
        const dataUrl = await inpaintLayer(sourceUrl, built[i], built.slice(0, i));
        filled.push({ ...built[i], dataUrl });
      }
      await saveConfirmedLayers(projectId, shot.id, filled.map((layer, index) => ({
        name: layer.name,
        dataUri: layer.dataUrl,
        zOffset: -2 - index * 3,
        order: index + 1,
      })));
      setConfirmed(filled);
      patch(shot.id, { sceneDone: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="h-full overflow-y-auto p-4 space-y-4">
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={detect}
          disabled={!!busy}
          className="px-3 py-1.5 rounded bg-blue-600 text-sm disabled:opacity-50"
        >
          检测
        </button>
        <button type="button" onClick={undo} disabled={history.length === 0 || !!busy} className="px-3 py-1.5 rounded bg-gray-800 text-sm disabled:opacity-40">
          撤销
        </button>
        <button type="button" onClick={confirm} disabled={!bandUrls || !!busy} className="px-3 py-1.5 rounded bg-emerald-700 text-sm disabled:opacity-40">
          补全并确认
        </button>
        {busy && <span className="text-xs text-gray-400 flex items-center gap-1"><Loader2 size={14} className="animate-spin" />{busy}</span>}
      </div>
      {error && <p className="text-sm text-red-400">{error}</p>}

      <img src={sourceUrl} alt="场景" className="max-h-64 rounded border border-gray-800" />

      {analysisResult && (
        <>
          <div className="grid grid-cols-3 gap-3 text-xs text-gray-300">
            {([
              ['foregroundMin', '前景分割点'],
              ['midgroundMin', '中景分割点'],
              ['backgroundMin', '背景分割点'],
            ] as const).map(([key, label]) => (
              <label key={key} className="flex flex-col gap-1">
                <span>{label} {thresholds[key]}</span>
                <input
                  type="range"
                  min={0}
                  max={255}
                  value={thresholds[key]}
                  onMouseDown={remember}
                  onChange={(e) => {
                    const next = { ...thresholds, [key]: Number(e.target.value) };
                    setThresholds(next);
                    void refreshSplit(next);
                  }}
                />
              </label>
            ))}
          </div>

          {bandUrls && (
            <div className="grid grid-cols-4 gap-2">
              {BANDS.map((band) => (
                <img key={band} src={bandUrls[band]} alt={band} className="rounded bg-black" />
              ))}
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            {objects.map((obj) => {
              const on = selectedIds.includes(obj.id);
              return (
                <button
                  key={obj.id}
                  type="button"
                  onClick={() => setSelectedIds((ids) => ids.includes(obj.id) ? ids.filter((id) => id !== obj.id) : [...ids, obj.id])}
                  className={`text-xs px-2 py-1 rounded border ${on ? 'border-blue-400 bg-blue-950' : 'border-gray-700'}`}
                >
                  {obj.classLabel || obj.id}
                  {assignments[obj.id] !== undefined ? ` · 色${assignments[obj.id]}` : ''}
                </button>
              );
            })}
          </div>

          <LayerSelector selectedColor={selectedColor} onSelect={assignSelected} counts={counts} />

          {selectedIds.length > 0 && (
            <button
              type="button"
              className="text-xs text-gray-400 underline"
              onClick={() => {
                remember();
                setAssignments((prev) => {
                  const next = { ...prev };
                  for (const id of selectedIds) delete next[id];
                  return next;
                });
                patch(shot.id, { sceneDone: false });
                setConfirmed(null);
              }}
            >
              把选中物体放回原图层
            </button>
          )}
        </>
      )}

      {confirmed && (
        <div>
          <div className="text-xs text-gray-400 mb-2">确认后的层（近到远）</div>
          <div className="grid grid-cols-4 gap-2">
            {confirmed.map((layer, index) => (
              <figure key={layer.name}>
                <img src={layer.dataUrl} alt={layer.name} className="rounded bg-black" />
                <figcaption className="text-[10px] text-gray-500">第 {index + 1} 层 {layer.name}</figcaption>
              </figure>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
