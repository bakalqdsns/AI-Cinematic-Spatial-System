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
import { LAYER_COLORS } from '../types';
import type { DepthLayerKey, DetectedObject } from '../types';
import { ExportPanel } from './ExportPanel';

// Scene dimensions (world units)
// 20:15 = 4:3 ???????????????????
// ???? FOV=50? ? position z=15????????
const SCENE_WIDTH = 20;
const SCENE_HEIGHT = 15;

// Z??????=-20???????=-12???=-6???=-2
// ??????????? z=15??-z?????-20 ~ -2 ????18??????
// ?????20???15???????????????????
const DEPTH_LAYER_Z: Record<DepthLayerKey, number> = {
  sky: -20,
  background: -12,
  midground: -6,
  foreground: -2,
};

// ??????????????? = ?? ? dioramaParams.thicknessMax
// ??????????????20x15????????0.08~0.30????????
// ???"??"??????????????????????
const LAYER_THICKNESS: Record<DepthLayerKey, number> = {
  sky: 0.08,
  background: 0.12,
  midground: 0.20,
  foreground: 0.30,
};

const DEPTH_LAYER_ORDER: DepthLayerKey[] = ['foreground', 'midground', 'background', 'sky'];

// ??? Texture cache ?????????????????????????????????????????????????????????????
// ?? Map ?? React state ????
// React state ????? SceneContent ?????? SceneContent ????? useMemo/useCallback ????
// textureCache ??????????????????? URL ??????????
// ?? useEffect cleanup ?????? dispose() ?????
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

// ??? Directional light for paper diorama shading ???????????????????????????????
function PaperDioramaLighting() {
  return (
    <>
      <ambientLight intensity={0.8} />
      <directionalLight
        position={[5, 8, 10]}
        intensity={1.2}
        color="#fff8e1"
      />
      {/* Soft fill from below-left to enhance paper thickness look */}
      <directionalLight
        position={[-4, -3, 5]}
        intensity={0.3}
        color="#e3f2fd"
      />
    </>
  );
}

// ??? Billboard mesh (flat plane) ???????????????????????????????????????????????
interface BillboardMeshProps {
  obj: DetectedObject;
  colorIndex: number;
  texture?: THREE.Texture;
  onSelect: (id: string) => void;
}

function BillboardMesh({ obj, colorIndex, texture, onSelect }: BillboardMeshProps) {
  const meshRef = useRef<THREE.Mesh>(null);
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

  // obj.depth ?? 0-50?AI ??????????????? [-5, 5] ????
  // ???depth/50*10 - 5 = ????? ? z ????
  // ?????? depth ??????????????????? z ??
  const posZ = useMemo(() => {
    const clampedDepth = Math.max(0, Math.min(obj.depth, 50));
    return (clampedDepth / 50) * 10 - 5;
  }, [obj.depth]);

  const sizeX = obj.boundingBox.w * SCENE_WIDTH;
  const sizeY = obj.boundingBox.h * SCENE_HEIGHT;

  const material = useMemo(() => {
    if (texture) {
      return new THREE.MeshBasicMaterial({
        map: texture,
        transparent: true,
        side: THREE.DoubleSide,
        opacity: 1,
      });
    }
    return new THREE.MeshBasicMaterial({
      color: new THREE.Color(color),
      transparent: true,
      opacity: 0.5,
      side: THREE.DoubleSide,
    });
  }, [texture, color]);

  useEffect(() => {
    return () => { material.dispose(); };
  }, [material]);

  const handleClick = useCallback((e: THREE.Event) => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (e as any).stopPropagation?.();
    // ??????? OrbitControls??????????????
    onSelect(obj.id);
  }, [obj.id, onSelect]);

  return (
    <mesh ref={meshRef} position={[posX, posY, posZ]} onClick={handleClick}>
      <planeGeometry args={[sizeX, sizeY]} />
      <primitive object={material} attach="material" />
    </mesh>
  );
}

// ??? Paper Diorama layer mesh (BoxGeometry with thickness) ?????????????????????
interface PaperLayerMeshProps {
  layer: DepthLayerKey;
  frontTexture: THREE.Texture;
  thicknessGrayTexture?: THREE.Texture;
  normalMapTexture?: THREE.Texture;
  thickness: number;
}

function PaperLayerMesh({
  layer,
  frontTexture,
  thicknessGrayTexture,
  normalMapTexture,
  thickness,
}: PaperLayerMeshProps) {
  const z = DEPTH_LAYER_Z[layer];

  const frontMat = useMemo(() => {
    const m = new THREE.MeshStandardMaterial({
      map: frontTexture,
      transparent: true,
      side: THREE.FrontSide,
      roughness: 0.9,
      metalness: 0.0,
    });
    if (normalMapTexture) m.normalMap = normalMapTexture;
    return m;
  }, [frontTexture, normalMapTexture]);

  const sideMat = useMemo(() => {
    if (thicknessGrayTexture) {
      const m = new THREE.MeshStandardMaterial({
        map: thicknessGrayTexture,
        transparent: true,
        side: THREE.FrontSide,
        roughness: 0.8,
        metalness: 0.0,
      });
      if (normalMapTexture) m.normalMap = normalMapTexture;
      return m;
    }
    return new THREE.MeshStandardMaterial({
      color: new THREE.Color('#f5f0e8'),
      transparent: true,
      opacity: 0.95,
      side: THREE.FrontSide,
      roughness: 0.8,
      metalness: 0.0,
    });
  }, [thicknessGrayTexture, normalMapTexture]);

  useEffect(() => {
    return () => {
      frontMat.dispose();
      sideMat.dispose();
    };
  }, [frontMat, sideMat]);

  return (
    <mesh position={[0, 0, z]} castShadow receiveShadow>
      <boxGeometry args={[SCENE_WIDTH, SCENE_HEIGHT, thickness]} />
      {/* BoxGeometry ???????? Three.js ??????
            0 = +x ???
            1 = -x ???
            2 = +y ??
            3 = -y ??
            4 = +z ????????
            5 = -z ??
          frontMat ?? 4/5???????????????
          sideMat ?? 0~3???????????????? */}
      <primitive object={frontMat} attach="material-4" />
      <primitive object={frontMat} attach="material-5" />
      <primitive object={sideMat} attach="material-0" />
      <primitive object={sideMat} attach="material-1" />
      <primitive object={sideMat} attach="material-2" />
      <primitive object={sideMat} attach="material-3" />
    </mesh>
  );
}

// ??? Paper Diorama object mesh (BoxGeometry with paper thickness) ???????????????
// ? PaperLayerMesh ??????
// - LayerMesh????????? BoxGeometry?????
// - ObjectMesh????????????? BoxGeometry???????? 2D ???????
//    boundingBox.w/h???? 0-1???? SCENE_WIDTH/HEIGHT ????
// ???????????"??"?????????????
interface PaperObjectMeshProps {
  obj: DetectedObject;
  colorIndex: number;
  frontTexture: THREE.Texture;
  thickness: number;
  onSelect: (id: string) => void;
}

function PaperObjectMesh({
  obj,
  colorIndex,
  frontTexture,
  thickness,
  onSelect,
}: PaperObjectMeshProps) {
  const billboardOffsets = useAppStore((s) => s.billboardOffsets);
  const offset = billboardOffsets[obj.id];

  const posX = useMemo(() => {
    const cx = obj.boundingBox.x + obj.boundingBox.w / 2;
    return (cx - 0.5) * SCENE_WIDTH + (offset?.offsetX ?? 0);
  }, [obj.boundingBox, offset]);

  const posY = useMemo(() => {
    const cy = 1 - (obj.boundingBox.y + obj.boundingBox.h / 2);
    return (cy - 0.5) * SCENE_HEIGHT;
  }, [obj.boundingBox]);

  const posZ = useMemo(() => {
    // obj.depth ?? 0-50?AI ??????????????? [-5, 5] ????
    // ???depth/50*10 - 5 = ????? ? z ????
    // ?????? depth ??????????????????? z ??
    const clampedDepth = Math.max(0, Math.min(obj.depth, 50));
    return (clampedDepth / 50) * 10 - 5;
  }, [obj.depth]);

  const sizeX = obj.boundingBox.w * SCENE_WIDTH;
  const sizeY = obj.boundingBox.h * SCENE_HEIGHT;
  const color = LAYER_COLORS[colorIndex];

  const frontMat = useMemo(() => {
    if (frontTexture) {
      return new THREE.MeshStandardMaterial({
        map: frontTexture,
        transparent: true,
        side: THREE.FrontSide,
        roughness: 0.9,
        metalness: 0.0,
      });
    }
    return new THREE.MeshStandardMaterial({
      color: new THREE.Color(color),
      transparent: true,
      opacity: 0.7,
      side: THREE.FrontSide,
      roughness: 0.9,
      metalness: 0.0,
    });
  }, [frontTexture, color]);

  const sideMat = useMemo(() => new THREE.MeshStandardMaterial({
    color: new THREE.Color('#f0ebe0'),
    transparent: true,
    opacity: 0.95,
    side: THREE.FrontSide,
    roughness: 0.85,
    metalness: 0.0,
  }), []);

  useEffect(() => {
    return () => {
      frontMat.dispose();
      sideMat.dispose();
    };
  }, [frontMat, sideMat]);

  const handleClick = useCallback((e: THREE.Event) => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (e as any).stopPropagation?.();
    onSelect(obj.id);
  }, [obj.id, onSelect]);

  return (
    <mesh
      position={[posX, posY, posZ]}
      onClick={handleClick}
      castShadow
      receiveShadow
    >
      <boxGeometry args={[sizeX, sizeY, thickness]} />
      {/* BoxGeometry ?????4=+z ???5=-z ???0..3=???? */}
      <primitive object={frontMat} attach="material-4" />
      <primitive object={frontMat} attach="material-5" />
      <primitive object={sideMat} attach="material-0" />
      <primitive object={sideMat} attach="material-1" />
      <primitive object={sideMat} attach="material-2" />
      <primitive object={sideMat} attach="material-3" />
    </mesh>
  );
}

// ??? Outline edge effect ????????????????????????????????????????????????????????
// Renders white edges on depth layer boundaries for paper-cut look
interface OutlineEdgeProps {
  layer: DepthLayerKey;
  texture: THREE.Texture;
  outlineEnabled: boolean;
}

function OutlineEdge({ layer, texture, outlineEnabled }: OutlineEdgeProps) {
  if (!outlineEnabled) return null;

  const z = DEPTH_LAYER_Z[layer];
  // z + 0.01?????????????????????? z-fighting??????
  // ????????????????????????"?"???????
  const color = layer === 'foreground' ? '#ffffff' : '#e0ddd8';

  return (
    <mesh position={[0, 0, z + 0.01]}>
      <planeGeometry args={[SCENE_WIDTH, SCENE_HEIGHT]} />
      <meshBasicMaterial
        map={texture}
        transparent
        // alphaTest=0.05???? alpha ? > 0.05 ?????????????????????
        // ???????"??"????????????????
        alphaTest={0.05}
        depthWrite={false}
        color={new THREE.Color(color)}
        opacity={0.3}
      />
    </mesh>
  );
}

// ??? Background plane ???????????????????????????????????????????????????????????
function BackgroundPlane() {
  const analysisResult = useAppStore((s) => s.analysisResult);
  const depthUrl = analysisResult?.depthMapUrl;

  const texture = useMemo(() => {
    if (!depthUrl) return null;
    return getOrLoadTexture(depthUrl, 'depth-bg');
  }, [depthUrl]);

  if (!texture) return null;

  return (
    <mesh position={[0, 0, DEPTH_LAYER_Z.sky - 0.5]}>
      <planeGeometry args={[SCENE_WIDTH, SCENE_HEIGHT]} />
      <meshBasicMaterial map={texture} transparent opacity={0.25} side={THREE.DoubleSide} />
    </mesh>
  );
}

// ??? Scene content ??????????????????????????????????????????????????????????????
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

  const objects = analysisResult?.objects ?? [];

  const assignedObjects = useMemo(
    () => objects.filter((o) => assignments[o.id] !== undefined),
    [objects, assignments],
  );

  const isPaperMode = dioramaMode === 'paper';

  useEffect(() => {
    return () => {
      disposeCache();
    };
  }, []);

  return (
    <>
      <BackgroundPlane />
      {isPaperMode ? <PaperDioramaLighting /> : <ambientLight intensity={1} />}

      {/* ?? Paper Diorama Mode ?????????????????????????????????????????????? */}
      {/* ??????????
          1. outlinedUrl???????????+??+?????????????
          2. paperStyleUrl???????????????
          3. rgbaUrl???????????????
          4. billboardAsset.rgbaUrl?billboard ???????
          ?????????????????? outlinedUrl ?????????????"????"??? */}
      {isPaperMode && DEPTH_LAYER_ORDER.map((layer) => {
        const dioramaAsset = depthLayerDioramaAssets[layer];
        const billboardAsset = depthLayerBillboardAssets[layer];

        // Prefer outlinedUrl (paper style + cut edges) for front face
        const frontUrl = dioramaAsset?.outlinedUrl
          || dioramaAsset?.paperStyleUrl
          || dioramaAsset?.rgbaUrl
          || billboardAsset?.rgbaUrl;

        if (!frontUrl) return null;

        const tex = getOrLoadTexture(frontUrl, `paper-layer-${layer}`);
        const thicknessWorld = LAYER_THICKNESS[layer] * (dioramaParams.thicknessMax / 5.0);

        const normalTex = dioramaAsset?.normalMapUrl
          ? getOrLoadTexture(dioramaAsset.normalMapUrl, `normal-layer-${layer}`)
          : undefined;
        const thicknessGrayTex = dioramaAsset?.thicknessGrayUrl
          ? getOrLoadTexture(dioramaAsset.thicknessGrayUrl, `thickness-layer-${layer}`)
          : undefined;

        return (
          <PaperLayerMesh
            key={layer}
            layer={layer}
            frontTexture={tex}
            normalMapTexture={normalTex}
            thicknessGrayTexture={thicknessGrayTex}
            thickness={thicknessWorld}
          />
        );
      })}

      {/* Paper Diorama individual object meshes */}
      {/* Paper ????? assignedObject ????? BoxGeometry??????
          ? PaperLayerMesh ????"????"???BoxGeometry ??????? 3D ??? */}
      {isPaperMode && assignedObjects.map((obj) => {
        const colorIndex = assignments[obj.id];
        const dioramaAsset = objectDioramaAssets[obj.id];
        const billboardAsset = billboardAssets[obj.id];

        const textureUrl = dioramaAsset?.paperStyleUrl
          || dioramaAsset?.outlinedUrl
          || dioramaAsset?.rgbaUrl
          || billboardAsset?.rgbaUrl;

        if (!textureUrl) {
          const color = LAYER_COLORS[colorIndex];
          const tex = getOrLoadTexture(
            `data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==`,
            `fallback-${obj.id}`,
          );
          const thicknessWorld = LAYER_THICKNESS.foreground * (dioramaParams.thicknessMax / 5.0);
          return (
            <PaperObjectMesh
              key={obj.id}
              obj={obj}
              colorIndex={colorIndex}
              frontTexture={tex}
              thickness={thicknessWorld}
              onSelect={onSelectObject}
            />
          );
        }

        const tex = getOrLoadTexture(textureUrl, `paper-obj-${obj.id}`);
        const thicknessWorld = LAYER_THICKNESS.foreground * (dioramaParams.thicknessMax / 5.0);

        return (
          <PaperObjectMesh
            key={obj.id}
            obj={obj}
            colorIndex={colorIndex}
            frontTexture={tex}
            thickness={thicknessWorld}
            onSelect={onSelectObject}
          />
        );
      })}

      {/* ?? Billboard Mode ?????????????????????????????????????????????????? */}
      {/* ? Paper ????????
          - ?????? PlaneGeometry?????? BoxGeometry?? 3D ??
          - ???MeshBasicMaterial??????? opacity ?????
          - ???????????????????? */}
      {!isPaperMode && DEPTH_LAYER_ORDER.map((layer) => {
        const asset = depthLayerBillboardAssets[layer];
        if (!asset?.rgbaUrl) return null;

        const tex = getOrLoadTexture(asset.rgbaUrl, `depth-layer-${layer}`);

        return (
          <mesh key={layer} position={[0, 0, DEPTH_LAYER_Z[layer]]}>
            <planeGeometry args={[SCENE_WIDTH, SCENE_HEIGHT]} />
            <meshBasicMaterial
              map={tex}
              transparent
              side={THREE.DoubleSide}
              opacity={0.92}
              depthWrite={false}
            />
          </mesh>
        );
      })}

      {/* Billboard individual objects */}
      {/* Billboard ????????? PlaneGeometry?????? BoxGeometry?
          z ?????obj.depth ?? 0-50??????????? [-5, 5] ?????
          ??????"???"????????????? z ?????? */}
      {!isPaperMode && assignedObjects.map((obj) => {
        const colorIndex = assignments[obj.id];
        const asset = billboardAssets[obj.id];

        let tex: THREE.Texture | undefined;
        if (asset?.rgbaUrl) {
          tex = getOrLoadTexture(asset.rgbaUrl, `billboard-${obj.id}`);
        }

        return (
          <BillboardMesh
            key={obj.id}
            obj={obj}
            colorIndex={colorIndex}
            texture={tex}
            onSelect={onSelectObject}
          />
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

      {/* Grid */}
      <gridHelper
        args={[SCENE_WIDTH, 20, '#333333', '#222222']}
        position={[0, -SCENE_HEIGHT / 2, 0]}
      />
    </>
  );
}

// ??? Expose WebGL canvas DOM element via ref ?????????????????????????????????????
interface GlDomElementProps {
  onDomReady: (el: HTMLCanvasElement) => void;
}

function GlDomElement({ onDomReady }: GlDomElementProps) {
  const { gl } = useThree();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { onDomReady(gl.domElement); }, []);
  return null;
}

// ??? Camera controller ?????????????????????????????????????????????????????????
function CameraController() {
  return (
    <OrbitControls
      makeDefault
      enableDamping
      dampingFactor={0.05}
      minDistance={3}
      maxDistance={60}
    />
  );
}

// ??? Main export ????????????????????????????????????????????????????????????????
export function Viewer3D() {
  const analysisResult = useAppStore((s) => s.analysisResult);
  const selectedObjectId = useAppStore((s) => s.selectedObjectId);
  const setSelectedObjectId = useAppStore((s) => s.setSelectedObjectId);
  const editMode = useAppStore((s) => s.editMode);
  const dioramaMode = useAppStore((s) => s.dioramaMode);

  // Hold the WebGL canvas DOM element (obtained via useThree inside the Canvas)
  const [glCanvas, setGlCanvas] = useState<HTMLCanvasElement | null>(null);

  const handleSelect = useCallback(
    (id: string) => {
      // ??????????????????id === null????????????????
      setSelectedObjectId(selectedObjectId === id ? null : id);
    },
    [selectedObjectId, setSelectedObjectId],
  );

  const hasAssignments = analysisResult?.objects
    ? Object.keys(useAppStore.getState().assignments).length > 0
    : false;

  return (
    <div className="relative w-full h-full bg-gray-950">
      <Canvas
        // antialias=true????????
        // alpha=false??? WebGL ???????????? CSS (#0a0a0f) ???????????
        gl={{ antialias: true, alpha: false }}
        shadows
        style={{ background: '#0a0a0f' }}
      >
        <color attach="background" args={['#0a0a0f']} />
        <GlDomElement onDomReady={setGlCanvas} />
        <SceneContent onSelectObject={handleSelect} />
        <CameraController />
      </Canvas>

      {/* Mode badge */}
      <div className="absolute top-3 right-3 flex items-center gap-2">
        <span
          className={`
            px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wider
            ${dioramaMode === 'paper' ? 'bg-amber-600 text-white' : 'bg-blue-600 text-white'}
          `}
        >
          {dioramaMode === 'paper' ? '????' : '????'}
        </span>
        <span
          className={`
            px-2 py-1 rounded-full text-xs font-semibold uppercase tracking-wider
            ${editMode === 'director' ? 'bg-purple-600 text-white' : 'bg-blue-600 text-white'}
          `}
        >
          {editMode === 'director' ? 'Director' : 'Camera'}
        </span>
      </div>

      {/* Selected object info */}
      {selectedObjectId && analysisResult && (
        <div className="absolute bottom-3 left-3 bg-black/70 text-white text-xs px-3 py-2 rounded-lg">
          Selected: {selectedObjectId}
        </div>
      )}

      {/* Empty state */}
      {!hasAssignments && analysisResult && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <p className="text-gray-600 text-sm">
            Assign objects to layers to see them here
          </p>
        </div>
      )}

      {/* Export Panel */}
      <ExportPanel canvasRef={{ current: glCanvas }} />
    </div>
  );
}
