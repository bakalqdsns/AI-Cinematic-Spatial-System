import { useCallback } from 'react';
import { useAppStore } from '../store/useAppStore';
import { DEFAULT_PAPER_DIORAMA_PARAMS } from '../types';
import type { PaperDioramaParams } from '../types';
import { generatePaperLayer } from '../services/aicssService';
import type { DepthLayerKey } from '../types';

const LAYER_LABELS: Record<DepthLayerKey, string> = {
  foreground: '前景',
  midground: '中景',
  background: '背景',
  sky: '天空',
};

const LAYER_ORDER: DepthLayerKey[] = ['foreground', 'midground', 'background', 'sky'];

interface DioramaSettingsPanelProps {
  /** Image URL to pass to the paper-layer endpoint */
  effectiveImageUrl: string;
  /** Map of layer → data URL of the RGBA layer image */
  depthSplitResult: Record<DepthLayerKey, string> | null;
}

export function DioramaSettingsPanel({ effectiveImageUrl, depthSplitResult }: DioramaSettingsPanelProps) {
  const dioramaParams = useAppStore((s) => s.dioramaParams);
  const setDioramaParams = useAppStore((s) => s.setDioramaParams);
  const dioramaLoading = useAppStore((s) => s.dioramaLoading);
  const dioramaError = useAppStore((s) => s.dioramaError);
  const setDioramaLoading = useAppStore((s) => s.setDioramaLoading);
  const setDioramaError = useAppStore((s) => s.setDioramaError);
  const depthLayerDioramaAssets = useAppStore((s) => s.depthLayerDioramaAssets);
  const setDepthLayerDioramaAsset = useAppStore((s) => s.setDepthLayerDioramaAsset);
  const dioramaMode = useAppStore((s) => s.dioramaMode);
  const setDioramaMode = useAppStore((s) => s.setDioramaMode);
  const outlineEnabled = useAppStore((s) => s.outlineEnabled);
  const setOutlineEnabled = useAppStore((s) => s.setOutlineEnabled);
  const parallaxEnabled = useAppStore((s) => s.parallaxEnabled);
  const setParallaxEnabled = useAppStore((s) => s.setParallaxEnabled);
  const parallaxIntensity = useAppStore((s) => s.parallaxIntensity);
  const setParallaxIntensity = useAppStore((s) => s.setParallaxIntensity);
  const depthSplitConfirmed = useAppStore((s) => s.depthSplitConfirmed);

  const updateParam = useCallback(
    <K extends keyof PaperDioramaParams>(key: K, value: PaperDioramaParams[K]) => {
      setDioramaParams({ [key]: value });
    },
    [setDioramaParams],
  );

  const handleGenerateAllLayers = useCallback(async () => {
    if (!depthSplitResult || !effectiveImageUrl) return;

    setDioramaLoading(true);
    setDioramaError(null);

    try {
      await Promise.all(
        LAYER_ORDER.map(async (layer) => {
          const layerUrl = depthSplitResult[layer];
          if (!layerUrl) return;
          const result = await generatePaperLayer(layerUrl, null, dioramaParams);
          setDepthLayerDioramaAsset(layer, {
            layer,
            rgbaUrl: result.paper_style_url,
            thicknessGrayUrl: result.thickness_gray_url,
            normalMapUrl: result.normal_map_url,
            outlinedUrl: result.outlined_url,
            paperStyleUrl: result.paper_style_url,
          });
        }),
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setDioramaError(msg);
      console.error('[DioramaSettings] Generate failed:', err);
    } finally {
      setDioramaLoading(false);
    }
  }, [depthSplitResult, effectiveImageUrl, dioramaParams, setDioramaLoading, setDioramaError, setDepthLayerDioramaAsset]);

  const hasGeneratedLayers = Object.keys(depthLayerDioramaAssets).length > 0;

  return (
    <div className="flex flex-col gap-3 p-4 bg-gray-900 border-t border-gray-700 shrink-0">
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-amber-200">Paper Diorama 2.0</div>
          <div className="text-xs text-gray-400">风格化 · 纸张厚度 · 法线贴图 · 视差动画</div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setDioramaParams(DEFAULT_PAPER_DIORAMA_PARAMS)}
            className="px-2 py-1 rounded border border-gray-700 bg-gray-900 text-xs text-gray-400 hover:text-gray-200 hover:border-gray-500 transition-colors"
          >
            重置参数
          </button>
        </div>
      </div>

      {/* Rendering mode toggle */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-gray-400">渲染模式：</span>
        <div className="flex rounded-lg border border-gray-700 overflow-hidden">
          <button
            type="button"
            onClick={() => setDioramaMode('billboard')}
            className={`px-3 py-1 text-xs font-medium transition-colors ${
              dioramaMode === 'billboard'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-900 text-gray-400 hover:text-gray-200'
            }`}
          >
            Billboard
          </button>
          <button
            type="button"
            onClick={() => setDioramaMode('paper')}
            className={`px-3 py-1 text-xs font-medium transition-colors ${
              dioramaMode === 'paper'
                ? 'bg-amber-600 text-white'
                : 'bg-gray-900 text-gray-400 hover:text-gray-200'
            }`}
          >
            纸雕模式
          </button>
        </div>
      </div>

      {/* Paper Diorama params — only show when in paper mode */}
      {dioramaMode === 'paper' && (
        <div className="flex flex-col gap-3">
          {/* Style params */}
          <div className="rounded-xl border border-amber-900/40 bg-gray-950/70 p-3">
            <div className="text-xs font-medium text-amber-300 mb-3">风格参数</div>
            <div className="grid gap-3 md:grid-cols-2">
              <label className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between text-xs text-gray-300">
                  <span>色彩层级</span>
                  <span className="text-amber-300">{dioramaParams.colorLevels}</span>
                </div>
                <input
                  type="range"
                  min={3}
                  max={30}
                  step={1}
                  value={dioramaParams.colorLevels}
                  onChange={(e) => updateParam('colorLevels', Number(e.target.value))}
                  className="w-full accent-amber-400"
                />
                <div className="text-[10px] text-gray-500">低 = 更平面化的纸雕感</div>
              </label>

              <label className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between text-xs text-gray-300">
                  <span>风格强度</span>
                  <span className="text-amber-300">{dioramaParams.styleStrength.toFixed(2)}</span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={dioramaParams.styleStrength}
                  onChange={(e) => updateParam('styleStrength', Number(e.target.value))}
                  className="w-full accent-amber-400"
                />
                <div className="text-[10px] text-gray-500">边缘保护与色块平滑的权衡</div>
              </label>
            </div>
          </div>

          {/* Thickness params */}
          <div className="rounded-xl border border-amber-900/40 bg-gray-950/70 p-3">
            <div className="text-xs font-medium text-amber-300 mb-3">纸张厚度</div>
            <div className="grid gap-3 md:grid-cols-2">
              <label className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between text-xs text-gray-300">
                  <span>最小厚度 (mm)</span>
                  <span className="text-amber-300">{dioramaParams.thicknessMin.toFixed(1)}</span>
                </div>
                <input
                  type="range"
                  min={0.1}
                  max={20}
                  step={0.1}
                  value={dioramaParams.thicknessMin}
                  onChange={(e) => updateParam('thicknessMin', Number(e.target.value))}
                  className="w-full accent-amber-400"
                />
              </label>

              <label className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between text-xs text-gray-300">
                  <span>最大厚度 (mm)</span>
                  <span className="text-amber-300">{dioramaParams.thicknessMax.toFixed(1)}</span>
                </div>
                <input
                  type="range"
                  min={0.1}
                  max={20}
                  step={0.1}
                  value={dioramaParams.thicknessMax}
                  onChange={(e) => updateParam('thicknessMax', Number(e.target.value))}
                  className="w-full accent-amber-400"
                />
              </label>
            </div>
          </div>

          {/* Outline params */}
          <div className="rounded-xl border border-amber-900/40 bg-gray-950/70 p-3">
            <div className="flex items-center justify-between mb-3">
              <div className="text-xs font-medium text-amber-300">纸雕描边</div>
              <button
                type="button"
                onClick={() => setOutlineEnabled(!outlineEnabled)}
                className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                  outlineEnabled ? 'bg-amber-500' : 'bg-gray-700'
                }`}
              >
                <span
                  className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                    outlineEnabled ? 'translate-x-4.5' : 'translate-x-0.5'
                  }`}
                />
              </button>
            </div>
            <label className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between text-xs text-gray-300">
                <span>描边宽度</span>
                <span className="text-amber-300">{dioramaParams.outlineWidth} px</span>
              </div>
              <input
                type="range"
                min={0}
                max={20}
                step={1}
                value={dioramaParams.outlineWidth}
                onChange={(e) => updateParam('outlineWidth', Number(e.target.value))}
                disabled={!outlineEnabled}
                className="w-full accent-amber-400 disabled:opacity-40"
              />
            </label>
          </div>

          {/* Parallax Animation */}
          <div className="rounded-xl border border-amber-900/40 bg-gray-950/70 p-3">
            <div className="flex items-center justify-between mb-3">
              <div className="text-xs font-medium text-amber-300">视差动画</div>
              <button
                type="button"
                onClick={() => setParallaxEnabled(!parallaxEnabled)}
                className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                  parallaxEnabled ? 'bg-amber-500' : 'bg-gray-700'
                }`}
              >
                <span
                  className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                    parallaxEnabled ? 'translate-x-4.5' : 'translate-x-0.5'
                  }`}
                />
              </button>
            </div>
            {parallaxEnabled && (
              <label className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between text-xs text-gray-300">
                  <span>视差强度</span>
                  <span className="text-amber-300">{parallaxIntensity.toFixed(2)}</span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={parallaxIntensity}
                  onChange={(e) => setParallaxIntensity(Number(e.target.value))}
                  className="w-full accent-amber-400"
                />
                <div className="text-[10px] text-gray-500">前景移动快，背景移动慢，增强空间纵深感</div>
              </label>
            )}
          </div>

          {/* Generate button */}
          <button
            type="button"
            onClick={handleGenerateAllLayers}
            disabled={!depthSplitResult || !effectiveImageUrl || dioramaLoading}
            className={`
              flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg font-medium text-sm transition-all
              ${!depthSplitResult || !effectiveImageUrl || dioramaLoading
                ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
                : 'bg-amber-600 hover:bg-amber-500 text-white active:scale-95'}
            `}
          >
            {dioramaLoading ? (
              <>
                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                生成纸雕纹理中...
              </>
            ) : (
              <>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="3" y="3" width="18" height="18" rx="2" />
                  <path d="M3 9h18M9 3v18" />
                </svg>
                生成纸雕纹理（全部 4 层）
              </>
            )}
          </button>

          {/* Layer thumbnails */}
          {hasGeneratedLayers && (
            <div className="grid grid-cols-2 gap-2">
              {LAYER_ORDER.map((layer) => {
                const asset = depthLayerDioramaAssets[layer];
                if (!asset) return null;
                return (
                  <div key={layer} className="overflow-hidden rounded-lg border border-gray-700 bg-gray-950">
                    <div className="aspect-video bg-black">
                      <img
                        src={asset.outlinedUrl || asset.rgbaUrl}
                        alt={LAYER_LABELS[layer]}
                        className="w-full h-full object-contain"
                        draggable={false}
                      />
                    </div>
                    <div className="px-2 py-1.5">
                      <div className="text-xs text-gray-200">{LAYER_LABELS[layer]}</div>
                      <div className="text-[10px] text-gray-500">纸雕风格</div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Mode hint */}
          {!depthSplitConfirmed && (
            <div className="text-[11px] text-amber-600/70 bg-amber-950/30 rounded px-3 py-2">
              请先在 Depth Split 面板中确认分层，再生成纸雕纹理
            </div>
          )}
        </div>
      )}

      {/* Billboard mode hint */}
      {dioramaMode === 'billboard' && (
        <div className="text-xs text-gray-500 bg-gray-950/50 rounded px-3 py-2">
          当前为 Billboard 渲染模式，切换到「纸雕模式」以启用风格化、厚度与视差效果
        </div>
      )}

      {/* Error */}
      {dioramaError && (
        <div className="flex items-center gap-2 text-red-400 text-xs">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          {dioramaError}
        </div>
      )}
    </div>
  );
}
