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

// LAYER_ORDER 的顺序与 UI 2x2 网格布局对应：
//   前两个（前景/中景）→ 左列（离观众更近）
//   后两个（背景/天空）→ 右列（离观众更远）
// 这与 z-buffer 深度顺序一致：近处物体遮挡远处物体
// 2x2 网格而非 1x4 列表的原因：预览图 16:9 比例下 2 列布局每格宽高比更接近原始画面
export function DepthSplitPanel({ result, selectedLayer, isConfirmed, onSelectLayer, onConfirm }: DepthSplitPanelProps) {
  return (
    <div className="flex flex-col gap-3 p-4 bg-gray-900 border-t border-gray-700 shrink-0">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-medium text-gray-200">
          <Image size={16} className="text-cyan-400" />
          <span>Depth Split Preview</span>
        </div>

        {/*
          确认分层：锁定深度分层的分割结果
          确认后：
            1. 按钮状态变为"已确认分层"（绿色），不可再次点击
            2. 触发 Paper Diorama 面板的启用（父组件通过 isConfirmed 控制）
            3. 后续对象分配、层级编辑均基于此次确认的分层数据进行
        */}
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
                {/*
                  result[layer] 是后端返回的 base64 PNG，每层对应一组前景掩码
                  object-contain 使图像完整显示在框内，letterbox 不变形
                  aspect-video 确保四格等大，便于视觉对比各层覆盖范围
                */}
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
