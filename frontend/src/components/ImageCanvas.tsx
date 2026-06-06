// ─────────────────────────────────────────────────────────────────────────────
// ImageCanvas — 2D canvas showing depth map + object overlays
// ─────────────────────────────────────────────────────────────────────────────
import { useCallback, useMemo } from 'react';
import { useAppStore } from '../store/useAppStore';
import type { DetectedObject } from '../types';
import { LAYER_COLORS } from '../types';

interface Props {
  width: number;
  height: number;
}

export function ImageCanvas({ width, height }: Props) {
  const analysisResult = useAppStore((s) => s.analysisResult);
  const originalImageUrl = useAppStore((s) => s.originalImageUrl);
  const croppedImageUrl = useAppStore((s) => s.croppedImageUrl);
  const originalImageBase64 = useAppStore((s) => s.originalImageBase64);
  const imageMode = useAppStore((s) => s.imageMode);
  const depthSplitResult = useAppStore((s) => s.depthSplitResult);
  const selectedDepthLayer = useAppStore((s) => s.selectedDepthLayer);
  const assignments = useAppStore((s) => s.assignments);
  const selectedLayerIndex = useAppStore((s) => s.selectedLayerIndex);
  const selectedObjectId = useAppStore((s) => s.selectedObjectId);
  const toggleObjectLayer = useAppStore((s) => s.toggleObjectLayer);
  const setSelectedObjectId = useAppStore((s) => s.setSelectedObjectId);

  const objects: DetectedObject[] = analysisResult?.objects ?? [];

  const originalUrl = croppedImageUrl || originalImageUrl || (originalImageBase64 ? `data:image/png;base64,${originalImageBase64}` : '');

  const bgUrl = useMemo(() => {
    if (imageMode === 'depth-layer') {
      return selectedDepthLayer && depthSplitResult ? depthSplitResult[selectedDepthLayer] : '';
    }
    if (imageMode === 'depth') {
      return analysisResult?.depthMapUrl || '';
    }
    return originalUrl;
  }, [analysisResult?.depthMapUrl, depthSplitResult, imageMode, originalUrl, selectedDepthLayer]);

  // 切换到深度分层视图（depth-layer）时隐藏物体标注叠加层——
  // 分层视图显示的是分割掩码图，叠加层与之叠开会造成视觉干扰；
  // 用户在分层模式下需要的是干净的分层图像，而不是额外的标注框。
  const showObjectOverlay = imageMode !== 'depth-layer';

  // selectedLayerIndex 为 null 时：仅高亮/取消高亮物体（用于查看）
  // selectedLayerIndex 有值时：将物体分配到 / 取消分配到对应深度层
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
      {showObjectOverlay && (
        <svg
          className="absolute inset-0 w-full h-full"
          viewBox={`0 0 ${width} ${height}`}
          onClick={handleCanvasClick}
          style={{ cursor: selectedLayerIndex !== null ? 'crosshair' : 'default' }}
        >
          {/*
            按面积从大到小排序 → 渲染顺序由大到小。
            SVG/Canvas 默认后绘元素在上层，因此最大物体最后画，叠在其他小物体上面，
            更符合"主要物体视觉层级最高"的直觉。

            形状选择：有 polygon（精确轮廓点）时优先用多边形渲染；
            polygon 为空时退化为 boundingBox（矩形）。
            多边形的 fill+stroke 组合使得精确遮罩和描边能同时生效，
            而 boundingBox 只在模型未输出精确轮廓时兜底。
          */}
          {[...objects].sort((a, b) => {
            const areaA = a.boundingBox.w * a.boundingBox.h;
            const areaB = b.boundingBox.w * b.boundingBox.h;
            return areaB - areaA;
          }).map((obj) => {
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
      )}

      {/* Empty state */}
      {objects.length === 0 && !analysisResult && (
        <div className="absolute inset-0 flex items-center justify-center text-gray-500">
          <span>Import an image and run analysis</span>
        </div>
      )}
    </div>
  );
}
