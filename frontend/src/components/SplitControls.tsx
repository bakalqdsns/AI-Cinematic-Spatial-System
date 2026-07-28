// ─────────────────────────────────────────────────────────────────────────────
// SplitControls — split image, generate 3D, reset, inpaint
// ─────────────────────────────────────────────────────────────────────────────
import { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import { useAppStore } from '../store/useAppStore';
import type { DepthSplitThresholds } from '../types';
import { generateBillboard, inpaintImage, extractRegionBillboard } from '../services/aicssService';
import { DEFAULT_DEPTH_SPLIT_THRESHOLDS, splitDepthLayers } from '../utils/depthSplit';
import { InpaintPreviewDialog } from './InpaintPreviewDialog';
import { DepthSplitPanel } from './DepthSplitPanel';
import { DioramaSettingsPanel } from './DioramaSettingsPanel';
import { Scissors, Wand2, RotateCcw, Loader2, CheckCircle, AlertCircle, Layers3, Pencil, MousePointer2, Trash2, Undo2, Sparkles } from 'lucide-react';

export function SplitControls() {
  const analysisResult = useAppStore((s) => s.analysisResult);
  const croppedImageUrl = useAppStore((s) => s.croppedImageUrl);
  const originalImageBase64 = useAppStore((s) => s.originalImageBase64);
  const originalImageUrl = useAppStore((s) => s.originalImageUrl);
  const assignments = useAppStore((s) => s.assignments);
  const selectedLayerIndex = useAppStore((s) => s.selectedLayerIndex);
  const billboardAssets = useAppStore((s) => s.billboardAssets);
  const setBillboardAsset = useAppStore((s) => s.setBillboardAsset);
  const setDepthLayerBillboardAsset = useAppStore((s) => s.setDepthLayerBillboardAsset);
  const clearDepthLayerBillboardAssets = useAppStore((s) => s.clearDepthLayerBillboardAssets);
  const clearAllAssignments = useAppStore((s) => s.clearAllAssignments);
  const reset = useAppStore((s) => s.reset);
  const inpaintPreviewUrl = useAppStore((s) => s.inpaintPreviewUrl);
  const setInpaintPreview = useAppStore((s) => s.setInpaintPreview);
  const depthSplitResult = useAppStore((s) => s.depthSplitResult);
  const setDepthSplitResult = useAppStore((s) => s.setDepthSplitResult);
  const depthSplitLoading = useAppStore((s) => s.depthSplitLoading);
  const setDepthSplitLoading = useAppStore((s) => s.setDepthSplitLoading);
  const depthSplitConfirmed = useAppStore((s) => s.depthSplitConfirmed);
  const setDepthSplitConfirmed = useAppStore((s) => s.setDepthSplitConfirmed);
  const depthSplitError = useAppStore((s) => s.depthSplitError);
  const setDepthSplitError = useAppStore((s) => s.setDepthSplitError);
  const selectedDepthLayer = useAppStore((s) => s.selectedDepthLayer);
  const setSelectedDepthLayer = useAppStore((s) => s.setSelectedDepthLayer);
  const depthSplitThresholds = useAppStore((s) => s.depthSplitThresholds);
  const setDepthSplitThresholds = useAppStore((s) => s.setDepthSplitThresholds);
  const imageMode = useAppStore((s) => s.imageMode);
  const setImageMode = useAppStore((s) => s.setImageMode);
  const inpaintLoading = useAppStore((s) => s.inpaintLoading);
  const setInpaintLoading = useAppStore((s) => s.setInpaintLoading);
  const inpaintError = useAppStore((s) => s.inpaintError);
  const setInpaintError = useAppStore((s) => s.setInpaintError);
  const dashscopeApiKey = useAppStore((s) => s.dashscopeApiKey);
  const regions = useAppStore((s) => s.regions);
  const drawMode = useAppStore((s) => s.drawMode);
  const drawPoints = useAppStore((s) => s.drawPoints);
  const clearDrawPoints = useAppStore((s) => s.clearDrawPoints);
  const imageWidth = useAppStore((s) => s.imageWidth);
  const imageHeight = useAppStore((s) => s.imageHeight);
  const startDrawing = useAppStore((s) => s.startDrawing);
  const cancelDrawing = useAppStore((s) => s.cancelDrawing);
  const removeRegion = useAppStore((s) => s.removeRegion);
  const setRegions = useAppStore((s) => s.setRegions);
  // Strip pipeline state — read for the "strip next layer" button row.
  const stripStack = useAppStore((s) => s.stripStack);
  const currentImageUrl = useAppStore((s) => s.currentImageUrl);
  const isStripping = useAppStore((s) => s.isStripping);
  const stripError = useAppStore((s) => s.stripError);
  const pushStripStep = useAppStore((s) => s.pushStripStep);
  const undoLastStripStep = useAppStore((s) => s.undoLastStripStep);
  const resetStripStack = useAppStore((s) => s.resetStripStack);
  const setStripping = useAppStore((s) => s.setStripping);
  const setStripError = useAppStore((s) => s.setStripError);

  const [splitting, setSplitting] = useState(false);
  const [splitProgress, setSplitProgress] = useState(0);
  const [splitError, setSplitError] = useState<string | null>(null);
  const [splitDone, setSplitDone] = useState(false);
  const lastPreviewThresholdsRef = useRef<string | null>(null);

  const objects = analysisResult?.objects ?? [];
  const assignedObjects = objects.filter((o) => assignments[o.id] !== undefined);
  // 当前选中图层（色块）上分配的物体集合。
  // 这是"补全背景"按钮要抹掉的集合——与 assignedObjects 语义相反：
  //   - assignedObjects: 所有被分配的物体，handleSplit（抠取 billboard）需要
  //   - currentLayerObjects: 当前选中图层的物体，inpaint 反向 mask 需要
  const currentLayerObjects = useMemo(
    () =>
      selectedLayerIndex === null
        ? []
        : objects.filter((o) => assignments[o.id] === selectedLayerIndex),
    [objects, assignments, selectedLayerIndex],
  );

  const updateDepthThreshold = (key: keyof DepthSplitThresholds, value: number) => {
    const clamped = Math.max(0, Math.min(255, value));
    const next = { ...depthSplitThresholds, [key]: clamped };

    if (key === 'foregroundMin' && next.foregroundMin < next.midgroundMin) {
      next.midgroundMin = next.foregroundMin;
    }
    if (key === 'midgroundMin') {
      if (next.midgroundMin > next.foregroundMin) {
        next.foregroundMin = next.midgroundMin;
      }
      if (next.midgroundMin < next.backgroundMin) {
        next.backgroundMin = next.midgroundMin;
      }
    }
    if (key === 'backgroundMin' && next.backgroundMin > next.midgroundMin) {
      next.midgroundMin = next.backgroundMin;
    }

    setDepthSplitThresholds(next);
  };

  // effectiveImageUrl 优先级链：
  // 1. croppedImageUrl — 用户裁剪后的图片（导入时自动缩放到 1920×1080），最精确
  // 2. originalImageUrl — Blob URL，未裁剪，适合需要完整画布的场景
  // 3. originalImageBase64 → data URI — 最终兜底，确保任何情况下都有可用图片
  // 裁剪图优先是因为 inpaint 需要精确的 mask 与图片尺寸对齐，原始图可能导致 mask 错位
  const effectiveImageUrl =
    croppedImageUrl ||
    originalImageUrl ||
    (originalImageBase64 ? `data:image/png;base64,${originalImageBase64}` : '');

  // ─── Compute inverse mask from the currently-selected layer ───────────────
  // Mask 语义（与 LaMa/后端约定一致）：
  //   - 白色区域（alpha=255）→ 保留原样（其他图层 + 背景）
  //   - 黑色区域（alpha=0）  → 需要被 inpaint 替换（当前选中图层上的物体）
  //
  // 关键反转：原实现把"所有已分配物体"涂黑（keep），与用户心智模型相反。
  // 现在只把"当前选中图层（selectedLayerIndex）"的物体涂黑（inpaint 区），
  // 其他图层和未分配的物体 + 背景一律视为保留。
  //
  // 双通道处理的原因：
  //   Canvas 2D 的 fillRect 默认为不透明，getImageData 只能读到 R/G/B，没有 alpha。
  //   因此需要两步：先用灰度绘制黑白遮罩，再将灰度值映射到 RGBA 的 alpha 通道，
  //   这样导出的 PNG 才能正确携带透明信息。
  const computeInverseMask = useCallback((): Promise<string> => {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement('canvas');
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;
        const ctx = canvas.getContext('2d')!;

        // White background = entire image is keep area by default
        ctx.fillStyle = 'white';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        // Draw CURRENT-layer object polygons in black = area to inpaint
        ctx.fillStyle = 'black';
        ctx.globalCompositeOperation = 'source-over';

        for (const obj of currentLayerObjects) {
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

        // Create RGBA canvas: alpha channel carries the inpaint mask.
        // LaMa semantics: alpha=255 = inpaint target, alpha=0 = preserve.
        //
        // In our grayscale canvas:
        //   - black (polygon interior) = area to inpaint (we want to erase these objects)
        //   - white (rest of image)    = area to keep
        //
        // So map: black -> alpha=255 (inpaint), white -> alpha=0 (preserve).
        // (Previous version had this inverted, which told LaMa to repaint
        //  the *whole* image and explain why the inpaint result looked like
        //  the whole scene was hallucinated.)
        const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
        const rgba = ctx.createImageData(canvas.width, canvas.height);
        for (let i = 0; i < imageData.data.length; i += 4) {
          const gray = imageData.data[i]; // R channel (all same: 0 or 255)
          rgba.data[i] = 255;     // R
          rgba.data[i + 1] = 255; // G
          rgba.data[i + 2] = 255; // B
          // Invert: gray=0 (black polygon → inpaint target) → alpha=255
          //         gray=255 (white background → preserve)         → alpha=0
          rgba.data[i + 3] = 255 - gray;
        }
        ctx.putImageData(rgba, 0, 0);

        // Export as RGBA PNG (alpha channel carries the mask)
        resolve(canvas.toDataURL('image/png'));
      };
      img.onerror = () => reject(new Error('Failed to load image for mask generation'));
      img.src = effectiveImageUrl;
    });
  }, [effectiveImageUrl, currentLayerObjects]);

  // ─── Generate auto-prompt for the current layer being inpainted ───────────
  const generatePrompt = useCallback((): string => {
    if (currentLayerObjects.length === 0) return '自然填补空白区域';
    const labels = currentLayerObjects.map((o) => o.classLabel).join('、');
    return `结合周围环境，自然替换/补全 ${labels || '当前图层物体'} 的区域`;
  }, [currentLayerObjects]);

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
  // API Key 检查放在最前面：在 UI 交互触发时就尽早失败，避免走到网络请求才发现问题
  // 注意：检查的是 dashscopeApiKey store 状态，若用户从未设置或未保存，此处直接拦截
  const handleSplitAndInpaint = async () => {
    // 防御性：UI 已禁用按钮，但函数本身也要拦截 selectedLayerIndex === null，
    // 避免误传空 mask 给 LaMa。
    if (!effectiveImageUrl || selectedLayerIndex === null || currentLayerObjects.length === 0) {
      setInpaintError('请先在左侧分组里选择目标图层，并把至少一个物体分配到该图层');
      return;
    }

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
      const resultUrl = await inpaintImage(effectiveImageUrl, maskDataUrl, prompt);
      setInpaintPreview(resultUrl);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setInpaintError(msg);
      console.error('Inpaint failed:', err);
    } finally {
      setInpaintLoading(false);
    }
  };

  // ─── Region-based inpaint ─────────────────────────────────────────────────
  // Inpaint all regions: each region uses its own polygon as the mask.
  // For occlusion-aware inpaint, we need the depth map — loaded here inline.
  const handleRegionInpaint = useCallback(async () => {
    if (!effectiveImageUrl || regions.length === 0) return;
    if (!dashscopeApiKey) {
      setInpaintError('请先在顶部输入 DashScope API Key');
      return;
    }

    setInpaintLoading(true);
    setInpaintError(null);
    setInpaintPreview(null);

    try {
      const { loadDepthMapImageData } = await import('../utils/depthUtils');
      const { computeSimpleMask } = await import('../utils/inpaintMask');

      const depthMapUrl = analysisResult?.depthMapUrl;
      const depthData = depthMapUrl
        ? await loadDepthMapImageData(depthMapUrl)
        : null;

      // Inpaint each region one by one
      for (let i = 0; i < regions.length; i++) {
        const region = regions[i];
        if (depthData) {
          const maskUrl = computeOcclusionAwareMask(region, depthData, imageWidth, imageHeight);
          const prompt = `结合周围环境，自然替换/补全 ${region.depthLayer} 区域的细节`;
          const result = await inpaintImage(effectiveImageUrl, maskUrl, prompt);
          setInpaintPreview(result);
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setInpaintError(msg);
      console.error('Region inpaint failed:', err);
    } finally {
      setInpaintLoading(false);
    }
  }, [effectiveImageUrl, regions, dashscopeApiKey, analysisResult, imageWidth, imageHeight]);

  // ─── Strip pipeline: peel one layer ──────────────────────────────────────
  // Each invocation:
  //   1. Samples the depth of the current polygon (kept as the depthValue for this layer).
  //   2. Calls extractRegionBillboard on currentImageUrl + the polygon → layer's RGBA billboard.
  //   3. Builds an occlusion-aware inpaint mask (keeps the target's foreground pixels,
  //      inpaint only the occluded interior).
  //   4. Calls inpaintImage on currentImageUrl + mask → result.
  //   5. Pushes a StripStep and replaces currentImageUrl with the inpaint result.
  // After this completes, the canvas displays the image with this layer erased,
  // and the user can draw the next polygon (typically picking pixels of the next
  // depth layer that are now visible).
  const handleStripNextStep = useCallback(async () => {
    // Strip pipeline: the currently drawn polygon IS the layer to peel.
    // We don't require drawMode === 'drawing' so that the user can either:
    //   - click points → click "剥离下一步" directly (no Enter needed), or
    //   - click points → press Enter to lock the polygon visually → click "剥离下一步"
    // Previously this checked drawMode, which left the button grey after
    // Enter cleared the draw points via completeDrawing.
    if (drawPoints.length < 3) {
      setStripError('请先在画布上画一个多边形（至少 3 个点）');
      return;
    }
    if (!currentImageUrl) {
      setStripError('没有可剥离的图片');
      return;
    }
    if (!dashscopeApiKey) {
      setStripError('请先在顶部输入 DashScope API Key');
      return;
    }

    setStripping(true);
    setStripError(null);

    // Snapshot the current image — this is what we'll inpaint on.
    const baseImageUrl = currentImageUrl;

    try {
      // Lazy-load because these are only needed while stripping.
      const { loadDepthMapImageData, sampleDepthAtPolygon, autoAssignDepthLayer } =
        await import('../utils/depthUtils');
      const { computeSimpleMask } = await import('../utils/inpaintMask');

      // 1. Sample depth (+ auto layer) from the analysis depth map.
      //    Note: depthMapUrl is from the ORIGINAL analysis — we keep it across
      //    steps because each layer's Z position is determined by the original
      //    image's depth, not the inpainting result.
      const depthMapUrl = analysisResult?.depthMapUrl;
      let depthValue = 128;
      let depthLayer: import('../types').DepthLayerKey = 'foreground';
      if (depthMapUrl) {
        const depthData = await loadDepthMapImageData(depthMapUrl);
        depthValue = sampleDepthAtPolygon(depthData, drawPoints, imageWidth, imageHeight);
        depthLayer = autoAssignDepthLayer(depthValue);
      }

      // 2. Build a LayerRegion for this polygon (used for billboard extraction too).
      const regionId = `strip-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const region: import('../types').LayerRegion = {
        id: regionId,
        polygon: drawPoints,
        depthLayer,
        colorIndex: stripStack.length,
        source: 'manual',
        depthValue,
      };

      // 3. Extract the billboard (RGBA PNG) for this layer against the current image.
      //    This is the texture that will be mounted on the 3D plane later.
      const billboardUrl = await extractRegionBillboard(baseImageUrl, region);

      // 4. Build the inpaint mask: polygon interior = inpaint target.
      //
      //    Semantics for "peel a layer off the image":
      //      - The polygon outlines the area we want to remove (the layer).
      //      - LaMa fills the polygon interior with surrounding context (i.e.
      //        replaces the layer with what should be behind it).
      //      - The layer itself is preserved separately via extractRegionBillboard
      //        (server cuts out the polygon region with alpha).
      //
      //    We do NOT use depth-aware masking here: the previous implementation
      //    tried to keep foreground pixels (depth >= layerLow) and only inpaint
      //    the occluded interior (depth < layerLow). For a foreground polygon
      //    that is mostly at foreground depth, this produced an empty mask
      //    (0% non-zero pixels) and the server rejected it. The correct path is
      //    to paint the polygon interior entirely white so LaMa replaces it
      //    with background texture; the foreground is recovered via billboard.
      const maskUrl = computeSimpleMask(
        drawPoints,
        imageWidth || 1920,
        imageHeight || 1080,
      );

      // 5. Inpaint to produce the next image.
      const prompt = `基于周围自然环境，合成/补全 ${depthLayer} 区域被遮挡部分的逼真内容`;
      const inpaintResultUrl = await inpaintImage(baseImageUrl, maskUrl, prompt);

      // 6. Persist the billboard and push the strip step.
      setBillboardAsset(regionId, billboardUrl);
      pushStripStep({
        regionId,
        baseImageDataUrl: baseImageUrl,
        inpaintResultUrl,
        billboardUrl,
        layerPolygon: drawPoints,
        depthLayer,
        depthValue,
        colorIndex: stripStack.length,
      });

      // 7. Clear the in-flight polygon so the next strip step starts fresh.
      //    Done only on success path (after pushStripStep) so the user can
      //    retry with the same polygon if inpainting failed.
      clearDrawPoints();
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setStripError(msg);
      console.error('Strip step failed:', err);
    } finally {
      setStripping(false);
    }
  }, [
    drawPoints,
    currentImageUrl,
    dashscopeApiKey,
    analysisResult,
    imageWidth,
    imageHeight,
    stripStack.length,
    pushStripStep,
    setStripping,
    setStripError,
    setBillboardAsset,
    clearDrawPoints,
  ]);

  // Wrappers around strip-stack actions that also surface errors via setStripError.
  const handleUndoStripStep = useCallback(() => {
    try {
      undoLastStripStep();
      setStripError(null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setStripError(msg);
    }
  }, [undoLastStripStep, setStripError]);

  const handleResetStripStack = useCallback(() => {
    try {
      resetStripStack();
      setStripError(null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setStripError(msg);
    }
  }, [resetStripStack, setStripError]);

  const handleDepthSplit = useCallback(async (options?: { keepCurrentLayer?: boolean; switchToLayerView?: boolean }) => {
    const keepCurrentLayer = options?.keepCurrentLayer ?? true;
    const switchToLayerView = options?.switchToLayerView ?? true;

    if (!analysisResult?.depthMapUrl || !effectiveImageUrl) {
      setDepthSplitError('请先导入图片并完成 Analyze');
      return;
    }

    setDepthSplitLoading(true);
    setDepthSplitError(null);
    setDepthSplitConfirmed(false);

    try {
      const result = await splitDepthLayers(
        analysisResult.depthMapUrl,
        effectiveImageUrl,
        depthSplitThresholds,
      );
      setDepthSplitResult(result);
      if (!keepCurrentLayer || !selectedDepthLayer) {
        setSelectedDepthLayer('foreground');
      }
      if (switchToLayerView) {
        lastPreviewThresholdsRef.current = JSON.stringify(depthSplitThresholds);
        setImageMode('depth-layer');
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setDepthSplitError(msg);
      console.error('Depth split failed:', err);
    } finally {
      setDepthSplitLoading(false);
    }
  }, [
    analysisResult?.depthMapUrl,
    effectiveImageUrl,
    depthSplitThresholds,
    selectedDepthLayer,
    setDepthSplitConfirmed,
    setDepthSplitError,
    setDepthSplitLoading,
    setDepthSplitResult,
    setImageMode,
    setSelectedDepthLayer,
  ]);

  // JSON 序列化作为阈值"签名"：三个数字组合成一个稳定字符串，
  // 用于精确判断阈值是否真正发生变化（引用比较不够，需比较内容）
  const thresholdSignature = JSON.stringify(depthSplitThresholds);

  // ─── 阈值滑动时的防抖 + 增量预览 ────────────────────────────────────────
  // 防抖机制的作用：
  //   1. 避免用户拖动滑块时每次微小的数值变化都触发一次深度分层计算
  //   2. 120ms 延迟确保在快速连续拖动期间只执行最后一次有效更新
  //
  // thresholdSignature 比较逻辑：
  //   进入 depth-layer 模式后，将 ref 与当前签名对比——若相同则跳过（已是最新的预览结果），
  //   若不同才重新调用 handleDepthSplit，从而在阈值更新和实际计算之间建立缓冲。
  //
  // switchToLayerView: false 的意义：
  //   useEffect 触发时不切换视图模式，避免用户在调节滑块时被强制跳转回深度分层视图
  useEffect(() => {
    if (imageMode !== 'depth-layer') {
      lastPreviewThresholdsRef.current = thresholdSignature;
      return;
    }

    if (!depthSplitResult || !analysisResult?.depthMapUrl || !effectiveImageUrl) {
      lastPreviewThresholdsRef.current = null;
      return;
    }

    if (lastPreviewThresholdsRef.current === thresholdSignature) {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      lastPreviewThresholdsRef.current = thresholdSignature;
      void handleDepthSplit({ keepCurrentLayer: true, switchToLayerView: false });
    }, 120);

    return () => window.clearTimeout(timeoutId);
  }, [
    analysisResult?.depthMapUrl,
    depthSplitResult,
    effectiveImageUrl,
    handleDepthSplit,
    imageMode,
    thresholdSignature,
  ]);

  // 确认后：将分层结果从临时预览状态写入 store 的 depthLayerBillboardAssets，
  // 并将 depthSplitConfirmed 置为 true——这是 DioramaSettingsPanel 的渲染条件。
  // 换言之，只有确认后，Paper Diorama 2.0 面板才允许操作深度分层资源。
  const handleConfirmDepthSplit = useCallback(() => {
    const { depthSplitResult } = useAppStore.getState();
    if (!depthSplitResult) return;

    clearDepthLayerBillboardAssets();
    Object.entries(depthSplitResult).forEach(([layer, rgbaUrl]) => {
      setDepthLayerBillboardAsset(layer as keyof typeof depthSplitResult, rgbaUrl);
    });
    setDepthSplitConfirmed(true);
  }, [clearDepthLayerBillboardAssets, setDepthLayerBillboardAsset, setDepthSplitConfirmed]);

  // Confirm inpaint → replace cropped image, keep analysisResult for re-use
  const handleConfirmInpaint = () => {
    if (!inpaintPreviewUrl) return;
    // Convert data URL to base64 for store compatibility
    const base64 = inpaintPreviewUrl.split(',')[1] || '';
    const img = new Image();
    img.onload = () => {
      const { setImage, setCroppedImage, clearAllAssignments } = useAppStore.getState();
      setImage(inpaintPreviewUrl, base64, img.naturalWidth, img.naturalHeight);
      setCroppedImage(inpaintPreviewUrl, null);
      clearAllAssignments();
      setInpaintPreview(null);
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
  const currentLayerCount = currentLayerObjects.length;
  const hasImage = !!effectiveImageUrl;
  const canSplit = hasImage && assignedCount > 0;
  // Inpaint 反转语义：必须先在 LayerSelector 选一个图层，并且该图层上有物体
  const canInpaint = hasImage && selectedLayerIndex !== null && currentLayerCount > 0;

  return (
    <>
      <div className="flex flex-col gap-3 p-4 bg-gray-900 border-t border-gray-700 shrink-0">
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

        {/* Depth split error */}
        {depthSplitError && (
          <div className="flex items-center gap-2 text-amber-400">
            <AlertCircle size={16} />
            <span className="text-sm">{depthSplitError}</span>
          </div>
        )}

        {/* Depth split thresholds */}
        <div className="rounded-xl border border-cyan-900/60 bg-gray-950/70 p-3">
          <div className="flex items-center justify-between gap-3 mb-3">
            <div>
              <div className="text-sm font-medium text-cyan-200">Depth Split 阈值</div>
              <div className="text-xs text-gray-400">当前按“白近黑远”解释：更亮的区域更靠前。</div>
            </div>
            <div className="flex items-center gap-2">
              <div className="text-[11px] text-gray-500">foreground ≥ midground ≥ background</div>
              <button
                type="button"
                onClick={() => setDepthSplitThresholds(DEFAULT_DEPTH_SPLIT_THRESHOLDS)}
                className="px-2.5 py-1 rounded-md border border-gray-700 bg-gray-900 text-xs text-gray-300 hover:border-cyan-700 hover:text-cyan-200 transition-colors"
              >
                重置默认阈值
              </button>
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            <label className="flex flex-col gap-2">
              <div className="flex items-center justify-between text-xs text-gray-300">
                <span>前景下限</span>
                <span>{depthSplitThresholds.foregroundMin}</span>
              </div>
              <input
                type="range"
                min={0}
                max={255}
                value={depthSplitThresholds.foregroundMin}
                onChange={(e) => updateDepthThreshold('foregroundMin', Number(e.target.value))}
                className="w-full accent-cyan-400"
              />
            </label>

            <label className="flex flex-col gap-2">
              <div className="flex items-center justify-between text-xs text-gray-300">
                <span>中景下限</span>
                <span>{depthSplitThresholds.midgroundMin}</span>
              </div>
              <input
                type="range"
                min={0}
                max={255}
                value={depthSplitThresholds.midgroundMin}
                onChange={(e) => updateDepthThreshold('midgroundMin', Number(e.target.value))}
                className="w-full accent-cyan-400"
              />
            </label>

            <label className="flex flex-col gap-2">
              <div className="flex items-center justify-between text-xs text-gray-300">
                <span>背景下限</span>
                <span>{depthSplitThresholds.backgroundMin}</span>
              </div>
              <input
                type="range"
                min={0}
                max={255}
                value={depthSplitThresholds.backgroundMin}
                onChange={(e) => updateDepthThreshold('backgroundMin', Number(e.target.value))}
                className="w-full accent-cyan-400"
              />
            </label>
          </div>

          <div className="mt-3 text-xs text-gray-500">
            sky &lt; {depthSplitThresholds.backgroundMin}，background {`≥ ${depthSplitThresholds.backgroundMin}`}，midground {`≥ ${depthSplitThresholds.midgroundMin}`}，foreground {`≥ ${depthSplitThresholds.foregroundMin}`}
          </div>
        </div>

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
            {splitting ? '抠取中...' : '抠取物体'}
            {assignedCount > 0 && !splitting && (
              <span className="ml-1 bg-blue-700 rounded px-1.5 py-0.5 text-xs">{assignedCount}</span>
            )}
          </button>

          <button
            onClick={() => {
              void handleDepthSplit({ keepCurrentLayer: false, switchToLayerView: true });
            }}
            disabled={splitting || inpaintLoading || depthSplitLoading || !analysisResult?.depthMapUrl || !hasImage}
            className={`
              flex items-center gap-2 px-4 py-2 rounded-lg font-medium text-sm transition-all
              ${splitting || inpaintLoading || depthSplitLoading || !analysisResult?.depthMapUrl || !hasImage
                ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
                : 'bg-cyan-600 hover:bg-cyan-500 text-white active:scale-95'}
            `}
          >
            {depthSplitLoading ? <Loader2 size={16} className="animate-spin" /> : <Layers3 size={16} />}
            {depthSplitLoading ? '分层中...' : '按深度分层'}
          </button>

          {/* Freehand polygon draw button */}
          {analysisResult && (
            <button
              onClick={drawMode === 'idle' ? startDrawing : cancelDrawing}
              className={`
                flex items-center gap-2 px-4 py-2 rounded-lg font-medium text-sm transition-all
                ${drawMode === 'drawing'
                  ? 'bg-amber-600 hover:bg-amber-500 text-white active:scale-95'
                  : 'bg-gray-700 hover:bg-gray-600 text-gray-200 active:scale-95'}
              `}
            >
              {drawMode === 'drawing' ? <MousePointer2 size={16} /> : <Pencil size={16} />}
              {drawMode === 'drawing'
                ? `取消绘制${drawPoints.length > 0 ? ` (${drawPoints.length} 点)` : ''}`
                : '自由选区'}
            </button>
          )}

          {/* Inpaint all drawn regions */}
          {regions.length > 0 && (
            <button
              onClick={() => { void handleRegionInpaint(); }}
              disabled={inpaintLoading || !dashscopeApiKey}
              className={`
                flex items-center gap-2 px-4 py-2 rounded-lg font-medium text-sm transition-all
                ${inpaintLoading || !dashscopeApiKey
                  ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
                  : 'bg-orange-600 hover:bg-orange-500 text-white active:scale-95'}
              `}
            >
              {inpaintLoading ? <Loader2 size={16} className="animate-spin" /> : <Wand2 size={16} />}
              {inpaintLoading ? '补全中...' : '补全选区'}
              <span className="ml-1 bg-orange-700 rounded px-1.5 py-0.5 text-xs">{regions.length}</span>
            </button>
          )}

          {/* Strip pipeline: peel the next layer (near → far). Each press
              turns the currently drawn polygon into a 3D billboard and
              replaces the canvas image with the inpainting result, so the
              next layer's pixels are now visible for the user to outline. */}
          <div className="flex items-center gap-2 ml-2 pl-2 border-l border-gray-700">
            <button
              onClick={() => { void handleStripNextStep(); }}
              disabled={
                isStripping ||
                drawPoints.length < 3 ||
                !currentImageUrl ||
                !dashscopeApiKey
              }
              data-testid="strip-next-step"
              className={`
                flex items-center gap-2 px-4 py-2 rounded-lg font-medium text-sm transition-all
                ${isStripping ||
                drawPoints.length < 3 ||
                !currentImageUrl ||
                !dashscopeApiKey
                  ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
                  : 'bg-emerald-600 hover:bg-emerald-500 text-white active:scale-95'}
              `}
              title={drawPoints.length < 3
                ? '请先在画布上画一个多边形（至少 3 个点）'
                : '使用当前 polygon 剥离一层'}
            >
              {isStripping ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
              {isStripping ? '剥离中...' : '剥离下一步'}
              {drawPoints.length >= 3 && (
                <span className="ml-1 bg-emerald-700 rounded px-1.5 py-0.5 text-xs">
                  {drawPoints.length} 点
                </span>
              )}
            </button>

            {drawMode === 'drawing' && drawPoints.length >= 3 && (
              <span className="text-xs text-emerald-300/80">
                画完直接点「剥离下一步」即可（无需按 Enter）
              </span>
            )}

            <button
              onClick={handleUndoStripStep}
              disabled={isStripping || stripStack.length === 0}
              className={`
                flex items-center gap-2 px-3 py-2 rounded-lg font-medium text-sm transition-all
                ${isStripping || stripStack.length === 0
                  ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
                  : 'bg-gray-700 hover:bg-gray-600 text-gray-200 active:scale-95'}
              `}
            >
              <Undo2 size={14} />
              撤销
            </button>

            <button
              onClick={handleResetStripStack}
              disabled={isStripping || stripStack.length === 0}
              className={`
                flex items-center gap-2 px-3 py-2 rounded-lg font-medium text-sm transition-all
                ${isStripping || stripStack.length === 0
                  ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
                  : 'bg-gray-700 hover:bg-gray-600 text-gray-200 active:scale-95'}
              `}
            >
              <Trash2 size={14} />
              重置
            </button>

            {stripStack.length > 0 && (
              <span className="ml-1 text-xs text-emerald-400 self-center">
                已剥离 {stripStack.length} 层
              </span>
            )}
          </div>

          {stripError && (
            <div className="flex items-center gap-2 text-red-400">
              <AlertCircle size={16} />
              <span className="text-sm">{stripError}</span>
            </div>
          )}

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
            {inpaintLoading ? '补全中...' : '补全背景'}
            {selectedLayerIndex !== null && currentLayerCount > 0 && !inpaintLoading && (
              <span className="ml-1 bg-purple-700 rounded px-1.5 py-0.5 text-xs">{currentLayerCount}</span>
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
          {analysisResult && selectedLayerIndex === null && assignedCount > 0 && (
            <span className="ml-auto text-xs text-amber-400 self-center">
              请先在左侧分组里选择要补全的目标图层
            </span>
          )}
          {analysisResult && selectedLayerIndex !== null && currentLayerCount === 0 && (
            <span className="ml-auto text-xs text-amber-400 self-center">
              当前图层（第 {selectedLayerIndex + 1} 组）暂未分配物体，请先点击物体分配到此图层
            </span>
          )}
          {regions.length > 0 && (
            <span className="ml-2 text-xs text-cyan-400 self-center">
              {regions.length} 个自由选区
              <button
                onClick={() => { if (confirm('清除所有自由选区？')) setRegions([]); }}
                className="ml-2 text-red-400 hover:text-red-300 underline"
              >
                清除
              </button>
            </span>
          )}
        </div>
      </div>

      {depthSplitResult && (
        <DepthSplitPanel
          result={depthSplitResult}
          selectedLayer={selectedDepthLayer}
          isConfirmed={depthSplitConfirmed}
          onSelectLayer={(layer) => {
            setSelectedDepthLayer(layer);
            setImageMode('depth-layer');
          }}
          onConfirm={handleConfirmDepthSplit}
        />
      )}

      {/* Paper Diorama 2.0 — always visible when depth split exists */}
      <DioramaSettingsPanel
        effectiveImageUrl={effectiveImageUrl}
        depthSplitResult={depthSplitResult}
      />

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
