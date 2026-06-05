// ─────────────────────────────────────────────────────────────────────────────
// App — Main layout: top toolbar + split pane (2D editor | 3D viewer)
// ─────────────────────────────────────────────────────────────────────────────
import { useCallback, useRef, useState, useEffect } from 'react';
import { Upload, Play, Undo2, Redo2, Film, Camera, RefreshCw, Key } from 'lucide-react';
import { ImageCanvas } from './components/ImageCanvas';
import { LayerSelector } from './components/LayerSelector';
import { Viewer3D } from './components/Viewer3D';
import { SplitControls } from './components/SplitControls';
import { useAppStore } from './store/useAppStore';
import { analyzeImage, generateDepth } from './services/aicssService';

const TARGET_W = 1920;
const TARGET_H = 1080;

function autoResizeTo1920x1080(file: File): Promise<{ dataUrl: string; base64: string }> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const src = e.target?.result as string;
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement('canvas');
        canvas.width = TARGET_W;
        canvas.height = TARGET_H;
        const ctx = canvas.getContext('2d')!;

        const srcW = img.naturalWidth;
        const srcH = img.naturalHeight;
        const srcRatio = srcW / srcH;
        const tgtRatio = TARGET_W / TARGET_H;

        let drawW: number, drawH: number, drawX: number, drawY: number;
        if (srcRatio > tgtRatio) {
          // Source wider → fit height, fill width
          drawH = TARGET_H;
          drawW = Math.round(drawH * srcRatio);
          drawX = Math.round((TARGET_W - drawW) / 2);
          drawY = 0;
        } else {
          // Source taller → fit width, fill height
          drawW = TARGET_W;
          drawH = Math.round(drawW / srcRatio);
          drawX = 0;
          drawY = Math.round((TARGET_H - drawH) / 2);
        }

        // Black fill for letterbox/pillarbox
        ctx.fillStyle = '#000000';
        ctx.fillRect(0, 0, TARGET_W, TARGET_H);
        ctx.drawImage(img, drawX, drawY, drawW, drawH);

        const dataUrl = canvas.toDataURL('image/png');
        const base64 = dataUrl.split(',')[1] || '';
        resolve({ dataUrl, base64 });
      };
      img.onerror = reject;
      img.src = src;
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

// ─── Toolbar ────────────────────────────────────────────────────────────────────
function Toolbar() {
  const {
    originalImageUrl,
    analysisResult,
    isAnalyzing,
    editMode,
    setEditMode,
    undo,
    redo,
    canUndo,
    canRedo,
    setIsAnalyzing,
    setAnalysisResult,
    setAnalysisError,
    croppedImageUrl,
  } = useAppStore();

  const dashscopeApiKey = useAppStore((s) => s.dashscopeApiKey);
  const setDashscopeApiKey = useAppStore((s) => s.setDashscopeApiKey);

  const imageUrl = originalImageUrl || croppedImageUrl || '';

  const handleAnalyze = async () => {
    if (!imageUrl) return;
    setIsAnalyzing(true);
    setAnalysisError(null);
    try {
      // Run /analyze and /depth in parallel — both pipelines are independent
      const [result, depthResult] = await Promise.all([
        analyzeImage(imageUrl, 'shot_001', dashscopeApiKey),
        generateDepth(imageUrl),
      ]);
      if (result.vlmDetectedScene || result.vlmDetectedClasses?.length) {
        console.group('[VLM Detection]');
        console.log('Scene:', result.vlmDetectedScene);
        console.log('Classes:', result.vlmDetectedClasses?.join(', '));
        console.log('Full result:', result);
        console.groupEnd();
      }
      setAnalysisResult(result);
      // depthModeResult drives LayerSelector + Viewer3D in imageMode='depth'
      useAppStore.getState().setDepthModeResult(depthResult);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setAnalysisError(msg);
    } finally {
      setIsAnalyzing(false);
    }
  };

  return (
    <header className="flex items-center gap-3 px-4 py-3 bg-gray-950 border-b border-gray-800">
      {/* Logo */}
      <div className="flex items-center gap-2 mr-2">
        <Film size={22} className="text-blue-400" />
        <span className="text-white font-bold text-lg tracking-tight">AICSS</span>
      </div>

      {/* DashScope API Key */}
      <div className="flex items-center gap-2 mr-2">
        <Key size={16} className="text-gray-400" />
        <input
          type="password"
          value={dashscopeApiKey}
          onChange={(e) => setDashscopeApiKey(e.target.value)}
          placeholder="API Key"
          className="w-32 px-2 py-1.5 rounded bg-gray-800 border border-gray-600 text-gray-200 text-xs
            placeholder-gray-500 focus:outline-none focus:border-blue-500 transition-colors"
          spellCheck={false}
        />
      </div>

      {/* Import image */}
      <button
        onClick={() => document.getElementById('aicss-file-input')?.click()}
        className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-200 text-sm font-medium transition-colors"
      >
        <Upload size={16} />
        Import Image
      </button>

      {/* Analyze */}
      <button
        onClick={handleAnalyze}
        disabled={!imageUrl || isAnalyzing}
        className={`
          flex items-center gap-2 px-4 py-2 rounded-lg font-medium text-sm transition-all
          ${!imageUrl || isAnalyzing
            ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
            : 'bg-blue-600 hover:bg-blue-500 text-white active:scale-95'}
        `}
      >
        {isAnalyzing ? <RefreshCw size={16} className="animate-spin" /> : <Play size={16} />}
        {isAnalyzing ? 'Analyzing...' : 'Analyze'}
      </button>

      <div className="w-px h-6 bg-gray-700" />

      <button onClick={undo} disabled={!canUndo()} title="Undo (Ctrl+Z)"
        className="p-2 rounded-lg hover:bg-gray-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors">
        <Undo2 size={18} className="text-gray-300" />
      </button>
      <button onClick={redo} disabled={!canRedo()} title="Redo (Ctrl+Y)"
        className="p-2 rounded-lg hover:bg-gray-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors">
        <Redo2 size={18} className="text-gray-300" />
      </button>

      <div className="w-px h-6 bg-gray-700" />

      <div className="flex rounded-lg overflow-hidden border border-gray-600">
        <button
          onClick={() => setEditMode('director')}
          className={`
            flex items-center gap-1.5 px-3 py-2 text-xs font-semibold uppercase tracking-wider transition-colors
            ${editMode === 'director' ? 'bg-purple-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}
          `}
        >
          <Film size={14} />
          Director
        </button>
        <button
          onClick={() => setEditMode('camera')}
          className={`
            flex items-center gap-1.5 px-3 py-2 text-xs font-semibold uppercase tracking-wider transition-colors
            ${editMode === 'camera' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}
          `}
        >
          <Camera size={14} />
          Camera
        </button>
      </div>

      <div className="flex-1" />

      {analysisResult && (
        <div className="flex items-center gap-3 text-xs text-gray-500">
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-green-400" />
            {analysisResult.objects.length} objects
          </span>
          <span>{analysisResult.analysisId}</span>
        </div>
      )}
    </header>
  );
}

// ─── 2D Panel ──────────────────────────────────────────────────────────────────
function Panel2D() {
  const analysisResult = useAppStore((s) => s.analysisResult);
  const croppedImageUrl = useAppStore((s) => s.croppedImageUrl);
  const originalImageBase64 = useAppStore((s) => s.originalImageBase64);
  const originalImageUrl = useAppStore((s) => s.originalImageUrl);
  const imageWidth = useAppStore((s) => s.imageWidth);
  const imageHeight = useAppStore((s) => s.imageHeight);
  const imageMode = useAppStore((s) => s.imageMode);
  const setImageMode = useAppStore((s) => s.setImageMode);

  const imageUrl = analysisResult?.depthMapUrl
    || croppedImageUrl
    || (originalImageBase64 ? `data:image/png;base64,${originalImageBase64}` : '');

  const originalUrl = originalImageUrl || (originalImageBase64 ? `data:image/png;base64,${originalImageBase64}` : '');

  // Depth-mode image URL (displayed when imageMode='depth' but analysisResult is null)
  const depthImageUrl = useAppStore((s) => s.depthModeResult)?.depthMapUrl ?? '';

  // Effective background URL for the ImageCanvas
  const effectiveImageUrl = imageMode === 'depth'
    ? (imageUrl || depthImageUrl)
    : (originalUrl || imageUrl);

  const aspect = imageWidth && imageHeight ? imageWidth / imageHeight : 16 / 9;
  const canvasWidth = 800;
  const canvasHeight = Math.round(canvasWidth / aspect);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-800 bg-gray-900">
        <span className="text-xs text-gray-500 uppercase tracking-wider mr-1">View:</span>
        <div className="flex rounded-lg overflow-hidden border border-gray-600">
          <button
            onClick={() => setImageMode('depth')}
            className={`px-3 py-1 text-xs font-medium transition-colors ${
              imageMode === 'depth' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'
            }`}
          >
            Depth
          </button>
          <button
            onClick={() => setImageMode('original')}
            className={`px-3 py-1 text-xs font-medium transition-colors ${
              imageMode === 'original' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'
            }`}
          >
            Original
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        {effectiveImageUrl ? (
          <ImageCanvas width={canvasWidth || 800} height={canvasHeight || 450} />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-gray-600 bg-gray-900">
            <div className="text-center space-y-2">
              <Upload size={40} className="mx-auto opacity-30" />
              <p className="text-sm">Import an image to begin</p>
            </div>
          </div>
        )}
      </div>

      {(analysisResult || useAppStore((s) => s.depthModeResult) !== null) && <LayerSelector />}
      {analysisResult && <SplitControls />}
    </div>
  );
}

// ─── App ──────────────────────────────────────────────────────────────────────
export default function App() {
  const [isDragging, setIsDragging] = useState(false);
  const [splitRatio, setSplitRatio] = useState(50);
  const containerRef = useRef<HTMLDivElement>(null);

  const setImage = useAppStore((s) => s.setImage);
  const setCroppedImage = useAppStore((s) => s.setCroppedImage);

  // Restore last session on mount
  useEffect(() => {
    (async () => {
      try {
        const { listSessions, loadSession, blobToUrl } = await import('./utils/db');
        const sessions = await listSessions();
        if (sessions.length === 0) return;
        const last = sessions[0];
        const session = await loadSession(last.id);
        if (!session) return;
        if (session.croppedImageBlob) {
          const url = blobToUrl(session.croppedImageBlob);
          setCroppedImage(url, session.cropParams ?? null);
        }
      } catch (err) {
        console.warn('Failed to restore session:', err);
      }
    })();
  }, [setCroppedImage]);

  // Auto-resize to 1920x1080 on import
  const handleFileChange = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      e.target.value = '';

      const { dataUrl, base64 } = await autoResizeTo1920x1080(file);
      setImage(dataUrl, base64, TARGET_W, TARGET_H);
      setCroppedImage(dataUrl, null);
    },
    [setImage, setCroppedImage],
  );

  // Split pane drag
  const handleMouseDown = useCallback(() => setIsDragging(true), []);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!isDragging || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      setSplitRatio(Math.max(20, Math.min(80, ((e.clientX - rect.left) / rect.width) * 100)));
    };
    const onUp = () => setIsDragging(false);
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [isDragging]);

  return (
    <>
      {/* Hidden file input */}
      <input
        id="aicss-file-input"
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handleFileChange}
      />

      <div
        className="flex flex-col h-screen w-screen overflow-hidden bg-gray-950 text-white select-none"
        style={{ fontFamily: 'system-ui, -apple-system, sans-serif' }}
      >
        <Toolbar />

        <div ref={containerRef} className="flex flex-1 overflow-hidden">
          {/* 2D Panel */}
          <div
            className="overflow-hidden border-r border-gray-800 flex-shrink-0"
            style={{ width: `${splitRatio}%` }}
          >
            <Panel2D />
          </div>

          {/* Resize handle */}
          <div
            className={`w-1 cursor-col-resize flex-shrink-0 transition-colors ${
              isDragging ? 'bg-blue-500' : 'bg-gray-800 hover:bg-gray-600'
            }`}
            onMouseDown={handleMouseDown}
          />

          {/* 3D Panel */}
          <div className="flex-1 overflow-hidden">
            <Viewer3D />
          </div>
        </div>
      </div>
    </>
  );
}
