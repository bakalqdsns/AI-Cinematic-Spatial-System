// ─────────────────────────────────────────────────────────────────────────────
// LayerSelector — 2D 画布叠加层的颜色分组工具
// 注意：这里的 15 个色块是用于 2D 叠加层视觉区分的任意颜色序号
// 与 DepthSplitPanel 中的深度分层（前景/中景/背景/天空）是完全不同的概念
// 深度分层是 AI 语义分割结果；这些色块只是给用户标记物体的视觉手段
// 对象可以被分配到任意一个色块中，色块颜色仅起视觉区分作用
// ─────────────────────────────────────────────────────────────────────────────
import { useMemo, useCallback } from 'react';
import { useAppStore } from '../store/useAppStore';
import { LAYER_COLORS, MAX_LAYERS } from '../types';
import { Trash2 } from 'lucide-react';

export function LayerSelector() {
  const assignments = useAppStore((s) => s.assignments);
  const selectedLayerIndex = useAppStore((s) => s.selectedLayerIndex);
  const analysisResult = useAppStore((s) => s.analysisResult);
  const selectLayer = useAppStore((s) => s.selectLayer);
  const clearLayer = useAppStore((s) => s.clearLayer);
  const pushHistory = useAppStore((s) => s.pushHistory);

  const objects = analysisResult?.objects ?? [];

  // 始终显示全部 15 个色块（而非仅已使用的）：
  //   - 用户可随时选择任意色块进行分配，无需先清空再添加
  //   - 空白色块同样可以作为分组用途（例如"待定"组）
  const displayCount = MAX_LAYERS;

  // usedIndices 用于显示"已用 N / 15"的计数器
  // 用 Set 去重：因为多个对象可能分配到同一色块，Object.values 会产生重复索引
  const usedIndices = useMemo(() => new Set(Object.values(assignments)), [assignments]);

  const handleClear = useCallback((e: React.MouseEvent, colorIndex: number) => {
    e.stopPropagation();
    pushHistory();
    clearLayer(colorIndex);
  }, [pushHistory, clearLayer]);

  return (
    <div className="flex flex-col gap-2 p-3 bg-gray-900 border-t border-gray-700">
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-400 uppercase tracking-wider">对象分组</span>
        <span className="text-xs text-gray-500">
          {usedIndices.size} / {MAX_LAYERS} used
        </span>
      </div>

      {/* Color swatches */}
      <div className="flex gap-2 flex-wrap">
        {Array.from({ length: displayCount }, (_, i) => i).map((i) => {
          const color = LAYER_COLORS[i];
          const objectsInLayer = objects.filter((o) => assignments[o.id] === i);
          const isActive = selectedLayerIndex === i;

          return (
            <div key={i} className="relative group" title={`Layer ${i + 1} (${objectsInLayer.length} objects)`}>
              {/*
                点击已选中的色块时传入 null，即取消选中（toggle 行为）
                这样用户无需额外操作即可退出分配模式
              */}
              <button
            onClick={() => selectLayer(isActive ? null : i)}
                className={`
                  w-10 h-10 rounded-lg border-2 transition-all duration-150 flex items-center justify-center
                  ${isActive ? 'border-white scale-110 shadow-lg' : 'border-transparent hover:border-gray-500'}
                `}
                style={{ backgroundColor: color }}
              >
                {objectsInLayer.length > 0 && (
                  <span className="text-white text-xs font-bold drop-shadow">
                    {objectsInLayer.length}
                  </span>
                )}
              </button>

              {/* Clear button on hover */}
              {objectsInLayer.length > 0 && (
                <button
                  onClick={(e) => handleClear(e, i)}
                  className="absolute -top-1 -right-1 bg-red-600 rounded-full p-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
                  title="Clear layer"
                >
                  <Trash2 size={10} className="text-white" />
                </button>
              )}

              {/* Active indicator */}
              {isActive && (
                <div className="absolute -bottom-1 left-1/2 -translate-x-1/2 w-2 h-2 bg-white rounded-full" />
              )}
            </div>
          );
        })}

        {/* Add layer placeholder — if fewer than 15 used */}
        {displayCount < MAX_LAYERS && displayCount > 0 && (
          <button
            onClick={() => {
              // Find next unused slot
              const next = displayCount;
              if (next < MAX_LAYERS) selectLayer(next);
            }}
            className="w-10 h-10 rounded-lg border-2 border-dashed border-gray-600 hover:border-gray-400 flex items-center justify-center text-gray-500 hover:text-gray-300 transition-colors"
            title="Add new layer"
          >
            +
          </button>
        )}
      </div>

      {/* Hint */}
            {/* 提示文案：告知用户当前工作流程 */}
      {/* 选中色块 → 点击画布中的对象完成分配 → 分配完成后可取消选中继续浏览 */}
      <p className="text-xs text-gray-600">
        {selectedLayerIndex !== null
          ? `点击画布中物体分配到分组 ${selectedLayerIndex + 1}`
          : '选择分组颜色，再点击画布中物体进行分配'}
      </p>
    </div>
  );
}
