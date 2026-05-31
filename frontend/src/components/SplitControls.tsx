// ─────────────────────────────────────────────────────────────────────────────
// SplitControls — split image, generate 3D, reset
// ─────────────────────────────────────────────────────────────────────────────
import { useState } from 'react';
import { useAppStore } from '../store/useAppStore';
import { generateBillboard } from '../services/aicssService';
import { Scissors, RotateCcw, Loader2, CheckCircle, AlertCircle } from 'lucide-react';

export function SplitControls() {
  const analysisResult = useAppStore((s) => s.analysisResult);
  const originalImageBase64 = useAppStore((s) => s.originalImageBase64);
  const originalImageUrl = useAppStore((s) => s.originalImageUrl);
  const assignments = useAppStore((s) => s.assignments);
  const billboardAssets = useAppStore((s) => s.billboardAssets);
  const setBillboardAsset = useAppStore((s) => s.setBillboardAsset);
  const clearAllAssignments = useAppStore((s) => s.clearAllAssignments);
  const reset = useAppStore((s) => s.reset);

  const [splitting, setSplitting] = useState(false);
  const [splitProgress, setSplitProgress] = useState(0);
  const [splitError, setSplitError] = useState<string | null>(null);
  const [splitDone, setSplitDone] = useState(false);

  const objects = analysisResult?.objects ?? [];
  const assignedObjects = objects.filter((o) => assignments[o.id] !== undefined);
  const hasAssets = Object.keys(billboardAssets).length > 0;

  const imageUrl = originalImageUrl || (originalImageBase64 ? `data:image/png;base64,${originalImageBase64}` : '');

  const handleSplit = async () => {
    if (!imageUrl || assignedObjects.length === 0) return;

    setSplitting(true);
    setSplitError(null);
    setSplitProgress(0);
    setSplitDone(false);

    let completed = 0;
    for (const obj of assignedObjects) {
      try {
        const rgbaUrl = await generateBillboard(imageUrl, obj.id, obj.boundingBox, obj.polygon);
        setBillboardAsset(obj.id, rgbaUrl);
        completed++;
        setSplitProgress(Math.round((completed / assignedObjects.length) * 100));
      } catch (err) {
        console.error(`Failed to generate billboard for ${obj.id}:`, err);
        // Continue with other objects
        completed++;
        setSplitProgress(Math.round((completed / assignedObjects.length) * 100));
      }
    }

    setSplitting(false);
    setSplitDone(true);
  };

  const handleReset = () => {
    reset();
    setSplitDone(false);
    setSplitError(null);
  };

  const assignedCount = assignedObjects.length;

  return (
    <div className="flex flex-col gap-3 p-4 bg-gray-900 border-t border-gray-700">
      {/* Progress bar */}
      {splitting && (
        <div className="flex items-center gap-3">
          <Loader2 size={16} className="text-blue-400 animate-spin" />
          <div className="flex-1 h-2 bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 transition-all duration-300"
              style={{ width: `${splitProgress}%` }}
            />
          </div>
          <span className="text-xs text-gray-400">{splitProgress}%</span>
        </div>
      )}

      {/* Status */}
      {splitDone && !splitting && (
        <div className="flex items-center gap-2 text-green-400">
          <CheckCircle size={16} />
          <span className="text-sm">{Object.keys(billboardAssets).length} billboards generated</span>
        </div>
      )}

      {splitError && (
        <div className="flex items-center gap-2 text-red-400">
          <AlertCircle size={16} />
          <span className="text-sm">{splitError}</span>
        </div>
      )}

      {/* Buttons */}
      <div className="flex gap-2">
        <button
          onClick={handleSplit}
          disabled={splitting || assignedCount === 0 || !imageUrl}
          className={`
            flex items-center gap-2 px-4 py-2 rounded-lg font-medium text-sm transition-all
            ${splitting || assignedCount === 0 || !imageUrl
              ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
              : 'bg-blue-600 hover:bg-blue-500 text-white active:scale-95'}
          `}
        >
          <Scissors size={16} />
          {splitting ? 'Splitting...' : 'Split Image'}
          {assignedCount > 0 && !splitting && (
            <span className="ml-1 bg-blue-700 rounded px-1.5 py-0.5 text-xs">{assignedCount}</span>
          )}
        </button>

        <button
          onClick={handleReset}
          className="flex items-center gap-2 px-4 py-2 rounded-lg font-medium text-sm
            bg-gray-700 hover:bg-gray-600 text-gray-200 transition-all active:scale-95"
        >
          <RotateCcw size={16} />
          Reset
        </button>

        {/* Status hint */}
        {!analysisResult && (
          <span className="ml-auto text-xs text-gray-500 self-center">
            Import and analyze an image first
          </span>
        )}
        {analysisResult && assignedCount === 0 && (
          <span className="ml-auto text-xs text-gray-500 self-center">
            Assign objects to layers first
          </span>
        )}
      </div>
    </div>
  );
}
