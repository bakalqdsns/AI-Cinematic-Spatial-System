// ─────────────────────────────────────────────────────────────────────────────
// Viewer3D — Three.js billboard 3D space with director/camera modes
// ─────────────────────────────────────────────────────────────────────────────
import { useRef, useMemo, useCallback, useEffect } from 'react';
import { Canvas, useThree } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';
import { useAppStore } from '../store/useAppStore';
import { LAYER_COLORS } from '../types';
import type { DetectedObject } from '../types';

// Scene dimensions (world units)
const SCENE_WIDTH = 20;
const SCENE_HEIGHT = 15;

// ─── Billboard mesh ───────────────────────────────────────────────────────────
interface BillboardMeshProps {
  obj: DetectedObject;
  colorIndex: number;
  texture?: THREE.Texture;
  onSelect: (id: string) => void;
}

function BillboardMesh({ obj, colorIndex, texture, onSelect }: BillboardMeshProps) {
  const meshRef = useRef<THREE.Mesh>(null);
  const billboardOffsets = useAppStore((s) => s.billboardOffsets);
  const editMode = useAppStore((s) => s.editMode);

  const color = LAYER_COLORS[colorIndex];
  const offset = billboardOffsets[obj.id];

  // World position derived from bounding box + depth
  const posX = useMemo(() => {
    const cx = obj.boundingBox.x + obj.boundingBox.w / 2; // 0-1 center
    return (cx - 0.5) * SCENE_WIDTH + (offset?.offsetX ?? 0);
  }, [obj.boundingBox, offset]);

  const posY = useMemo(() => {
    const cy = 1 - (obj.boundingBox.y + obj.boundingBox.h / 2); // flip Y for 3D
    return (cy - 0.5) * SCENE_HEIGHT;
  }, [obj.boundingBox]);

  const posZ = useMemo(() => {
    // depth: 0 = close (near camera), higher = far
    // Map depth to -5 (front) to +5 (back)
    const clampedDepth = Math.max(0, Math.min(obj.depth, 50));
    return (clampedDepth / 50) * 10 - 5;
  }, [obj.depth]);

  // Billboard size in world units
  const sizeX = obj.boundingBox.w * SCENE_WIDTH;
  const sizeY = obj.boundingBox.h * SCENE_HEIGHT;

  // Material
  const material = useMemo(() => {
    const nextMaterial = texture
      ? new THREE.MeshBasicMaterial({
          map: texture,
          transparent: true,
          side: THREE.DoubleSide,
          opacity: 1,
        })
      : new THREE.MeshBasicMaterial({
          color: new THREE.Color(color),
          transparent: true,
          opacity: 0.5,
          side: THREE.DoubleSide,
        });

    return nextMaterial;
  }, [texture, color]);

  useEffect(() => {
    return () => {
      material.dispose();
    };
  }, [material]);

  const handleClick = useCallback(
    (e: THREE.Event) => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (e as any).stopPropagation?.();
      onSelect(obj.id);
    },
    [obj.id, onSelect],
  );

  return (
    <mesh
      ref={meshRef}
      position={[posX, posY, posZ]}
      onClick={handleClick}
    >
      <planeGeometry args={[sizeX, sizeY]} />
      <primitive object={material} attach="material" />
    </mesh>
  );
}

// ─── Background plane ─────────────────────────────────────────────────────────
function BackgroundPlane() {
  const analysisResult = useAppStore((s) => s.analysisResult);
  const depthUrl = analysisResult?.depthMapUrl;

  const texture = useMemo(() => {
    if (!depthUrl) return null;
    const loader = new THREE.TextureLoader();
    const tex = loader.load(depthUrl);
    tex.colorSpace = THREE.SRGBColorSpace;
    return tex;
  }, [depthUrl]);

  if (!texture) return null;

  return (
    <mesh position={[0, 0, -6]}>
      <planeGeometry args={[SCENE_WIDTH, SCENE_HEIGHT]} />
      <meshBasicMaterial map={texture} transparent opacity={0.3} side={THREE.DoubleSide} />
    </mesh>
  );
}

// ─── Scene content ────────────────────────────────────────────────────────────
interface SceneContentProps {
  onSelectObject: (id: string) => void;
}

function SceneContent({ onSelectObject }: SceneContentProps) {
  const analysisResult = useAppStore((s) => s.analysisResult);
  const assignments = useAppStore((s) => s.assignments);
  const billboardAssets = useAppStore((s) => s.billboardAssets);

  const objects = analysisResult?.objects ?? [];

  // Only show assigned objects
  const assignedObjects = useMemo(
    () => objects.filter((o) => assignments[o.id] !== undefined),
    [objects, assignments],
  );

  const textureCache = useRef<Record<string, THREE.Texture>>({});

  useEffect(() => {
    return () => {
      Object.values(textureCache.current).forEach((texture) => texture.dispose());
      textureCache.current = {};
    };
  }, []);

  return (
    <>
      <BackgroundPlane />

      {/* Directional light so billboards are visible */}
      <ambientLight intensity={1} />

      {/* Billboards */}
      {assignedObjects.map((obj) => {
        const colorIndex = assignments[obj.id];
        const asset = billboardAssets[obj.id];

        let texture: THREE.Texture | undefined;
        if (asset?.rgbaUrl) {
          if (!textureCache.current[asset.objectId]) {
            const loader = new THREE.TextureLoader();
            textureCache.current[asset.objectId] = loader.load(asset.rgbaUrl);
            textureCache.current[asset.objectId].colorSpace = THREE.SRGBColorSpace;
          }
          texture = textureCache.current[asset.objectId];
        }

        return (
          <BillboardMesh
            key={obj.id}
            obj={obj}
            colorIndex={colorIndex}
            texture={texture}
            onSelect={onSelectObject}
          />
        );
      })}

      {/* Grid helper for spatial reference */}
      <gridHelper args={[SCENE_WIDTH, 20, '#333333', '#222222']} position={[0, -SCENE_HEIGHT / 2, 0]} />
    </>
  );
}

// ─── Camera controller ────────────────────────────────────────────────────────
function CameraController() {
  return (
    <OrbitControls
      makeDefault
      enableDamping
      dampingFactor={0.05}
      minDistance={5}
      maxDistance={50}
      // In director mode, camera itself can be manipulated fully
      // In camera mode, still can rotate/zoom but focus stays on scene
    />
  );
}

// ─── Main export ─────────────────────────────────────────────────────────────
export function Viewer3D() {
  const analysisResult = useAppStore((s) => s.analysisResult);
  const selectedObjectId = useAppStore((s) => s.selectedObjectId);
  const setSelectedObjectId = useAppStore((s) => s.setSelectedObjectId);
  const editMode = useAppStore((s) => s.editMode);

  const handleSelect = useCallback(
    (id: string) => {
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
        camera={{ position: [0, 0, 15], fov: 50 }}
        gl={{ antialias: true, alpha: false }}
        style={{ background: '#0a0a0f' }}
      >
        <color attach="background" args={['#0a0a0f']} />
        <SceneContent onSelectObject={handleSelect} />
        <CameraController />
      </Canvas>

      {/* Mode badge */}
      <div className="absolute top-3 right-3 flex items-center gap-2">
        <span
          className={`
            px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wider
            ${editMode === 'director'
              ? 'bg-purple-600 text-white'
              : 'bg-blue-600 text-white'}
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
    </div>
  );
}
