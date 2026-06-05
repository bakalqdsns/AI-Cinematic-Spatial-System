// ─────────────────────────────────────────────────────────────────────────────
// LayerSelector — 15 color swatches, shows which layer is active
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

  // Show all MAX_LAYERS swatches so the user can always pick a layer to assign to
  const displayCount = MAX_LAYERS;

  // Keep usedIndices for the counter display
  const usedIndices = useMemo(() => new Set(Object.values(assignments)), [assignments]);

  const handleClear = useCallback((e: React.MouseEvent, colorIndex: number) => {
    e.stopPropagation();
    pushHistory();
    clearLayer(colorIndex);
  }, [pushHistory, clearLayer]);

  return (
    <div className="flex flex-col gap-2 p-3 bg-gray-900 border-t border-gray-700">
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-400 uppercase tracking-wider">Layers</span>
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
      <p className="text-xs text-gray-600">
        {selectedLayerIndex !== null
          ? `Click objects to assign to Layer ${selectedLayerIndex + 1}`
          : 'Select a layer, then click objects to assign'}
      </p>
    </div>
  );
}
