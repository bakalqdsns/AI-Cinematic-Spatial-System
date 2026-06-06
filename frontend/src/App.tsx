// ─────────────────────────────────────────────────────────────────────────────
// App — Main layout: top toolbar + split pane (2D editor | 3D viewer)
// ─────────────────────────────────────────────────────────────────────────────
import { useCallback, useRef, useState, useEffect } from 'react';
import { Upload, Play, Undo2, Redo2, Film, Camera, RefreshCw, Key, Sparkles } from 'lucide-react';
import type { DepthLayerKey } from './types';
import type { DepthLayerDioramaAsset } from './types';
import { ImageCanvas } from './components/ImageCanvas';
import { LayerSelector } from './components/LayerSelector';
import { Viewer3D } from './components/Viewer3D';
import { SplitControls } from './components/SplitControls';
import { useAppStore } from './store/useAppStore';
import { analyzeImage } from './services/aicssService';
import { splitDepthLayers } from './utils/depthSplit';
import { generatePaperLayer } from './services/aicssService';

const TARGET_W = 1920;
const TARGET_H = 1080;

// 将任意比例图像缩放填充到 1920×1080，边缘留黑（letterbox/pillarbox）。
// 策略：取原图宽高比与目标比例 16:9 比较——
//
//   - 原图更宽（如 21:9 带鱼屏）：高度填满，高度方向居中，
//     宽度方向会超出画布，用 fillRect 填黑边（左右黑条）
//   - 原图更高（如 9:16 手机竖图）：宽度填满，宽度方向居中，
//     高度方向会超出画布，用 fillRect 填黑边（上下黑条）
//
// 这样 ML pipeline 收到的永远是标准化 1920×1080 输入，
// 避免原图尺寸差异导致 depth/segmentation 模型输出分辨率不一致。
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
    autoGenPhase,
    autoGenProgress,
    autoGenError,
    setAutoGenPhase,
    setAutoGenProgress,
    setAutoGenError,
    vlmHint,
    setVlmHint,
    analysisError,
  } = useAppStore();

  const dashscopeApiKey = useAppStore((s) => s.dashscopeApiKey);
  const setDashscopeApiKey = useAppStore((s) => s.setDashscopeApiKey);

  const imageUrl = originalImageUrl || croppedImageUrl || '';

  const handleAnalyze = async () => {
    if (!imageUrl) return;
    setIsAnalyzing(true);
    setAnalysisError(null);
    setVlmHint('正在识别场景内容...');
    try {
      const result = await analyzeImage(imageUrl, 'shot_001', dashscopeApiKey);
      if (result.vlmDetectedClasses?.length) {
        setVlmHint(`场景：${result.vlmDetectedScene || '未知'} | 识别到 ${result.vlmDetectedClasses.length} 个类别`);
      } else {
        setVlmHint('未能识别任何物体，请检查 API Key 或图片质量');
      }
      setAnalysisResult(result);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setAnalysisError(msg);
      setVlmHint(`分析失败：${msg}`);
    } finally {
      setIsAnalyzing(false);
    }
  };

  // One-click auto-generate: analyze → depth split → paper layer generation
  const handleAutoGenerate = async () => {
    if (!imageUrl || !dashscopeApiKey) return;

    setAutoGenPhase('analyzing');
    setAutoGenProgress(5);
    setAutoGenError(null);
    setIsAnalyzing(true);

    try {
      const result = await analyzeImage(imageUrl, 'shot_001', dashscopeApiKey);
      setAnalysisResult(result);
      setAutoGenProgress(30);

      if (result.vlmDetectedClasses?.length) {
        setVlmHint(`场景：${result.vlmDetectedScene || '未知'} | 识别到 ${result.vlmDetectedClasses.length} 个类别`);
      } else {
        setVlmHint('未能识别任何物体');
      }

      // Phase 2: depth split (frontend compute)
      setAutoGenPhase('splitting');
      setAutoGenProgress(40);

      const depthSplit = await splitDepthLayers(
        result.depthMapUrl,
        imageUrl,
        { foregroundMin: 192, midgroundMin: 128, backgroundMin: 64 },
      );

      setAutoGenProgress(60);

      // Phase 3: paper layer generation (backend)
      setAutoGenPhase('generating');

      const LAYER_ORDER: DepthLayerKey[] = ['foreground', 'midground', 'background', 'sky'];
      const layerAssets: Partial<Record<DepthLayerKey, DepthLayerDioramaAsset>> = {};

      await Promise.all(
        LAYER_ORDER.map(async (layer, idx) => {
          const layerUrl = depthSplit[layer];
          if (!layerUrl) return;
          const textures = await generatePaperLayer(layerUrl, null, {});
          const asset: DepthLayerDioramaAsset = {
            layer,
            rgbaUrl: textures.paper_style_url,
            thicknessGrayUrl: textures.thickness_gray_url,
            normalMapUrl: textures.normal_map_url,
            outlinedUrl: textures.outlined_url,
            paperStyleUrl: textures.paper_style_url,
          };
          layerAssets[layer] = asset;
          setAutoGenProgress(60 + Math.round(((idx + 1) / 4) * 35));
        }),
      );

      // Write all layer assets to store
      const { setDepthSplitResult, setDepthLayerDioramaAsset, setDepthLayerBillboardAsset, setDioramaMode, setImageMode, clearDepthLayerBillboardAssets, setDepthSplitConfirmed, setSelectedDepthLayer } = useAppStore.getState();
      setDepthSplitResult(depthSplit);
      // Write billboard assets (RGBA PNG from depth split) for Billboard mode
      clearDepthLayerBillboardAssets();
      Object.entries(depthSplit).forEach(([layer, rgbaUrl]) => {
        setDepthLayerBillboardAsset(layer as DepthLayerKey, rgbaUrl);
      });
      // Write diorama assets (paper textures) for Paper Diorama mode
      Object.entries(layerAssets).forEach(([layer, asset]) => {
        if (asset) setDepthLayerDioramaAsset(layer as DepthLayerKey, asset);
      });
      setDepthSplitConfirmed(true);
      setSelectedDepthLayer('foreground');
      setDioramaMode('paper');
      setImageMode('original');

      setAutoGenPhase('done');
      setAutoGenProgress(100);
      setVlmHint(null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setAutoGenPhase('error');
      setAutoGenError(msg);
    } finally {
      setIsAnalyzing(false);
    }
  };

  const isAutoGenerating = autoGenPhase !== 'idle' && autoGenPhase !== 'done' && autoGenPhase !== 'error';
  const autoGenDone = autoGenPhase === 'done';
  const autoGenHasError = autoGenPhase === 'error';

  const getAutoGenLabel = () => {
    switch (autoGenPhase) {
      case 'analyzing': return 'AI 分析中...';
      case 'splitting': return '深度分层中...';
      case 'generating': return '生成纹理中...';
      case 'done': return '生成完成';
      case 'error': return '生成失败';
      default: return '一键生成';
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

      {/* One-click Auto Generate */}
      <button
        onClick={handleAutoGenerate}
        disabled={!imageUrl || !dashscopeApiKey || isAutoGenerating}
        title={!dashscopeApiKey ? '请先输入 DashScope API Key' : '一键完成分析、分层与纸雕生成'}
        className={`
          flex items-center gap-2 px-4 py-2 rounded-lg font-medium text-sm transition-all
          ${!imageUrl || !dashscopeApiKey || isAutoGenerating
            ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
            : 'bg-green-600 hover:bg-green-500 text-white active:scale-95'}
        `}
      >
        {isAutoGenerating ? <RefreshCw size={16} className="animate-spin" /> : <Sparkles size={16} />}
        {getAutoGenLabel()}
        {isAutoGenerating && autoGenProgress > 0 && (
          <span className="ml-1 text-xs opacity-75">{autoGenProgress}%</span>
        )}
      </button>

      {/* VLM hint area */}
      {vlmHint && (
        <span className={`text-xs px-2 py-1 rounded ${
          autoGenHasError || (analysisError && vlmHint.includes('失败'))
            ? 'text-red-400 bg-red-900/30'
            : vlmHint.includes('未能识别')
              ? 'text-amber-400 bg-amber-900/30'
              : 'text-green-400 bg-green-900/30'
        }`}>
          {vlmHint}
        </span>
      )}

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

      {/* Auto-generate error */}
      {autoGenHasError && autoGenError && (
        <div className="flex items-center gap-2 text-xs text-red-400">
          <span>{autoGenError}</span>
          <button onClick={() => setAutoGenPhase('idle')} className="underline hover:text-red-300">重试</button>
        </div>
      )}
    </header>
  );
}

// ─── 2D Panel ──────────────────────────────────────────────────────────────────
function Panel2D() {
  const analysisResult = useAppStore((s) => s.analysisResult);
  const croppedImageUrl = useAppStore((s) => s.croppedImageUrl);
  const originalImageUrl = useAppStore((s) => s.originalImageUrl);
  const originalImageBase64 = useAppStore((s) => s.originalImageBase64);
  const imageWidth = useAppStore((s) => s.imageWidth);
  const imageHeight = useAppStore((s) => s.imageHeight);
  const imageMode = useAppStore((s) => s.imageMode);
  const setImageMode = useAppStore((s) => s.setImageMode);
  const depthSplitResult = useAppStore((s) => s.depthSplitResult);
  const selectedDepthLayer = useAppStore((s) => s.selectedDepthLayer);
  const setSelectedDepthLayer = useAppStore((s) => s.setSelectedDepthLayer);

  const displayOriginalUrl = croppedImageUrl || originalImageUrl || (originalImageBase64 ? `data:image/png;base64,${originalImageBase64}` : '');

  // imageMode 控制 2D 面板显示哪一路 URL：
  //   - 'original'   → 显示裁剪图或原图（用户最终看到的画面）
  //   - 'depth'       → 显示 ML 推理出的深度图
  //   - 'depth-layer' → 显示选定深度层的分割掩码图（selectedDepthLayer 指明是哪层）
  const imageUrl = imageMode === 'depth-layer'
    ? (selectedDepthLayer && depthSplitResult ? depthSplitResult[selectedDepthLayer] : '')
    : imageMode === 'depth'
      ? (analysisResult?.depthMapUrl || '')
      : displayOriginalUrl;

  const aspect = imageWidth && imageHeight ? imageWidth / imageHeight : 16 / 9;
  const canvasWidth = 800;
  const canvasHeight = Math.round(canvasWidth / aspect);

  return (
    <div className="flex flex-col h-full min-h-0 overflow-y-auto overflow-x-hidden">
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
        <span className="ml-auto text-[10px] text-gray-600">
          点击下方分层预览选择层
        </span>
      </div>

      <div
        className="relative"
        style={{ height: canvasHeight || 450 }}
      >
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

      {analysisResult && <LayerSelector />}
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
        // 只恢复裁剪图（croppedImageBlob）——这是用户的编辑结果，应该保留。
        // 不恢复 analysisResult：ML 分析结果依赖于服务器状态，刷新页面后
        // analysisId 已失效，重新渲染会报错；用户重新点击 Analyze 即可恢复。
        if (session.croppedImageBlob) {
          const url = blobToUrl(session.croppedImageBlob);
          setCroppedImage(url, session.cropParams ?? null);
        }
      } catch (err) {
        console.warn('Failed to restore session:', err);
      }
    })();
  }, [setCroppedImage]);

  // 导入图片时强制 resize 到 1920×1080，确保 ML pipeline 收到的输入尺寸固定。
  // 原图比例不匹配时 autoResizeTo1920x1080 会自动加黑边保持内容不变形。
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
      // 拖拽分割条时限制在 20%~80% 之间——防止任一面板被压到几乎不可见，
      // 也避免 3D viewer 因为宽高比极端而渲染出错（Three.js 容易报 invalid frustum）。
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
