import { Image, CheckCircle2 } from 'lucide-react';
import type { DepthLayerKey, DepthSplitResult } from '../types';

interface DepthSplitPanelProps {
  result: DepthSplitResult;
  selectedLayer: DepthLayerKey | null;
  isConfirmed: boolean;
  onSelectLayer: (layer: DepthLayerKey) => void;
  onConfirm: () => void;
}

const LAYER_LABELS: Record<DepthLayerKey, string> = {
  foreground: '前景',
  midground: '中景',
  background: '背景',
  sky: '天空',
};

const LAYER_ORDER: DepthLayerKey[] = ['foreground', 'midground', 'background', 'sky'];

export function DepthSplitPanel({ result, selectedLayer, isConfirmed, onSelectLayer, onConfirm }: DepthSplitPanelProps) {
  return (
    <div className="flex flex-col gap-3 p-4 bg-gray-900 border-t border-gray-700 shrink-0">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-medium text-gray-200">
          <Image size={16} className="text-cyan-400" />
          <span>Depth Split Preview</span>
        </div>

        <button
          type="button"
          onClick={onConfirm}
          className={[
            'inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors',
            isConfirmed
              ? 'bg-emerald-700/70 text-emerald-100 border border-emerald-500/60'
              : 'bg-cyan-600 text-white hover:bg-cyan-500 border border-cyan-500/60',
          ].join(' ')}
        >
          <CheckCircle2 size={14} />
          {isConfirmed ? '已确认分层' : '确认分层生成面片'}
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {LAYER_ORDER.map((layer) => {
          const active = selectedLayer === layer;
          return (
            <button
              key={layer}
              type="button"
              onClick={() => onSelectLayer(layer)}
              className={[
                'overflow-hidden rounded-xl border text-left transition-all',
                active
                  ? 'border-cyan-400 bg-gray-800 shadow-[0_0_0_1px_rgba(34,211,238,0.5)]'
                  : 'border-gray-700 bg-gray-900 hover:border-gray-500 hover:bg-gray-800',
              ].join(' ')}
            >
              <div className="aspect-video bg-black">
                <img
                  src={result[layer]}
                  alt={LAYER_LABELS[layer]}
                  className="w-full h-full object-contain"
                  draggable={false}
                />
              </div>
              <div className="flex items-center justify-between px-3 py-2">
                <span className="text-sm text-gray-100">{LAYER_LABELS[layer]}</span>
                {active && <span className="text-[11px] text-cyan-300">查看中</span>}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
