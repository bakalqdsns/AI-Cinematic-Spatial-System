// ─────────────────────────────────────────────────────────────────────────────
// ExportPanel — 3D viewport screenshot export
// ─────────────────────────────────────────────────────────────────────────────
import { useState, useCallback } from 'react';
import { Download, X, Image, Box } from 'lucide-react';

interface ExportPanelProps {
  /** Pass a ref to the Canvas DOM element (gl.domElement) */
  canvasRef: React.RefObject<HTMLCanvasElement | null>;
}

export function ExportPanel({ canvasRef }: ExportPanelProps) {
  const [expanded, setExpanded] = useState(false);

  const handleExportPNG = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const dataUrl = canvas.toDataURL('image/png');
    const link = document.createElement('a');
    link.download = `aicss-3d-${Date.now()}.png`;
    link.href = dataUrl;
    link.click();
  }, [canvasRef]);

  return (
    <div className="absolute bottom-3 right-3 z-10">
      {expanded ? (
        <div className="bg-gray-900/95 border border-gray-700 rounded-xl p-3 flex flex-col gap-2 shadow-xl">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-gray-200">导出 3D 视图</span>
            <button
              onClick={() => setExpanded(false)}
              className="p-1 hover:bg-gray-700 rounded transition-colors"
            >
              <X size={14} className="text-gray-400" />
            </button>
          </div>

          <button
            onClick={handleExportPNG}
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition-colors"
          >
            <Image size={14} />
            导出 PNG 截图
          </button>

          <div className="flex gap-2">
            <button
              onClick={() => setExpanded(false)}
              className="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-700 hover:bg-gray-600 text-gray-300 text-xs transition-colors"
            >
              关闭
            </button>
          </div>

          <p className="text-[10px] text-gray-500">截图分辨率与当前视口一致</p>
        </div>
      ) : (
        <button
          onClick={() => setExpanded(true)}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-gray-800/90 hover:bg-gray-700 text-gray-300 text-xs font-medium border border-gray-700 transition-colors shadow-lg"
          title="导出 3D 视图"
        >
          <Download size={14} />
          导出
        </button>
      )}
    </div>
  );
}
