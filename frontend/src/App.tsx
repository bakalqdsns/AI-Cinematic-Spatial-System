// ─────────────────────────────────────────────────────────────────────────────
// App — Main layout: top toolbar + split pane (2D editor | 3D viewer)
// ─────────────────────────────────────────────────────────────────────────────
import { useCallback, useRef, useState, useEffect } from 'react';
import { Upload, Play, Undo2, Redo2, Film, Camera, RefreshCw } from 'lucide-react';
import { ImageCanvas } from './components/ImageCanvas';
import { LayerSelector } from './components/LayerSelector';
import { Viewer3D } from './components/Viewer3D';
import { SplitControls } from './components/SplitControls';
import { useAppStore } from './store/useAppStore';
import { analyzeImage } from './services/aicssService';

// ─── Image loader ──────────────────────────────────────────────────────────────
function useImageLoader() {
  const setImage = useAppStore((s) => s.setImage);

  const loadFromFile = useCallback(
    async (file: File) => {
      return new Promise<void>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = (e) => {
          const dataUrl = e.target?.result as string;
          const img = new Image();
          img.onload = () => {
            // Store as base64 without prefix for API calls
            const base64 = dataUrl.split(',')[1] || '';
            setImage(dataUrl, base64, img.width, img.height);
            resolve();
          };
          img.onerror = reject;
          img.src = dataUrl;
        };
        reader.onerror = reject;
        reader.readAsDataURL(file);
      });
    },
    [setImage],
  );

  return { loadFromFile };
}

// ─── Toolbar ────────────────────────────────────────────────────────────────────
function Toolbar() {
  const {
    originalImageUrl,
    originalImageBase64,
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
    segmentationPrompt,
    setSegmentationPrompt,
  } = useAppStore();

  const fileInputRef = useRef<HTMLInputElement>(null);
  const { loadFromFile } = useImageLoader();

  const imageUrl = originalImageUrl || (originalImageBase64 ? `data:image/png;base64,${originalImageBase64}` : '');

  const handleAnalyze = async () => {
    if (!imageUrl) return;
    setIsAnalyzing(true);
    setAnalysisError(null);
    try {
      const result = await analyzeImage(imageUrl, segmentationPrompt);
      setAnalysisResult(result);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setAnalysisError(msg);
      console.error('Analysis failed:', err);
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    await loadFromFile(file);
    e.target.value = '';
  };

  return (
    <header className="flex items-center gap-3 px-4 py-3 bg-gray-950 border-b border-gray-800">
      {/* Logo */}
      <div className="flex items-center gap-2 mr-4">
        <Film size={22} className="text-blue-400" />
        <span className="text-white font-bold text-lg tracking-tight">AICSS</span>
      </div>

      {/* Import image */}
      <button
        onClick={() => fileInputRef.current?.click()}
        className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-200 text-sm font-medium transition-colors"
      >
        <Upload size={16} />
        Import Image
      </button>
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handleFileChange}
      />

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

      {/* Prompt input */}
      <input
        type="text"
        value={segmentationPrompt}
        onChange={(e) => setSegmentationPrompt(e.target.value)}
        placeholder="person,car,building,tree..."
        className="flex-1 min-w-0 max-w-xs px-3 py-2 rounded-lg bg-gray-800 border border-gray-600
          text-gray-200 text-sm placeholder-gray-500 focus:outline-none focus:border-blue-500
          focus:ring-1 focus:ring-blue-500 transition-colors"
        disabled={isAnalyzing}
        spellCheck={false}
      />

      {/* Divider */}
      <div className="w-px h-6 bg-gray-700" />

      {/* Undo / Redo */}
      <button
        onClick={undo}
        disabled={!canUndo()}
        title="Undo (Ctrl+Z)"
        className="p-2 rounded-lg hover:bg-gray-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
      >
        <Undo2 size={18} className="text-gray-300" />
      </button>
      <button
        onClick={redo}
        disabled={!canRedo()}
        title="Redo (Ctrl+Y)"
        className="p-2 rounded-lg hover:bg-gray-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
      >
        <Redo2 size={18} className="text-gray-300" />
      </button>

      {/* Divider */}
      <div className="w-px h-6 bg-gray-700" />

      {/* Mode toggle */}
      <div className="flex rounded-lg overflow-hidden border border-gray-600">
        <button
          onClick={() => setEditMode('director')}
          className={`
            flex items-center gap-1.5 px-3 py-2 text-xs font-semibold uppercase tracking-wider transition-colors
            ${editMode === 'director'
              ? 'bg-purple-600 text-white'
              : 'bg-gray-800 text-gray-400 hover:text-white'}
          `}
        >
          <Film size={14} />
          Director
        </button>
        <button
          onClick={() => setEditMode('camera')}
          className={`
            flex items-center gap-1.5 px-3 py-2 text-xs font-semibold uppercase tracking-wider transition-colors
            ${editMode === 'camera'
              ? 'bg-blue-600 text-white'
              : 'bg-gray-800 text-gray-400 hover:text-white'}
          `}
        >
          <Camera size={14} />
          Camera
        </button>
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Status */}
      {analysisResult && (
        <div className="flex items-center gap-3 text-xs text-gray-500">
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-green-400" />
            {analysisResult.objects.length} objects detected
          </span>
          <span>{analysisResult.analysisId}</span>
        </div>
      )}
    </header>
  );
}

// ─── 2D Panel ──────────────────────────────────────────────────────────────────
function Panel2D() {
  const { analysisResult, originalImageBase64 } = useAppStore();
  const imageMode = useAppStore((s) => s.imageMode);
  const setImageMode = useAppStore((s) => s.setImageMode);
  const imageUrl = analysisResult?.depthMapUrl
    || useAppStore.getState().originalImageUrl
    || (originalImageBase64 ? `data:image/png;base64,${originalImageBase64}` : '');

  // Determine canvas dimensions based on image
  const { imageWidth, imageHeight } = useAppStore();
  const aspect = imageWidth && imageHeight ? imageWidth / imageHeight : 16 / 9;
  const canvasWidth = 800;
  const canvasHeight = Math.round(canvasWidth / aspect);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Image mode toggle */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-800 bg-gray-900">
        <span className="text-xs text-gray-500 uppercase tracking-wider mr-1">View:</span>
        <div className="flex rounded-lg overflow-hidden border border-gray-600">
          <button
            onClick={() => setImageMode('depth')}
            className={`px-3 py-1 text-xs font-medium transition-colors ${
              imageMode === 'depth'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-800 text-gray-400 hover:text-white'
            }`}
          >
            Depth
          </button>
          <button
            onClick={() => setImageMode('original')}
            className={`px-3 py-1 text-xs font-medium transition-colors ${
              imageMode === 'original'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-800 text-gray-400 hover:text-white'
            }`}
          >
            Original
          </button>
        </div>
      </div>

      {/* Image canvas */}
      <div className="flex-1 overflow-auto">
        {imageUrl ? (
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

      {/* Layer selector */}
      {analysisResult && <LayerSelector />}

      {/* Split controls */}
      {analysisResult && <SplitControls />}
    </div>
  );
}

// ─── App ───────────────────────────────────────────────────────────────────────
export default function App() {
  const [splitRatio, setSplitRatio] = useState(50); // percent for left panel
  const [isDragging, setIsDragging] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const handleMouseDown = useCallback(() => {
    setIsDragging(true);
  }, []);

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!isDragging || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const ratio = ((e.clientX - rect.left) / rect.width) * 100;
      setSplitRatio(Math.max(20, Math.min(80, ratio)));
    },
    [isDragging],
  );

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  useEffect(() => {
    const handleGlobalUp = () => setIsDragging(false);
    window.addEventListener('mouseup', handleGlobalUp);
    return () => window.removeEventListener('mouseup', handleGlobalUp);
  }, []);

  return (
    <div
      className="flex flex-col h-screen w-screen overflow-hidden bg-gray-950 text-white select-none"
      style={{ fontFamily: 'system-ui, -apple-system, sans-serif' }}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
    >
      <Toolbar />

      {/* Split panes */}
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
  );
}
