// ─────────────────────────────────────────────────────────────────────────────
// InpaintPreviewDialog — confirm or reject inpaint result
// ─────────────────────────────────────────────────────────────────────────────
import { Check, X } from 'lucide-react';

interface Props {
  originalUrl: string;
  resultUrl: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function InpaintPreviewDialog({ originalUrl, resultUrl, onConfirm, onCancel }: Props) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
      <div className="flex flex-col w-full max-w-5xl max-h-[92vh] bg-gray-900 rounded-xl overflow-hidden shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-700">
          <h2 className="text-white font-semibold text-base">补全结果预览</h2>
          <button
            onClick={onCancel}
            className="p-1 rounded hover:bg-gray-700 text-gray-400 hover:text-white transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        {/* Side-by-side comparison */}
        <div className="flex flex-1 overflow-hidden">
          <div className="flex-1 flex flex-col border-r border-gray-700">
            <div className="px-3 py-2 text-xs text-gray-500 border-b border-gray-800">原图</div>
            <div className="flex-1 overflow-hidden bg-black flex items-center justify-center">
              <img
                src={originalUrl}
                alt="Original"
                className="max-w-full max-h-full object-contain"
              />
            </div>
          </div>
          <div className="flex-1 flex flex-col">
            <div className="px-3 py-2 text-xs text-gray-500 border-b border-gray-800">补全结果</div>
            <div className="flex-1 overflow-hidden bg-black flex items-center justify-center">
              <img
                src={resultUrl}
                alt="Inpainted"
                className="max-w-full max-h-full object-contain"
              />
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-3 px-5 py-4 border-t border-gray-700">
          <button
            onClick={onCancel}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium
              bg-gray-700 hover:bg-gray-600 text-gray-300 transition-colors"
          >
            <X size={16} />
            取消
          </button>
          <button
            onClick={onConfirm}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium
              bg-green-600 hover:bg-green-500 text-white transition-colors"
          >
            <Check size={16} />
            确认替换
          </button>
        </div>
      </div>
    </div>
  );
}
