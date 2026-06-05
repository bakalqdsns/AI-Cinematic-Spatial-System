// ─────────────────────────────────────────────────────────────────────────────
// LayerSelector — depth-bucket layers + 15 color swatches for manual assignment
// ─────────────────────────────────────────────────────────────────────────────
import { useMemo, useCallback } from 'react';
import { useAppStore } from '../store/useAppStore';
import { LAYER_COLORS, MAX_LAYERS } from '../types';
import { Trash2 } from 'lucide-react';
import type { DetectedObject, SpatialLayer, DepthBucket } from '../types';

// ─── helpers ────────────────────────────────────────────────────────────────

/**
 * Build SpatialLayer[] from meter-based depth bucket config.
 * Both analyze mode (analysisResult.layers) and depth mode (computed from depthBuckets)
 * use the same shape — this function is for depth mode where the backend
 * hasn't pre-built the layers array.
 */
function computeBucketLayers(
  depthBuckets: DepthBucket[],
  objects: DetectedObject[],
): SpatialLayer[] {
  return depthBuckets.map((bucket, i) => {
    const objectsInBucket = objects.filter((obj) => {
      if (obj.depth == null) return false;
      return obj.depth >= bucket.zMin && obj.depth < bucket.zMax;
    });
    return {
      id: `bucket_${bucket.name}_${i}`,
      name: bucket.name,
      zMin: bucket.zMin,
      zMax: bucket.zMax,
      objects: objectsInBucket,
    };
  });
}

// ─── component ─────────────────────────────────────────────────────────────

export function LayerSelector() {
  const assignments = useAppStore((s) => s.assignments);
  const selectedLayerIndex = useAppStore((s) => s.selectedLayerIndex);
  const analysisResult = useAppStore((s) => s.analysisResult);
  const depthModeResult = useAppStore((s) => s.depthModeResult);
  const imageMode = useAppStore((s) => s.imageMode);
  const selectLayer = useAppStore((s) => s.selectLayer);
  const clearLayer = useAppStore((s) => s.clearLayer);
  const pushHistory = useAppStore((s) => s.pushHistory);

  // Source objects: analyze mode → analysisResult.objects, depth mode → depthModeResult.objects
  const sourceObjects: DetectedObject[] = imageMode === 'depth' && depthModeResult
    ? depthModeResult.objects
    : (analysisResult?.objects ?? []);

  // Bucket layers for display: analyze mode uses pre-built layers from backend,
  // depth mode computes them from depthBuckets.
  const availableLayers: SpatialLayer[] = useMemo(() => {
    if (imageMode === 'depth' && depthModeResult?.depthBuckets) {
      return computeBucketLayers(depthModeResult.depthBuckets, sourceObjects);
    }
    // Analyze mode: backend already bucketed objects into layers
    return analysisResult?.layers ?? [];
  }, [imageMode, depthModeResult, analysisResult, sourceObjects]);

  const usedIndices = useMemo(() => new Set(Object.values(assignments)), [assignments]);

  const handleClear = useCallback((e: React.MouseEvent, colorIndex: number) => {
    e.stopPropagation();
    pushHistory();
    clearLayer(colorIndex);
  }, [pushHistory, clearLayer]);

  // Objects visible under the currently active color swatch
  const objectsInActiveLayer = useMemo(() => {
    if (selectedLayerIndex === null) return sourceObjects;
    const colorIndex = selectedLayerIndex;
    return sourceObjects.filter((o) => assignments[o.id] === colorIndex);
  }, [sourceObjects, assignments, selectedLayerIndex]);

  // Bucket-layer info for the active layer (shows which bucket the selected swatch
  // aligns with, if any)
  const activeLayerInfo = selectedLayerIndex !== null
    ? availableLayers[selectedLayerIndex]
    : null;

  return (
    <div className="flex flex-col gap-2 p-3 bg-gray-900 border-t border-gray-700">
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-400 uppercase tracking-wider">
          {imageMode === 'depth' ? 'Depth Layers' : 'Layers'}
        </span>
        <span className="text-xs text-gray-500">
          {usedIndices.size} / {MAX_LAYERS} used
        </span>
      </div>

      {/* Depth bucket layer bar — shows which buckets exist */}
      {availableLayers.length > 0 && (
        <div className="flex gap-1 mb-1">
          {availableLayers.map((layer, i) => {
            const count = sourceObjects.filter((o) => o.depth >= layer.zMin && o.depth < layer.zMax).length;
            const isActive = selectedLayerIndex === i;
            return (
              <button
                key={layer.id}
                onClick={() => selectLayer(isActive ? null : i)}
                className={`
                  flex-1 text-center py-1 px-1 rounded text-xs font-medium transition-all
                  ${isActive ? 'ring-2 ring-white scale-105' : 'hover:scale-105 opacity-80 hover:opacity-100'}
                `}
                style={{ backgroundColor: LAYER_COLORS[i % LAYER_COLORS.length] }}
                title={`${layer.name} (${layer.zMin}–${layer.zMax}m, ${count} objects)`}
              >
                {layer.name}
              </button>
            );
          })}
        </div>
      )}

      {/* 15 color swatches for manual object assignment */}
      <div className="flex gap-2 flex-wrap">
        {Array.from({ length: MAX_LAYERS }, (_, i) => i).map((i) => {
          const color = LAYER_COLORS[i];
          const objectsInLayer = sourceObjects.filter((o) => assignments[o.id] === i);
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
      </div>

      {/* Hint */}
      <p className="text-xs text-gray-600">
        {selectedLayerIndex !== null
          ? `Click objects to assign to Layer ${selectedLayerIndex + 1}${activeLayerInfo ? ` (${activeLayerInfo.name})` : ''}`
          : imageMode === 'depth'
            ? `${sourceObjects.length} objects across ${availableLayers.length} depth layers`
            : 'Select a layer, then click objects to assign'}
      </p>
    </div>
  );
}
