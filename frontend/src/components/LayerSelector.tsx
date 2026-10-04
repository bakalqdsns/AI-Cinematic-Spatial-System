import { LAYER_COLORS } from '../types';

const BAND_LABELS = ['前景', '中景', '背景', '天空'];

export function LayerSelector({
  selectedColor,
  onSelect,
  counts,
}: {
  selectedColor: number | null;
  onSelect: (colorIndex: number) => void;
  counts: Record<number, number>;
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="text-xs text-gray-400">深度层（一色一层）</div>
      <div className="flex gap-2 flex-wrap">
        {BAND_LABELS.map((label, i) => (
          <div key={label} className="flex items-center gap-1 text-[11px] text-gray-300">
            <span className="w-4 h-4 rounded" style={{ background: LAYER_COLORS[i] }} />
            {label}
          </div>
        ))}
      </div>
      <div className="text-xs text-gray-400">拆出的物体层。选中物体后点一个颜色，同一颜色共用一个深度。</div>
      <div className="flex gap-2 flex-wrap">
        {LAYER_COLORS.slice(4).map((color, offset) => {
          const index = offset + 4;
          const count = counts[index] || 0;
          const active = selectedColor === index;
          return (
            <button
              key={color}
              type="button"
              onClick={() => onSelect(index)}
              title={count > 0 ? `${count} 个物体` : '新建物体层'}
              className={`w-7 h-7 rounded border-2 ${active ? 'border-white' : 'border-transparent'}`}
              style={{ background: color }}
            >
              {count > 0 && <span className="text-[10px] text-black font-semibold">{count}</span>}
            </button>
          );
        })}
      </div>
    </div>
  );
}
