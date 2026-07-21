// ─────────────────────────────────────────────────────────────────────────────
// ExportPanel — 3D viewport screenshot + 3D mesh export
// Supports: PNG screenshot | GLB/FBX mesh export (objects, layers, scene)
// ─────────────────────────────────────────────────────────────────────────────
import { useState, useCallback } from 'react';
import { Download, X, Image, Box, Loader2, AlertCircle, CheckCircle2, ChevronDown } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import {
  exportMeshObjects,
  exportMeshLayers,
  exportMeshScene,
  checkBlenderAvailable,
  downloadMeshFile,
  type MeshExportResponse,
  type BlenderCheckResponse,
} from '../services/meshExportService';
import type { DepthLayerKey } from '../types';

interface ExportPanelProps {
  /** Pass a ref to the Canvas DOM element (gl.domElement) */
  canvasRef: React.RefObject<HTMLCanvasElement | null>;
}

type ExportScope = 'objects' | 'layers' | 'scene';
type ExportFormat = 'png' | 'glb' | 'fbx';

export function ExportPanel({ canvasRef }: ExportPanelProps) {
  const [expanded, setExpanded] = useState(false);
  const [activeSection, setActiveSection] = useState<'2d' | '3d'>('2d');

  // 3D mesh export state
  const [scope, setScope] = useState<ExportScope>('layers');
  const [format, setFormat] = useState<ExportFormat>('glb');
  const [includeTextures, setIncludeTextures] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [exportResult, setExportResult] = useState<MeshExportResponse | null>(null);
  const [blenderStatus, setBlenderStatus] = useState<BlenderCheckResponse | null>(null);

  const analysisResult = useAppStore((s) => s.analysisResult);
  const depthLayerDioramaAssets = useAppStore((s) => s.depthLayerDioramaAssets);
  const objectDioramaAssets = useAppStore((s) => s.objectDioramaAssets);
  const billboardOffsets = useAppStore((s) => s.billboardOffsets);
  const depthSplitResult = useAppStore((s) => s.depthSplitResult);

  // ── PNG Screenshot ────────────────────────────────────────────────────────────

  const handleExportPNG = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dataUrl = canvas.toDataURL('image/png');
    const link = document.createElement('a');
    link.download = `aicss-3d-${Date.now()}.png`;
    link.href = dataUrl;
    link.click();
  }, [canvasRef]);

  // ── Check Blender availability ───────────────────────────────────────────────

  const checkBlender = useCallback(async () => {
    try {
      const status = await checkBlenderAvailable();
      setBlenderStatus(status);
      return status.available;
    } catch {
      setBlenderStatus({ available: false, message: 'Failed to check Blender', path: null, version: null, error: 'Network error' });
      return false;
    }
  }, []);

  // ── 3D Mesh Export ──────────────────────────────────────────────────────────

  const handleExport3D = useCallback(async () => {
    if (!analysisResult) return;

    const blenderOk = blenderStatus?.available ?? (await checkBlender());
    if (!blenderOk) {
      setExportResult({
        mesh_id: '',
        scope,
        format,
        success: false,
        blender_available: false,
        error: blenderStatus?.message || 'Blender not available',
        object_count: 0,
        vertex_count: 0,
        face_count: 0,
        include_textures: false,
      } as MeshExportResponse);
      return;
    }

    setExporting(true);
    setExportResult(null);

    try {
      let result: MeshExportResponse;

      const commonParams = {
        format: format as 'glb' | 'fbx',
        include_textures: includeTextures,
      };

      if (scope === 'objects') {
        const objectIds = analysisResult.objects.map((o) => o.id);
        result = await exportMeshObjects({
          analysis_result: analysisResult as unknown as Record<string, unknown>,
          object_ids: objectIds,
          object_assets: objectDioramaAssets as Record<string, unknown>,
          billboard_offsets: billboardOffsets as Record<string, unknown>,
          ...commonParams,
        });
      } else if (scope === 'layers') {
        result = await exportMeshLayers({
          layer_assets: depthLayerDioramaAssets as Record<string, unknown>,
          ...commonParams,
        });
      } else {
        // scene: all layers + objects combined
        result = await exportMeshScene({
          analysis_result: analysisResult as unknown as Record<string, unknown>,
          depth_split_result: depthSplitResult as Record<string, unknown>,
          layer_assets: depthLayerDioramaAssets as Record<string, unknown>,
          object_assets: objectDioramaAssets as Record<string, unknown>,
          billboard_offsets: billboardOffsets as Record<string, unknown>,
          ...commonParams,
        });
      }

      setExportResult(result);

      // Auto-download if successful
      if (result.success && result.mesh_id && result.file_name) {
        downloadMeshFile(result.mesh_id, '', result.file_name);
      }
    } catch (err) {
      setExportResult({
        mesh_id: '',
        scope,
        format,
        success: false,
        blender_available: blenderStatus?.available ?? false,
        error: err instanceof Error ? err.message : String(err),
        object_count: 0,
        vertex_count: 0,
        face_count: 0,
        include_textures: false,
      } as MeshExportResponse);
    } finally {
      setExporting(false);
    }
  }, [
    analysisResult, scope, format, includeTextures, blenderStatus,
    checkBlender, depthLayerDioramaAssets, objectDioramaAssets,
    billboardOffsets, depthSplitResult,
  ]);

  const scopeLabel = {
    objects: '物体',
    layers: '层',
    scene: '场景',
  }[scope];

  const formatLabel = format.toUpperCase();

  return (
    <div className="absolute bottom-3 right-3 z-10">
      {expanded ? (
        <div className="bg-gray-900/95 border border-gray-700 rounded-xl p-3 flex flex-col gap-3 shadow-xl w-72">
          {/* Header */}
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-gray-200">导出</span>
            <button
              onClick={() => setExpanded(false)}
              className="p-1 hover:bg-gray-700 rounded transition-colors"
            >
              <X size={14} className="text-gray-400" />
            </button>
          </div>

          {/* Section tabs */}
          <div className="flex rounded-lg overflow-hidden border border-gray-700">
            <button
              onClick={() => setActiveSection('2d')}
              className={`flex-1 px-3 py-1.5 text-xs font-medium transition-colors ${
                activeSection === '2d'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-800 text-gray-400 hover:text-white'
              }`}
            >
              PNG 截图
            </button>
            <button
              onClick={() => setActiveSection('3d')}
              className={`flex-1 px-3 py-1.5 text-xs font-medium transition-colors ${
                activeSection === '3d'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-800 text-gray-400 hover:text-white'
              }`}
            >
              3D Mesh
            </button>
          </div>

          {/* PNG Section */}
          {activeSection === '2d' && (
            <div className="flex flex-col gap-2">
              <button
                onClick={handleExportPNG}
                disabled={!canvasRef.current}
                className="flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition-colors disabled:opacity-40"
              >
                <Image size={14} />
                导出 PNG 截图
              </button>
              <p className="text-[10px] text-gray-500 text-center">
                截图分辨率与当前视口一致
              </p>
            </div>
          )}

          {/* 3D Mesh Section */}
          {activeSection === '3d' && (
            <div className="flex flex-col gap-2">
              {/* Blender status */}
              {blenderStatus && !blenderStatus.available && (
                <div className="flex items-start gap-1.5 p-2 bg-red-900/40 border border-red-800 rounded-lg">
                  <AlertCircle size={12} className="text-red-400 mt-0.5 flex-shrink-0" />
                  <p className="text-[10px] text-red-300 leading-relaxed">
                    {blenderStatus.message || 'Blender 不可用'}
                    {!blenderStatus.path && (
                      <span className="block mt-0.5 opacity-70">
                        请安装 Blender >= 3.0 并添加到系统 PATH
                      </span>
                    )}
                  </p>
                </div>
              )}

              {/* Scope selector */}
              <div>
                <label className="text-[10px] text-gray-400 mb-1 block">导出范围</label>
                <div className="flex flex-wrap gap-1">
                  {(['objects', 'layers', 'scene'] as ExportScope[]).map((s) => (
                    <button
                      key={s}
                      onClick={() => setScope(s)}
                      className={`px-2 py-1 rounded text-[10px] font-medium transition-colors ${
                        scope === s
                          ? 'bg-purple-600 text-white'
                          : 'bg-gray-800 text-gray-400 hover:text-white'
                      }`}
                    >
                      {s === 'objects' ? '物体' : s === 'layers' ? '层' : '场景'}
                    </button>
                  ))}
                </div>
              </div>

              {/* Format selector */}
              <div>
                <label className="text-[10px] text-gray-400 mb-1 block">格式</label>
                <div className="flex gap-1">
                  {(['glb', 'fbx'] as ExportFormat[]).map((f) => (
                    <button
                      key={f}
                      onClick={() => setFormat(f)}
                      className={`px-3 py-1 rounded text-[10px] font-mono font-medium transition-colors ${
                        format === f
                          ? 'bg-green-600 text-white'
                          : 'bg-gray-800 text-gray-400 hover:text-white'
                      }`}
                    >
                      {f.toUpperCase()}
                    </button>
                  ))}
                </div>
              </div>

              {/* Textures toggle */}
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={includeTextures}
                  onChange={(e) => setIncludeTextures(e.target.checked)}
                  className="w-3 h-3 rounded accent-green-500"
                />
                <span className="text-[10px] text-gray-400">嵌入纹理</span>
              </label>

              {/* Export button */}
              <button
                onClick={handleExport3D}
                disabled={exporting || !analysisResult}
                className="flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-green-600 hover:bg-green-500 text-white text-xs font-medium transition-colors disabled:opacity-40"
              >
                {exporting ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    导出中...
                  </>
                ) : (
                  <>
                    <Box size={14} />
                    导出 {scopeLabel} ({formatLabel})
                  </>
                )}
              </button>

              {/* Result */}
              {exportResult && (
                <div className={`flex items-start gap-1.5 p-2 rounded-lg border ${
                  exportResult.success
                    ? 'bg-green-900/40 border-green-800'
                    : 'bg-red-900/40 border-red-800'
                }`}>
                  {exportResult.success ? (
                    <CheckCircle2 size={12} className="text-green-400 mt-0.5 flex-shrink-0" />
                  ) : (
                    <AlertCircle size={12} className="text-red-400 mt-0.5 flex-shrink-0" />
                  )}
                  <div className="text-[10px] leading-relaxed">
                    {exportResult.success ? (
                      <>
                        <span className="text-green-300 font-medium">导出成功</span>
                        <span className="text-gray-400 ml-1">
                          {exportResult.object_count} 对象 | {exportResult.vertex_count} 顶点
                        </span>
                        {exportResult.file_name && (
                          <span className="block text-gray-500 mt-0.5">
                            {exportResult.file_name} ({(exportResult.file_size! / 1024).toFixed(1)} KB)
                          </span>
                        )}
                      </>
                    ) : (
                      <span className="text-red-300">
                        {exportResult.error?.slice(0, 100) || '导出失败'}
                      </span>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Close */}
          <button
            onClick={() => setExpanded(false)}
            className="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-700 hover:bg-gray-600 text-gray-300 text-xs transition-colors"
          >
            关闭
          </button>
        </div>
      ) : (
        <button
          onClick={async () => {
            setExpanded(true);
            if (!blenderStatus) await checkBlender();
          }}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-gray-800/90 hover:bg-gray-700 text-gray-300 text-xs font-medium border border-gray-700 transition-colors shadow-lg"
          title="导出"
        >
          <Download size={14} />
          导出
        </button>
      )}
    </div>
  );
}
