// ?????????????????????????????????????????????????????????????????????????????
// Viewer3D ? Three.js Paper Diorama 3D Scene
// Supports: Billboard mode | Paper Diorama mode
// Paper Diorama: BoxGeometry (3D paper thickness), normal maps, outline edges, parallax animation
// ?????????????????????????????????????????????????????????????????????????????
import { useRef, useMemo, useCallback, useEffect, useState } from 'react';
import { Canvas, useThree } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';
import { useAppStore } from '../store/useAppStore';
import { LAYER_COLORS, DEPTH_LAYER_Z } from '../types';
import type { DepthLayerKey, DetectedObject, LayerRegion } from '../types';
import { zForRegion } from '../utils/depthUtils';
import { ExportPanel } from './ExportPanel';

// Scene dimensions (world units)
const SCENE_WIDTH = 20;
const SCENE_HEIGHT = 15;

// DEPTH_LAYER_Z imported from '../types'

// 各层纸模厚度（world units），由 dioramaParams.thicknessMax 缩放
const LAYER_THICKNESS: Record<DepthLayerKey, number> = {
  sky: 0.08,
  background: 0.12,
  midground: 0.20,
  foreground: 0.30,
};

const DEPTH_LAYER_ORDER: DepthLayerKey[] = ['foreground', 'midground', 'background', 'sky'];

// Texture cache — persists across component re-renders
const textureCache = new Map<string, THREE.Texture>();

function getOrLoadTexture(url: string, key: string): THREE.Texture {
  if (textureCache.has(key)) return textureCache.get(key)!;
  const loader = new THREE.TextureLoader();
  const tex = loader.load(url);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.wrapS = THREE.ClampToEdgeWrapping;
  tex.wrapT = THREE.ClampToEdgeWrapping;
  textureCache.set(key, tex);
  return tex;
}

function disposeCache() {
  textureCache.forEach((tex) => tex.dispose());
  textureCache.clear();
}

// Directional light for paper diorama shading
function PaperDioramaLighting() {
  return (
    <>
      <ambientLight intensity={0.8} />
      <directionalLight position={[5, 8, 10]} intensity={1.2} color="#fff8e1" />
      <directionalLight position={[-4, -3, 5]} intensity={0.3} color="#e3f2fd" />
    </>
  );
}

// Billboard mesh (flat plane)
interface BillboardMeshProps {
  obj: DetectedObject;
  colorIndex: number;
  texture?: THREE.Texture;
  onSelect: (id: string) => void;
}

function BillboardMesh({ obj, colorIndex, texture, onSelect }: BillboardMeshProps) {
  const billboardOffsets = useAppStore((s) => s.billboardOffsets);
  const offset = billboardOffsets[obj.id];
  const color = LAYER_COLORS[colorIndex];

  const posX = useMemo(() => {
    const cx = obj.boundingBox.x + obj.boundingBox.w / 2;
    return (cx - 0.5) * SCENE_WIDTH + (offset?.offsetX ?? 0);
  }, [obj.boundingBox, offset]);

  const posY = useMemo(() => {
    const cy = 1 - (obj.boundingBox.y + obj.boundingBox.h / 2);
    return (cy - 0.5) * SCENE_HEIGHT;
  }, [obj.boundingBox]);

  const posZ = useMemo(() => {
    const clampedDepth = Math.max(0, Math.min(obj.depth, 50));
    return (clampedDepth / 50) * 10 - 5;
  }, [obj.depth]);

  const sizeX = obj.boundingBox.w * SCENE_WIDTH;
  const sizeY = obj.boundingBox.h * SCENE_HEIGHT;

  const material = useMemo(() => {
    if (texture) {
      return new THREE.MeshBasicMaterial({ map: texture, transparent: true, side: THREE.DoubleSide, opacity: 1 });
    }
    return new THREE.MeshBasicMaterial({ color: new THREE.Color(color), transparent: true, opacity: 0.5, side: THREE.DoubleSide });
  }, [texture, color]);

  useEffect(() => { return () => { material.dispose(); }; }, [material]);

  const handleClick = useCallback((e: THREE.Event) => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (e as any).stopPropagation?.();
    onSelect(obj.id);
  }, [obj.id, onSelect]);

  return (
    <mesh position={[posX, posY, posZ]} onClick={handleClick}>
      <planeGeometry args={[sizeX, sizeY]} />
      <primitive object={material} attach="material" />
    </mesh>
  );
}

// Paper Diorama layer mesh (BoxGeometry with thickness)
interface PaperLayerMeshProps {
  layer: DepthLayerKey;
  frontTexture: THREE.Texture;
  thicknessGrayTexture?: THREE.Texture;
  normalMapTexture?: THREE.Texture;
  thickness: number;
}

function PaperLayerMesh({ layer, frontTexture, thicknessGrayTexture, normalMapTexture, thickness }: PaperLayerMeshProps) {
  const z = DEPTH_LAYER_Z[layer];

  const frontMat = useMemo(() => {
    const m = new THREE.MeshStandardMaterial({ map: frontTexture, transparent: true, side: THREE.FrontSide, roughness: 0.9, metalness: 0.0 });
    if (normalMapTexture) m.normalMap = normalMapTexture;
    return m;
  }, [frontTexture, normalMapTexture]);

  const sideMat = useMemo(() => {
    if (thicknessGrayTexture) {
      const m = new THREE.MeshStandardMaterial({ map: thicknessGrayTexture, transparent: true, side: THREE.FrontSide, roughness: 0.8, metalness: 0.0 });
      if (normalMapTexture) m.normalMap = normalMapTexture;
      return m;
    }
    return new THREE.MeshStandardMaterial({ color: new THREE.Color('#f5f0e8'), transparent: true, opacity: 0.95, side: THREE.FrontSide, roughness: 0.8, metalness: 0.0 });
  }, [thicknessGrayTexture, normalMapTexture]);

  useEffect(() => { return () => { frontMat.dispose(); sideMat.dispose(); }; }, [frontMat, sideMat]);

  return (
    <mesh position={[0, 0, z]} castShadow receiveShadow>
      <boxGeometry args={[SCENE_WIDTH, SCENE_HEIGHT, thickness]} />
      <primitive object={frontMat} attach="material-4" />
      <primitive object={frontMat} attach="material-5" />
      <primitive object={sideMat} attach="material-0" />
      <primitive object={sideMat} attach="material-1" />
      <primitive object={sideMat} attach="material-2" />
      <primitive object={sideMat} attach="material-3" />
    </mesh>
  );
}

// Paper Diorama individual object mesh
interface PaperObjectMeshProps {
  obj: DetectedObject;
  colorIndex: number;
  frontTexture: THREE.Texture;
  thickness: number;
  onSelect: (id: string) => void;
}

function PaperObjectMesh({ obj, colorIndex, frontTexture, thickness, onSelect }: PaperObjectMeshProps) {
  const billboardOffsets = useAppStore((s) => s.billboardOffsets);
  const offset = billboardOffsets[obj.id];
  const color = LAYER_COLORS[colorIndex];

  const posX = useMemo(() => {
    const cx = obj.boundingBox.x + obj.boundingBox.w / 2;
    return (cx - 0.5) * SCENE_WIDTH + (offset?.offsetX ?? 0);
  }, [obj.boundingBox, offset]);

  const posY = useMemo(() => {
    const cy = 1 - (obj.boundingBox.y + obj.boundingBox.h / 2);
    return (cy - 0.5) * SCENE_HEIGHT;
  }, [obj.boundingBox]);

  const posZ = useMemo(() => {
    const clampedDepth = Math.max(0, Math.min(obj.depth, 50));
    return (clampedDepth / 50) * 10 - 5;
  }, [obj.depth]);

  const sizeX = obj.boundingBox.w * SCENE_WIDTH;
  const sizeY = obj.boundingBox.h * SCENE_HEIGHT;

  const frontMat = useMemo(() => {
    if (frontTexture) {
      return new THREE.MeshStandardMaterial({ map: frontTexture, transparent: true, side: THREE.FrontSide, roughness: 0.9, metalness: 0.0 });
    }
    return new THREE.MeshStandardMaterial({ color: new THREE.Color(color), transparent: true, opacity: 0.7, side: THREE.FrontSide, roughness: 0.9, metalness: 0.0 });
  }, [frontTexture, color]);

  const sideMat = useMemo(() => new THREE.MeshStandardMaterial({
    color: new THREE.Color('#f0ebe0'), transparent: true, opacity: 0.95, side: THREE.FrontSide, roughness: 0.85, metalness: 0.0,
  }), []);

  useEffect(() => { return () => { frontMat.dispose(); sideMat.dispose(); }; }, [frontMat, sideMat]);

  const handleClick = useCallback((e: THREE.Event) => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (e as any).stopPropagation?.();
    onSelect(obj.id);
  }, [obj.id, onSelect]);

  return (
    <mesh position={[posX, posY, posZ]} onClick={handleClick} castShadow receiveShadow>
      <boxGeometry args={[sizeX, sizeY, thickness]} />
      <primitive object={frontMat} attach="material-4" />
      <primitive object={frontMat} attach="material-5" />
      <primitive object={sideMat} attach="material-0" />
      <primitive object={sideMat} attach="material-1" />
      <primitive object={sideMat} attach="material-2" />
      <primitive object={sideMat} attach="material-3" />
    </mesh>
  );
}

// Outline edge effect for paper mode
interface OutlineEdgeProps {
  layer: DepthLayerKey;
  texture: THREE.Texture;
  outlineEnabled: boolean;
}

function OutlineEdge({ layer, texture, outlineEnabled }: OutlineEdgeProps) {
  if (!outlineEnabled) return null;
  const z = DEPTH_LAYER_Z[layer];
  const color = layer === 'foreground' ? '#ffffff' : '#e0ddd8';
  return (
    <mesh position={[0, 0, z + 0.01]}>
      <planeGeometry args={[SCENE_WIDTH, SCENE_HEIGHT]} />
      <meshBasicMaterial map={texture} transparent alphaTest={0.05} depthWrite={false} color={new THREE.Color(color)} opacity={0.3} />
    </mesh>
  );
}

// Background plane (depth map)
// Background plane — shows the strip pipeline's current image (the original
// once at the start, or the inpainting result after the last strip step).
// If no in-progress strip pipeline is running, falls back to the depth map.
interface BackgroundPlaneProps {
  urlOverride?: string;
}

function BackgroundPlane({ urlOverride }: BackgroundPlaneProps = {}) {
  const analysisResult = useAppStore((s) => s.analysisResult);
  const depthUrl = analysisResult?.depthMapUrl;

  // Prefer urlOverride (the "currentImageUrl" — the image with stripped layers
  // already removed). When no override is provided, fall back to the depth map.
  const textureUrl = urlOverride || depthUrl;
  const cacheKey = urlOverride ? 'strip-current' : 'depth-bg';
  const texture = useMemo(() => textureUrl ? getOrLoadTexture(textureUrl, cacheKey) : null, [textureUrl, cacheKey]);
  if (!texture) return null;
  return (
    <mesh position={[0, 0, DEPTH_LAYER_Z.sky - 0.5]}>
      <planeGeometry args={[SCENE_WIDTH, SCENE_HEIGHT]} />
      <meshBasicMaterial map={texture} transparent opacity={0.25} side={THREE.DoubleSide} />
    </mesh>
  );
}

// Region mesh — renders a manually drawn LayerRegion as a billboard
interface RegionMeshProps {
  region: LayerRegion;
  texture?: THREE.Texture;
  onSelect: (id: string) => void;
}

function RegionMesh({ region, texture, onSelect }: RegionMeshProps) {
  const color = LAYER_COLORS[region.colorIndex % LAYER_COLORS.length];

  const posX = useMemo(() => {
    const sumX = region.polygon.reduce((s, [x]) => s + x, 0);
    const cx = sumX / region.polygon.length;
    return (cx - 0.5) * SCENE_WIDTH;
  }, [region.polygon]);

  const posY = useMemo(() => {
    const sumY = region.polygon.reduce((s, [, y]) => s + y, 0);
    const cy = sumY / region.polygon.length;
    return (cy - 0.5) * SCENE_HEIGHT;
  }, [region.polygon]);

  const posZ = useMemo(() => zForRegion(region), [region]);

  const material = useMemo(() => {
    if (texture) {
      return new THREE.MeshBasicMaterial({ map: texture, transparent: true, side: THREE.DoubleSide, opacity: 0.9 });
    }
    return new THREE.MeshBasicMaterial({ color: new THREE.Color(color), transparent: true, opacity: 0.55, side: THREE.DoubleSide });
  }, [texture, color]);

  useEffect(() => { return () => { material.dispose(); }; }, [material]);

  const handleClick = useCallback((e: THREE.Event) => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (e as any).stopPropagation?.();
    onSelect(region.id);
  }, [region.id, onSelect]);

  return (
    <mesh position={[posX, posY, posZ]} onClick={handleClick}>
      <planeGeometry args={[SCENE_WIDTH, SCENE_HEIGHT]} />
      <primitive object={material} attach="material" />
    </mesh>
  );
}

// Scene content
interface SceneContentProps {
  onSelectObject: (id: string) => void;
}

function SceneContent({ onSelectObject }: SceneContentProps) {
  const analysisResult = useAppStore((s) => s.analysisResult);
  const assignments = useAppStore((s) => s.assignments);
  const billboardAssets = useAppStore((s) => s.billboardAssets);
  const depthLayerBillboardAssets = useAppStore((s) => s.depthLayerBillboardAssets);
  const depthLayerDioramaAssets = useAppStore((s) => s.depthLayerDioramaAssets);
  const objectDioramaAssets = useAppStore((s) => s.objectDioramaAssets);
  const dioramaMode = useAppStore((s) => s.dioramaMode);
  const outlineEnabled = useAppStore((s) => s.outlineEnabled);
  const dioramaParams = useAppStore((s) => s.dioramaParams);
  const regions = useAppStore((s) => s.regions);
  // Strip pipeline: when stripStack is non-empty, prefer rendering layers
  // from it (each step has its own polygon/depth/billboard URL) over the
  // legacy `regions` array. The two are mutually exclusive in practice.
  const stripStack = useAppStore((s) => s.stripStack);
  const currentImageUrl = useAppStore((s) => s.currentImageUrl);

  const objects = analysisResult?.objects ?? [];

  const assignedObjects = useMemo(
    () => objects.filter((o) => assignments[o.id] !== undefined),
    [objects, assignments],
  );

  const isPaperMode = dioramaMode === 'paper';

  useEffect(() => { return () => { disposeCache(); }; }, []);

  return (
    <>
      <BackgroundPlane urlOverride={currentImageUrl} />
      {isPaperMode ? <PaperDioramaLighting /> : <ambientLight intensity={1} />}

      {/* Paper Diorama depth layer meshes */}
      {isPaperMode && DEPTH_LAYER_ORDER.map((layer) => {
        const dioramaAsset = depthLayerDioramaAssets[layer];
        const billboardAsset = depthLayerBillboardAssets[layer];
        const frontUrl = dioramaAsset?.outlinedUrl
          || dioramaAsset?.paperStyleUrl
          || dioramaAsset?.rgbaUrl
          || billboardAsset?.rgbaUrl;
        if (!frontUrl) return null;
        const tex = getOrLoadTexture(frontUrl, `paper-layer-${layer}`);
        const thicknessWorld = LAYER_THICKNESS[layer] * (dioramaParams.thicknessMax / 5.0);
        const normalTex = dioramaAsset?.normalMapUrl ? getOrLoadTexture(dioramaAsset.normalMapUrl, `normal-layer-${layer}`) : undefined;
        const thicknessGrayTex = dioramaAsset?.thicknessGrayUrl ? getOrLoadTexture(dioramaAsset.thicknessGrayUrl, `thickness-layer-${layer}`) : undefined;
        return (
          <PaperLayerMesh key={layer} layer={layer} frontTexture={tex}
            normalMapTexture={normalTex} thicknessGrayTexture={thicknessGrayTex} thickness={thicknessWorld} />
        );
      })}

      {/* Paper Diorama individual object meshes */}
      {isPaperMode && assignedObjects.map((obj) => {
        const colorIndex = assignments[obj.id];
        const dioramaAsset = objectDioramaAssets[obj.id];
        const billboardAsset = billboardAssets[obj.id];
        const textureUrl = dioramaAsset?.paperStyleUrl
          || dioramaAsset?.outlinedUrl
          || dioramaAsset?.rgbaUrl
          || billboardAsset?.rgbaUrl;
        const tex = textureUrl
          ? getOrLoadTexture(textureUrl, `paper-obj-${obj.id}`)
          : getOrLoadTexture(`data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==`, `fallback-${obj.id}`);
        const thicknessWorld = LAYER_THICKNESS.foreground * (dioramaParams.thicknessMax / 5.0);
        return (
          <PaperObjectMesh key={obj.id} obj={obj} colorIndex={colorIndex}
            frontTexture={tex} thickness={thicknessWorld} onSelect={onSelectObject} />
        );
      })}

      {/* Billboard depth layer planes */}
      {!isPaperMode && DEPTH_LAYER_ORDER.map((layer) => {
        const asset = depthLayerBillboardAssets[layer];
        if (!asset?.rgbaUrl) return null;
        const tex = getOrLoadTexture(asset.rgbaUrl, `depth-layer-${layer}`);
        return (
          <mesh key={layer} position={[0, 0, DEPTH_LAYER_Z[layer]]}>
            <planeGeometry args={[SCENE_WIDTH, SCENE_HEIGHT]} />
            <meshBasicMaterial map={tex} transparent side={THREE.DoubleSide} opacity={0.92} depthWrite={false} />
          </mesh>
        );
      })}

      {/* Billboard individual objects */}
      {!isPaperMode && assignedObjects.map((obj) => {
        const colorIndex = assignments[obj.id];
        const asset = billboardAssets[obj.id];
        const tex = asset?.rgbaUrl ? getOrLoadTexture(asset.rgbaUrl, `billboard-${obj.id}`) : undefined;
        return (
          <BillboardMesh key={obj.id} obj={obj} colorIndex={colorIndex} texture={tex} onSelect={onSelectObject} />
        );
      })}

      {/* Layer regions (manually drawn polygons).
          Prefer stripStack (the result of the strip pipeline) when present,
          because it has the authoritative billboard + depth info for each
          peeled layer. Fall back to the legacy `regions` array for the
          user-drawn standalone regions. */}
      {stripStack.length > 0
        ? stripStack.map((step) => (
            <RegionMesh
              key={step.regionId}
              region={{
                id: step.regionId,
                polygon: step.layerPolygon,
                depthLayer: step.depthLayer,
                colorIndex: step.colorIndex,
                source: 'manual',
                depthValue: step.depthValue,
              }}
              texture={step.billboardUrl ? getOrLoadTexture(step.billboardUrl, `strip-${step.regionId}`) : undefined}
              onSelect={onSelectObject}
            />
          ))
        : regions.map((region) => {
            const regionAsset = billboardAssets[region.id];
            const tex = regionAsset?.rgbaUrl ? getOrLoadTexture(regionAsset.rgbaUrl, `region-${region.id}`) : undefined;
            return (
              <RegionMesh key={region.id} region={region} texture={tex} onSelect={onSelectObject} />
            );
          })}

      {/* Outline edges overlay for paper mode */}
      {isPaperMode && outlineEnabled && DEPTH_LAYER_ORDER.map((layer) => {
        const dioramaAsset = depthLayerDioramaAssets[layer];
        const billboardAsset = depthLayerBillboardAssets[layer];
        const textureUrl = dioramaAsset?.outlinedUrl
          || dioramaAsset?.paperStyleUrl
          || dioramaAsset?.rgbaUrl
          || billboardAsset?.rgbaUrl;
        if (!textureUrl) return null;
        const tex = getOrLoadTexture(textureUrl, `outline-${layer}`);
        return <OutlineEdge key={`outline-${layer}`} layer={layer} texture={tex} outlineEnabled />;
      })}

      <gridHelper args={[SCENE_WIDTH, 20, '#333333', '#222222']} position={[0, -SCENE_HEIGHT / 2, 0]} />
    </>
  );
}

// Expose WebGL canvas DOM element
interface GlDomElementProps {
  onDomReady: (el: HTMLCanvasElement) => void;
}

function GlDomElement({ onDomReady }: GlDomElementProps) {
  const { gl } = useThree();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { onDomReady(gl.domElement); }, []);
  return null;
}

// Camera controller
function CameraController() {
  return (
    <OrbitControls makeDefault enableDamping dampingFactor={0.05} minDistance={3} maxDistance={60} />
  );
}

// Main export
export function Viewer3D() {
  const analysisResult = useAppStore((s) => s.analysisResult);
  const selectedObjectId = useAppStore((s) => s.selectedObjectId);
  const setSelectedObjectId = useAppStore((s) => s.setSelectedObjectId);
  const editMode = useAppStore((s) => s.editMode);
  const dioramaMode = useAppStore((s) => s.dioramaMode);
  const regions = useAppStore((s) => s.regions);

  const [glCanvas, setGlCanvas] = useState<HTMLCanvasElement | null>(null);

  const handleSelect = useCallback(
    (id: string) => { setSelectedObjectId(selectedObjectId === id ? null : id); },
    [selectedObjectId, setSelectedObjectId],
  );

  const hasAssignments = analysisResult?.objects
    ? Object.keys(useAppStore.getState().assignments).length > 0
    : false;

  return (
    <div className="relative w-full h-full bg-gray-950">
      <Canvas gl={{ antialias: true, alpha: false }} shadows style={{ background: '#0a0a0f' }}>
        <color attach="background" args={['#0a0a0f']} />
        <GlDomElement onDomReady={setGlCanvas} />
        <SceneContent onSelectObject={handleSelect} />
        <CameraController />
      </Canvas>

      <div className="absolute top-3 right-3 flex items-center gap-2">
        <span className={`px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wider ${dioramaMode === 'paper' ? 'bg-amber-600 text-white' : 'bg-blue-600 text-white'}`}>
          {dioramaMode === 'paper' ? 'Paper' : '3D'}
        </span>
        <span className={`px-2 py-1 rounded-full text-xs font-semibold uppercase tracking-wider ${editMode === 'director' ? 'bg-purple-600 text-white' : 'bg-blue-600 text-white'}`}>
          {editMode === 'director' ? 'Director' : 'Camera'}
        </span>
      </div>

      {selectedObjectId && analysisResult && (
        <div className="absolute bottom-3 left-3 bg-black/70 text-white text-xs px-3 py-2 rounded-lg">
          Selected: {selectedObjectId}
        </div>
      )}

      {!hasAssignments && regions.length === 0 && analysisResult && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <p className="text-gray-600 text-sm">Assign objects or draw regions to see them here</p>
        </div>
      )}

      <ExportPanel canvasRef={{ current: glCanvas }} />
    </div>
  );
}
