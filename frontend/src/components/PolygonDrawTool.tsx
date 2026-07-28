// ─────────────────────────────────────────────────────────────────────────────
// PolygonDrawTool — freehand polygon selection for multi-billboard reconstruction
//
// Modes:
//   - idle: no drawing, normal layer assignment mode
//   - drawing: user is actively drawing a polygon
//
// Usage:
//   1. Click the "Draw" button in the toolbar (SplitControls area) to enter draw mode
//   2. Click on the canvas to place polygon vertices
//   3. Double-click or press Enter to close the polygon
//   4. The polygon depth is sampled → auto-assigned to a depth layer
//   5. Region is added to the store as a LayerRegion
//   6. Press Escape to cancel drawing
// ─────────────────────────────────────────────────────────────────────────────
import { useState, useCallback, useRef, useEffect } from 'react';
import { useAppStore } from '../store/useAppStore';
import type { PolygonPoint, LayerRegion } from '../types';
import { LAYER_COLORS, DEPTH_LAYER_THRESHOLDS } from '../types';
import { loadDepthMapImageData, sampleDepthAtPolygon, autoAssignDepthLayer } from '../utils/depthUtils';

export type DrawMode = 'idle' | 'drawing';

interface Props {
  imageWidth: number;
  imageHeight: number;
  onDrawComplete?: (region: LayerRegion) => void;
}

export function usePolygonDraw({ imageWidth, imageHeight, onDrawComplete }: Props) {
  const [drawMode, setDrawMode] = useState<DrawMode>('idle');
  const [points, setPoints] = useState<PolygonPoint[]>([]);
  const [previewDepthLayer, setPreviewDepthLayer] = useState<string | null>(null);
  const samplingRef = useRef(false);

  const analysisResult = useAppStore((s) => s.analysisResult);
  const regions = useAppStore((s) => s.regions);
  const selectedLayerIndex = useAppStore((s) => s.selectedLayerIndex);
  const addRegion = useAppStore((s) => s.addRegion);

  // ─── Start drawing ─────────────────────────────────────────────────────────
  const startDrawing = useCallback(() => {
    setDrawMode('drawing');
    setPoints([]);
    setPreviewDepthLayer(null);
  }, []);

  // ─── Cancel drawing ─────────────────────────────────────────────────────────
  const cancelDrawing = useCallback(() => {
    setDrawMode('idle');
    setPoints([]);
    setPreviewDepthLayer(null);
  }, []);

  // ─── Add a point (click on canvas) ─────────────────────────────────────────
  const addPoint = useCallback(
    (normalizedX: number, normalizedY: number) => {
      if (drawMode !== 'drawing') return;
      setPoints((prev) => {
        const next = [...prev, [normalizedX, normalizedY] as PolygonPoint];
        return next;
      });
    },
    [drawMode],
  );

  // ─── Remove last point (undo last click) ────────────────────────────────────
  const undoLastPoint = useCallback(() => {
    setPoints((prev) => prev.slice(0, -1));
  }, []);

  // ─── Preview depth layer as user draws ─────────────────────────────────────
  const updatePreviewDepthLayer = useCallback(async () => {
    if (points.length < 3 || !analysisResult?.depthMapUrl || samplingRef.current) return;
    samplingRef.current = true;
    try {
      const depthData = await loadDepthMapImageData(analysisResult.depthMapUrl);
      const median = sampleDepthAtPolygon(depthData, points, imageWidth, imageHeight);
      const layer = autoAssignDepthLayer(median);
      setPreviewDepthLayer(layer);
    } finally {
      samplingRef.current = false;
    }
  }, [points, analysisResult, imageWidth, imageHeight]);

  useEffect(() => {
    updatePreviewDepthLayer();
  }, [updatePreviewDepthLayer]);

  // ─── Complete polygon ───────────────────────────────────────────────────────
  const completePolygon = useCallback(async () => {
    if (drawMode !== 'drawing' || points.length < 3) return;

    const depthMapUrl = analysisResult?.depthMapUrl;
    let depthValue = 128;
    let depthLayer = previewDepthLayer ?? 'foreground';

    if (depthMapUrl && !samplingRef.current) {
      samplingRef.current = true;
      try {
        const depthData = await loadDepthMapImageData(depthMapUrl);
        depthValue = sampleDepthAtPolygon(depthData, points, imageWidth, imageHeight);
        depthLayer = autoAssignDepthLayer(depthValue);
      } catch (err) {
        console.error('Failed to sample depth for polygon:', err);
      } finally {
        samplingRef.current = false;
      }
    }

    const colorIndex = selectedLayerIndex ?? (regions.length % LAYER_COLORS.length);

    const region: LayerRegion = {
      id: `region-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      polygon: points,
      depthLayer,
      colorIndex,
      source: 'manual',
      depthValue,
    };

    addRegion(region);
    onDrawComplete?.(region);
    setDrawMode('idle');
    setPoints([]);
    setPreviewDepthLayer(null);
  }, [drawMode, points, analysisResult, previewDepthLayer, selectedLayerIndex, regions, imageWidth, imageHeight, addRegion, onDrawComplete]);

  // ─── Keyboard shortcuts ─────────────────────────────────────────────────────
  useEffect(() => {
    if (drawMode !== 'drawing') return;

    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Enter' && points.length >= 3) {
        completePolygon();
      } else if (e.key === 'Escape') {
        cancelDrawing();
      } else if (e.key === 'z' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        undoLastPoint();
      } else if (e.key === 'Backspace') {
        undoLastPoint();
      }
    };

    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [drawMode, points, completePolygon, cancelDrawing, undoLastPoint]);

  return {
    drawMode,
    points,
    previewDepthLayer,
    startDrawing,
    cancelDrawing,
    addPoint,
    undoLastPoint,
    completePolygon,
  };
}

// ─── SVG overlay for the polygon being drawn ──────────────────────────────────
interface PolygonOverlayProps {
  points: PolygonPoint[];
  imageWidth: number;
  imageHeight: number;
  previewColor?: string;
}

export function PolygonOverlay({ points, imageWidth, imageHeight, previewColor = '#00BCD4' }: PolygonOverlayProps) {
  if (points.length === 0) return null;

  const toSvg = ([x, y]: PolygonPoint) => `${x * imageWidth},${y * imageHeight}`;
  const ptsStr = points.map(toSvg).join(' ');
  const polyStr = points.map(toSvg).join(' ');

  return (
    <svg
      className="absolute inset-0 w-full h-full pointer-events-none"
      viewBox={`0 0 ${imageWidth} ${imageHeight}`}
    >
      {/* Filled preview */}
      {points.length >= 3 && (
        <polygon
          points={polyStr}
          fill={previewColor}
          fillOpacity={0.2}
          stroke={previewColor}
          strokeWidth={2}
          strokeOpacity={0.8}
        />
      )}
      {/* Lines between points */}
      {points.length >= 2 && (
        <polyline
          points={ptsStr}
          fill="none"
          stroke={previewColor}
          strokeWidth={1.5}
          strokeDasharray="4 2"
          strokeOpacity={0.7}
        />
      )}
      {/* Point handles */}
      {points.map((pt, i) => {
        const [x, y] = pt;
        return (
          <circle
            key={i}
            cx={x * imageWidth}
            cy={y * imageHeight}
            r={5}
            fill={i === 0 ? previewColor : 'white'}
            stroke={previewColor}
            strokeWidth={1.5}
          />
        );
      })}
      {/* Hint text */}
      {points.length < 3 && (
        <text
          x={imageWidth / 2}
          y={imageHeight - 20}
          textAnchor="middle"
          fontSize={13}
          fill={previewColor}
          style={{ fontFamily: 'monospace' }}
        >
          {points.length === 0
            ? 'Click to place points'
            : `${points.length} point${points.length > 1 ? 's' : ''} — need ${3 - points.length} more`}
        </text>
      )}
      {points.length >= 3 && (
        <text
          x={imageWidth / 2}
          y={imageHeight - 20}
          textAnchor="middle"
          fontSize={13}
          fill={previewColor}
          style={{ fontFamily: 'monospace' }}
        >
          Press Enter to confirm · Esc to cancel · Ctrl+Z to undo last point
        </text>
      )}
    </svg>
  );
}

// ─── SVG overlay for completed regions ────────────────────────────────────────
interface RegionOverlaysProps {
  regions: LayerRegion[];
  imageWidth: number;
  imageHeight: number;
}

export function RegionOverlays({ regions, imageWidth, imageHeight }: RegionOverlaysProps) {
  return (
    <svg
      className="absolute inset-0 w-full h-full pointer-events-none"
      viewBox={`0 0 ${imageWidth} ${imageHeight}`}
    >
      {regions.map((region) => {
        const color = LAYER_COLORS[region.colorIndex % LAYER_COLORS.length];
        const pts = region.polygon.map(([x, y]) => `${x * imageWidth},${y * imageHeight}`).join(' ');

        return (
          <g key={region.id}>
            <polygon
              points={pts}
              fill={color}
              fillOpacity={0.25}
              stroke={color}
              strokeWidth={2}
            />
            <text
              x={region.polygon[0][0] * imageWidth + 4}
              y={region.polygon[0][1] * imageHeight + 14}
              fontSize={11}
              fill={color}
              style={{ fontFamily: 'monospace', textShadow: '0 1px 3px rgba(0,0,0,0.8)' }}
            >
              {region.depthLayer} {region.source === 'manual' ? '(手绘)' : ''}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
