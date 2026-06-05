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
  const materialRef = useRef<THREE.Material | null>(null);
  const billboardOffsets = useAppStore((s) => s.billboardOffsets);
  const editMode = useAppStore((s) => s.editMode);

  const color = LAYER_COLORS[colorIndex % LAYER_COLORS.length];
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
    const clampedDepth = Math.max(0, Math.min(obj.depth, 50));
    return (clampedDepth / 50) * 10 - 5;
  }, [obj.depth]);

  const sizeX = obj.boundingBox.w * SCENE_WIDTH;
  const sizeY = obj.boundingBox.h * SCENE_HEIGHT;

  // Build material; dispose previous one on texture or color change
  const material = useMemo(() => {
    if (materialRef.current) {
      materialRef.current.dispose();
    }
    const mat = texture
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
    materialRef.current = mat;
    return mat;
  }, [texture, color]);

  // Dispose material on unmount
  useEffect(() => {
    return () => {
      material.dispose();
      materialRef.current = null;
    };
  }, []);

  const handleClick = useCallback(
    (e: THREE.Event) => {
      (e as unknown as { stopPropagation: () => void }).stopPropagation?.();
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
  const depthModeResult = useAppStore((s) => s.depthModeResult);
  const imageMode = useAppStore((s) => s.imageMode);

  const depthUrl = imageMode === 'depth' && depthModeResult
    ? depthModeResult.depthMapUrl
    : analysisResult?.depthMapUrl;

  const texture = useMemo(() => {
    if (!depthUrl) return null;
    const loader = new THREE.TextureLoader();
    const tex = loader.load(depthUrl);
    tex.colorSpace = THREE.SRGBColorSpace;
    return tex;
  }, [depthUrl]);

  // Dispose texture on unmount
  useEffect(() => {
    return () => {
      texture?.dispose();
    };
  }, [texture]);

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
  const depthModeResult = useAppStore((s) => s.depthModeResult);
  const imageMode = useAppStore((s) => s.imageMode);
  const assignments = useAppStore((s) => s.assignments);
  const billboardAssets = useAppStore((s) => s.billboardAssets);

  const objects = imageMode === 'depth' && depthModeResult
    ? depthModeResult.objects
    : (analysisResult?.objects ?? []);

  const assignedObjects = useMemo(
    () => objects.filter((o) => assignments[o.id] !== undefined),
    [objects, assignments],
  );

  // Cache textures keyed by objectId+rgbaUrl so URL changes are detected
  const textureCache = useRef<Record<string, THREE.Texture>>({});

  // Cleanup all cached textures on unmount
  useEffect(() => {
    return () => {
      for (const tex of Object.values(textureCache.current)) {
        tex.dispose();
      }
      textureCache.current = {};
    };
  }, []);

  return (
    <>
      <BackgroundPlane />

      <ambientLight intensity={1} />

      {assignedObjects.map((obj) => {
        const colorIndex = assignments[obj.id];
        const asset = billboardAssets[obj.id];

        let texture: THREE.Texture | undefined;
        if (asset?.rgbaUrl) {
          // Invalidate cache if URL changed (e.g. after re-analysis)
          const cacheKey = `${asset.objectId}:${asset.rgbaUrl}`;
          if (!textureCache.current[cacheKey]) {
            textureCache.current[cacheKey]?.dispose();
            const loader = new THREE.TextureLoader();
            textureCache.current[cacheKey] = loader.load(asset.rgbaUrl);
            textureCache.current[cacheKey].colorSpace = THREE.SRGBColorSpace;
          }
          texture = textureCache.current[cacheKey];
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

      <gridHelper args={[SCENE_WIDTH, 20, '#333333', '#222222']} position={[0, -SCENE_HEIGHT / 2, 0]} />
    </>
  );
}

// ─── Camera controller ────────────────────────────────────────────────────────
function CameraController() {
  const editMode = useAppStore((s) => s.editMode);

  return (
    <OrbitControls
      makeDefault
      enableDamping
      dampingFactor={0.05}
      minDistance={5}
      maxDistance={50}
    />
  );
}

// ─── Main export ─────────────────────────────────────────────────────────────
export function Viewer3D() {
  const analysisResult = useAppStore((s) => s.analysisResult);
  const depthModeResult = useAppStore((s) => s.depthModeResult);
  const selectedObjectId = useAppStore((s) => s.selectedObjectId);
  const setSelectedObjectId = useAppStore((s) => s.setSelectedObjectId);
  const editMode = useAppStore((s) => s.editMode);

  const handleSelect = useCallback(
    (id: string) => {
      setSelectedObjectId(selectedObjectId === id ? null : id);
    },
    [selectedObjectId, setSelectedObjectId],
  );

  const hasAssignments = Object.keys(useAppStore.getState().assignments).length > 0;
  const hasResult = !!(analysisResult || depthModeResult);

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

      {selectedObjectId && hasResult && (
        <div className="absolute bottom-3 left-3 bg-black/70 text-white text-xs px-3 py-2 rounded-lg">
          Selected: {selectedObjectId}
        </div>
      )}

      {!hasAssignments && hasResult && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <p className="text-gray-600 text-sm">
            Assign objects to layers to see them here
          </p>
        </div>
      )}
    </div>
  );
}
