// ─────────────────────────────────────────────────────────────────────────────
// SplitControls — split image, generate 3D, reset, inpaint
// ─────────────────────────────────────────────────────────────────────────────
import { useState, useCallback } from 'react';
import { useAppStore } from '../store/useAppStore';
import { generateBillboard, inpaintImage } from '../services/aicssService';
import { InpaintPreviewDialog } from './InpaintPreviewDialog';
import { Scissors, Wand2, RotateCcw, Loader2, CheckCircle, AlertCircle } from 'lucide-react';

export function SplitControls() {
  const analysisResult = useAppStore((s) => s.analysisResult);
  const croppedImageUrl = useAppStore((s) => s.croppedImageUrl);
  const originalImageBase64 = useAppStore((s) => s.originalImageBase64);
  const originalImageUrl = useAppStore((s) => s.originalImageUrl);
  const assignments = useAppStore((s) => s.assignments);
  const billboardAssets = useAppStore((s) => s.billboardAssets);
  const setBillboardAsset = useAppStore((s) => s.setBillboardAsset);
  const clearAllAssignments = useAppStore((s) => s.clearAllAssignments);
  const reset = useAppStore((s) => s.reset);
  const inpaintPreviewUrl = useAppStore((s) => s.inpaintPreviewUrl);
  const setInpaintPreview = useAppStore((s) => s.setInpaintPreview);
  const inpaintLoading = useAppStore((s) => s.inpaintLoading);
  const setInpaintLoading = useAppStore((s) => s.setInpaintLoading);
  const inpaintError = useAppStore((s) => s.inpaintError);
  const setInpaintError = useAppStore((s) => s.setInpaintError);
  const dashscopeApiKey = useAppStore((s) => s.dashscopeApiKey);

  const [splitting, setSplitting] = useState(false);
  const [splitProgress, setSplitProgress] = useState(0);
  const [splitError, setSplitError] = useState<string | null>(null);
  const [splitDone, setSplitDone] = useState(false);

  const objects = analysisResult?.objects ?? [];
  const assignedObjects = objects.filter((o) => assignments[o.id] !== undefined);

  // The image used for inpaint: croppedImageUrl (set on import, auto-resized to 1920×1080)
  const effectiveImageUrl =
    croppedImageUrl ||
    originalImageUrl ||
    (originalImageBase64 ? `data:image/png;base64,${originalImageBase64}` : '');

  // ─── Compute inverse mask from assigned object polygons ───────────────────
  const computeInverseMask = useCallback((): Promise<string> => {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement('canvas');
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;
        const ctx = canvas.getContext('2d')!;

        // White background = entire image is edit area by default
        ctx.fillStyle = 'white';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        // Draw assigned object polygons in black = keep area
        ctx.fillStyle = 'black';
        ctx.globalCompositeOperation = 'source-over';

        for (const obj of assignedObjects) {
          const poly = obj.polygon;
          if (poly.length < 3) continue;
          ctx.beginPath();
          const [x0, y0] = poly[0];
          ctx.moveTo(x0 * canvas.width, y0 * canvas.height);
          for (let i = 1; i < poly.length; i++) {
            const [x, y] = poly[i];
            ctx.lineTo(x * canvas.width, y * canvas.height);
          }
          ctx.closePath();
          ctx.fill();
        }

        // Create RGBA canvas: alpha channel = canvas luminance
        // black (keep) -> alpha=0, white (edit) -> alpha=255
        const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
        const rgba = ctx.createImageData(canvas.width, canvas.height);
        for (let i = 0; i < imageData.data.length; i += 4) {
          const gray = imageData.data[i]; // R channel (all same: 0 or 255)
          rgba.data[i] = 255;       // R
          rgba.data[i + 1] = 255;   // G
          rgba.data[i + 2] = 255;   // B
          rgba.data[i + 3] = gray;  // A: 255=white=edit, 0=black=keep
        }
        ctx.putImageData(rgba, 0, 0);

        // Export as RGBA PNG (alpha channel carries the mask)
        resolve(canvas.toDataURL('image/png'));
      };
      img.onerror = () => reject(new Error('Failed to load image for mask generation'));
      img.src = effectiveImageUrl;
    });
  }, [effectiveImageUrl, assignedObjects]);

  // ─── Generate auto-prompt from scene graph ────────────────────────────────
  const generatePrompt = useCallback((): string => {
    if (!analysisResult) return '保持主体结构，自然填补背景区域';
    const labels = assignedObjects.map((o) => o.classLabel).join('、');
    return `保留${labels || '主体'}，自然填补背景区域`;
  }, [analysisResult, assignedObjects]);

  // ─── Split Image ─────────────────────────────────────────────────────────
  const handleSplit = async () => {
    if (!effectiveImageUrl || assignedObjects.length === 0) return;

    setSplitting(true);
    setSplitError(null);
    setSplitProgress(0);
    setSplitDone(false);

    let completed = 0;
    for (const obj of assignedObjects) {
      try {
        const rgbaUrl = await generateBillboard(effectiveImageUrl, obj.id, obj.boundingBox, obj.polygon);
        setBillboardAsset(obj.id, rgbaUrl);
        completed++;
        setSplitProgress(Math.round((completed / assignedObjects.length) * 100));
      } catch (err) {
        console.error(`Failed to generate billboard for ${obj.id}:`, err);
        completed++;
        setSplitProgress(Math.round((completed / assignedObjects.length) * 100));
      }
    }

    setSplitting(false);
    setSplitDone(true);
  };

  // ─── Split & Inpaint ─────────────────────────────────────────────────────
  const handleSplitAndInpaint = async () => {
    if (!effectiveImageUrl || assignedObjects.length === 0) return;
    
    if (!dashscopeApiKey) {
      setInpaintError('请先在顶部输入 DashScope API Key');
      setInpaintLoading(false);
      return;
    }

    setInpaintLoading(true);
    setInpaintError(null);
    setInpaintPreview(null);

    try {
      const maskDataUrl = await computeInverseMask();
      const prompt = generatePrompt();
      const resultUrl = await inpaintImage(effectiveImageUrl, maskDataUrl, prompt, dashscopeApiKey);
      setInpaintPreview(resultUrl);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setInpaintError(msg);
      console.error('Inpaint failed:', err);
    } finally {
      setInpaintLoading(false);
    }
  };

  // ─── Confirm inpaint → replace cropped image ────────────────────────────
  const handleConfirmInpaint = () => {
    if (!inpaintPreviewUrl) return;
    // Convert data URL to base64 for store compatibility
    const base64 = inpaintPreviewUrl.split(',')[1] || '';
    const img = new Image();
    img.onload = () => {
      const { setImage, setCroppedImage, setAnalysisResult, clearAllAssignments } = useAppStore.getState();
      setImage(inpaintPreviewUrl, base64, img.naturalWidth, img.naturalHeight);
      setCroppedImage(inpaintPreviewUrl, null);
      clearAllAssignments();
      setInpaintPreview(null);
      setAnalysisResult(null as never);
    };
    img.src = inpaintPreviewUrl;
  };

  const handleCancelInpaint = () => {
    setInpaintPreview(null);
  };

  const handleReset = () => {
    reset();
    setSplitDone(false);
    setSplitError(null);
    setInpaintPreview(null);
    setInpaintError(null);
  };

  const assignedCount = assignedObjects.length;
  const hasImage = !!effectiveImageUrl;
  const canSplit = hasImage && assignedCount > 0;
  const canInpaint = hasImage && assignedCount > 0;

  return (
    <>
      <div className="flex flex-col gap-3 p-4 bg-gray-900 border-t border-gray-700">
        {/* Inpaint loading */}
        {inpaintLoading && (
          <div className="flex items-center gap-3">
            <Loader2 size={16} className="text-purple-400 animate-spin" />
            <span className="text-xs text-gray-400">正在调用 DashScope 局部重绘...</span>
          </div>
        )}

        {/* Inpaint error */}
        {inpaintError && (
          <div className="flex items-center gap-2 text-red-400">
            <AlertCircle size={16} />
            <span className="text-sm">{inpaintError}</span>
          </div>
        )}

        {/* Split progress bar */}
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

        {/* Split done */}
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
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={handleSplit}
            disabled={splitting || inpaintLoading || !canSplit}
            className={`
              flex items-center gap-2 px-4 py-2 rounded-lg font-medium text-sm transition-all
              ${splitting || inpaintLoading || !canSplit
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
            onClick={handleSplitAndInpaint}
            disabled={splitting || inpaintLoading || !canInpaint}
            className={`
              flex items-center gap-2 px-4 py-2 rounded-lg font-medium text-sm transition-all
              ${splitting || inpaintLoading || !canInpaint
                ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
                : 'bg-purple-600 hover:bg-purple-500 text-white active:scale-95'}
            `}
          >
            {inpaintLoading ? <Loader2 size={16} className="animate-spin" /> : <Wand2 size={16} />}
            {inpaintLoading ? '补全中...' : 'Split & Inpaint'}
            {assignedCount > 0 && !inpaintLoading && (
              <span className="ml-1 bg-purple-700 rounded px-1.5 py-0.5 text-xs">{assignedCount}</span>
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
              Import and analyze first
            </span>
          )}
          {analysisResult && assignedCount === 0 && (
            <span className="ml-auto text-xs text-gray-500 self-center">
              Assign objects to layers first
            </span>
          )}
        </div>
      </div>

      {/* Inpaint preview dialog */}
      {inpaintPreviewUrl && (
        <InpaintPreviewDialog
          originalUrl={effectiveImageUrl}
          resultUrl={inpaintPreviewUrl}
          onConfirm={handleConfirmInpaint}
          onCancel={handleCancelInpaint}
        />
      )}
    </>
  );
}
