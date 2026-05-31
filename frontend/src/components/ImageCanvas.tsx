// ─────────────────────────────────────────────────────────────────────────────
// ImageCanvas — 2D canvas showing depth map + object overlays
// ─────────────────────────────────────────────────────────────────────────────
import { useCallback } from 'react';
import { useAppStore } from '../store/useAppStore';
import { LAYER_COLORS } from '../types';
import type { DetectedObject } from '../types';

interface Props {
  width: number;
  height: number;
}

export function ImageCanvas({ width, height }: Props) {
  const analysisResult = useAppStore((s) => s.analysisResult);
  const originalImageUrl = useAppStore((s) => s.originalImageUrl);
  const originalImageBase64 = useAppStore((s) => s.originalImageBase64);
  const imageMode = useAppStore((s) => s.imageMode);
  const assignments = useAppStore((s) => s.assignments);
  const selectedLayerIndex = useAppStore((s) => s.selectedLayerIndex);
  const selectedObjectId = useAppStore((s) => s.selectedObjectId);
  const toggleObjectLayer = useAppStore((s) => s.toggleObjectLayer);
  const setSelectedObjectId = useAppStore((s) => s.setSelectedObjectId);

  const objects: DetectedObject[] = analysisResult?.objects ?? [];

  const originalUrl = originalImageUrl || (originalImageBase64 ? `data:image/png;base64,${originalImageBase64}` : '');
  const bgUrl = imageMode === 'original' ? originalUrl : analysisResult?.depthMapUrl;

  const handleObjectClick = useCallback(
    (obj: DetectedObject, e: React.MouseEvent) => {
      e.stopPropagation();
      if (selectedLayerIndex === null) {
        // No layer selected — just toggle highlight
        setSelectedObjectId(selectedObjectId === obj.id ? null : obj.id);
      } else {
        // Assign / unassign
        toggleObjectLayer(obj.id);
        setSelectedObjectId(obj.id);
      }
    },
    [selectedLayerIndex, selectedObjectId, toggleObjectLayer, setSelectedObjectId],
  );

  const handleCanvasClick = useCallback(() => {
    setSelectedObjectId(null);
  }, [setSelectedObjectId]);

  return (
    <div
      className="relative w-full h-full overflow-hidden bg-gray-900"
      style={{ minHeight: 400 }}
    >
      {/* Background image (depth map or original) */}
      {bgUrl && (
        <img
          src={bgUrl}
          alt={imageMode === 'original' ? 'Original Image' : 'Depth Map'}
          className="absolute inset-0 w-full h-full object-contain"
          draggable={false}
        />
      )}

      {/* Object overlay */}
      <svg
        className="absolute inset-0 w-full h-full"
        viewBox={`0 0 ${width} ${height}`}
        onClick={handleCanvasClick}
        style={{ cursor: selectedLayerIndex !== null ? 'crosshair' : 'default' }}
      >
        {objects.map((obj) => {
          const bbox = obj.boundingBox;
          const px = bbox.x * width;
          const py = bbox.y * height;
          const pw = bbox.w * width;
          const ph = bbox.h * height;

          const layerIndex = assignments[obj.id];
          const isAssigned = layerIndex !== undefined;
          const isSelected = selectedObjectId === obj.id;
          const isActiveLayer = layerIndex === selectedLayerIndex;

          const color = isAssigned ? LAYER_COLORS[layerIndex] : '#ffffff';
          const fillColor = isAssigned ? color : 'transparent';

          // Convert normalized polygon [x,y] pairs to SVG points string
          const polygonPoints = obj.polygon.length > 0
            ? obj.polygon.map(([x, y]) => `${x * width},${y * height}`).join(' ')
            : '';

          return (
            <g
              key={obj.id}
              onClick={(e) => handleObjectClick(obj, e)}
              style={{ cursor: 'pointer' }}
              className="transition-opacity duration-150"
            >
              {/* Polygon fill (if polygon available) */}
              {obj.polygon.length > 0 ? (
                <polygon
                  points={polygonPoints}
                  fill={fillColor}
                  fillOpacity={isAssigned ? 0.35 : 0}
                  stroke="none"
                />
              ) : (
                <rect
                  x={px}
                  y={py}
                  width={pw}
                  height={ph}
                  fill={fillColor}
                  fillOpacity={isAssigned ? 0.35 : 0}
                  stroke="none"
                />
              )}
              {/* Polygon border (if polygon available) */}
              {obj.polygon.length > 0 ? (
                <polygon
                  points={polygonPoints}
                  fill="none"
                  stroke={isSelected ? '#ffffff' : color}
                  strokeWidth={isSelected ? 3 : isActiveLayer ? 2.5 : 1.5}
                  strokeDasharray={isSelected ? 'none' : '4 2'}
                />
              ) : (
                <rect
                  x={px}
                  y={py}
                  width={pw}
                  height={ph}
                  fill="none"
                  stroke={isSelected ? '#ffffff' : color}
                  strokeWidth={isSelected ? 3 : isActiveLayer ? 2.5 : 1.5}
                  strokeDasharray={isSelected ? 'none' : '4 2'}
                  rx={3}
                  ry={3}
                />
              )}
              {/* Label */}
              <text
                x={px + 4}
                y={py + 14}
                fontSize={11}
                fill={color}
                className="pointer-events-none select-none"
                style={{ fontFamily: 'monospace', textShadow: '0 1px 3px rgba(0,0,0,0.8)' }}
              >
                {obj.classLabel}
                {isAssigned ? ` [L${layerIndex + 1}]` : ''}
              </text>
            </g>
          );
        })}
      </svg>

      {/* Empty state */}
      {objects.length === 0 && !analysisResult && (
        <div className="absolute inset-0 flex items-center justify-center text-gray-500">
          <span>Import an image and run analysis</span>
        </div>
      )}
    </div>
  );
}
