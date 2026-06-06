// ─────────────────────────────────────────────────────────────────────────────
// Viewer3D — Three.js Paper Diorama 3D Scene
// Supports: Billboard mode | Paper Diorama mode
// Paper Diorama: BoxGeometry (3D paper thickness), normal maps, outline edges, parallax animation
// ─────────────────────────────────────────────────────────────────────────────
import { useRef, useMemo, useCallback, useEffect, useState } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';
import { useAppStore } from '../store/useAppStore';
import { LAYER_COLORS } from '../types';
import type { DepthLayerKey, DetectedObject } from '../types';
import { ExportPanel } from './ExportPanel';

// Scene dimensions (world units)
// 20:15 = 4:3 比例，与大多数相机的默认画幅比例接近，
// 配合相机 FOV=50° 和 position z=15，形成自然透视感
const SCENE_WIDTH = 20;
const SCENE_HEIGHT = 15;

// Z轴位置：天空=-20（最远），背景=-12，中景=-6，前景=-2
// 数值设计考虑：相机位于 z=15，向-z方向观察。-20 ~ -2 的范围约18个世界单位，
// 与场景宽度20、高度15相近，形成透视比例协调的立体纸雕层次感
const DEPTH_LAYER_Z: Record<DepthLayerKey, number> = {
  sky: -20,
  background: -12,
  midground: -6,
  foreground: -2,
};

// 纸张厚度（世界单位），最终厚度 = 此值 × dioramaParams.thicknessMax
// 采用小数的理由：场景总尺寸约20x15个世界单位，厚度0.08~0.30（约指甲盖厚度）
// 更符合"薄纸"的视觉隐喻；厚度过大会破坏纸雕感，显得像积木
const LAYER_THICKNESS: Record<DepthLayerKey, number> = {
  sky: 0.08,
  background: 0.12,
  midground: 0.20,
  foreground: 0.30,
};

const DEPTH_LAYER_ORDER: DepthLayerKey[] = ['foreground', 'midground', 'background', 'sky'];

// ─── Texture cache ─────────────────────────────────────────────────────────────
// 使用 Map 而非 React state 的原因：
// React state 更新会触发 SceneContent 重新渲染，而 SceneContent 内部有大量 useMemo/useCallback 依赖链。
// textureCache 作为模块级变量，跨渲染周期持久化，同一 URL 的纹理只需加载一次。
// 配合 useEffect cleanup 在组件卸载时 dispose() 释放显存。
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

// ─── Parallax Camera Controller ─────────────────────────────────────────────────
interface ParallaxCameraProps {
  enabled: boolean;
  intensity: number;
}

function ParallaxCamera({ enabled, intensity }: ParallaxCameraProps) {
  const { camera, pointer } = useThree();
  const basePosition = useMemo(() => camera.position.clone(), []);
  const targetOffset = useRef(new THREE.Vector3());

  useFrame(() => {
    if (!enabled) {
      // 缓慢插值回原点：0.05 的 lerp 因子使相机在失能后约 60帧（~1秒）平滑归位
      camera.position.lerp(basePosition, 0.05);
      return;
    }

    // pointer.x 范围 [-0.5, 0.5]，乘以 intensity * 2 得到水平位移量
    // pointer.y 范围 [-0.5, 0.5]，乘以 intensity * 1.5 得到垂直位移量
    // 1.5/2 = 0.75 的系数补偿了视锥体宽高比（场景 4:3）对视角偏移的影响，
    // 使水平和垂直视差效果在视觉上均衡
    const parallaxX = pointer.x * intensity * 2;
    const parallaxY = pointer.y * intensity * 1.5;

    camera.position.x = basePosition.x + parallaxX;
    camera.position.y = basePosition.y + parallaxY;
  });

  return null;
}

// ─── Directional light for paper diorama shading ───────────────────────────────
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

// ─── Billboard mesh (flat plane) ───────────────────────────────────────────────
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

  // obj.depth 范围 0-50（AI 模型输出的归一化深度），映射到 [-5, 5] 世界单位
  // 公式：depth/50*10 - 5 = 归一化深度 → z 轴偏移量
  // 注意：此处的 depth 是检测算法给出的语义深度值，不是实际的 z 坐标
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
    // 阻止事件冒泡到 OrbitControls，避免点击物体时触发相机旋转
    onSelect(obj.id);
  }, [obj.id, onSelect]);

  return (
    <mesh ref={meshRef} position={[posX, posY, posZ]} onClick={handleClick}>
      <planeGeometry args={[sizeX, sizeY]} />
      <primitive object={material} attach="material" />
    </mesh>
  );
}

// ─── Paper Diorama layer mesh (BoxGeometry with thickness) ─────────────────────
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
      {/* BoxGeometry 默认材质分组索引：0=背面(-z)，1=正面(+z)，2=左，3=右，4=顶，5=底
          material-0 和 material-1 均使用 frontMat，使纸层前后两面都显示正面纹理，
          模拟薄纸两面纹理相同的视觉效果。material-2~5 使用 sideMat（厚度灰度图或米色）
          显示纸层侧边（切割边缘）的颜色。 */}
      <primitive object={frontMat} attach="material-1" />
      <primitive object={frontMat} attach="material-0" />
      <primitive object={sideMat} attach="material-2" />
      <primitive object={sideMat} attach="material-3" />
      <primitive object={sideMat} attach="material-4" />
      <primitive object={sideMat} attach="material-5" />
    </mesh>
  );
}

// ─── Paper Diorama object mesh (BoxGeometry with paper thickness) ───────────────
// 与 PaperLayerMesh 的关键区别：
// - LayerMesh：全场景宽高的平面 BoxGeometry，每层一个
// - ObjectMesh：每个检测到的物体一个独立 BoxGeometry，尺寸由该物体的 2D 边界框计算得出
//    boundingBox.w/h（归一化 0-1）映射到 SCENE_WIDTH/HEIGHT 世界单位
// 这样每个物体都是独立的"纸片"，拥有自己的厚度和侧边颜色
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
    // obj.depth 范围 0-50（AI 模型输出的归一化深度），映射到 [-5, 5] 世界单位
    // 公式：depth/50*10 - 5 = 归一化深度 → z 轴偏移量
    // 注意：此处的 depth 是检测算法给出的语义深度值，不是实际的 z 坐标
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
      <primitive object={frontMat} attach="material-1" />
      <primitive object={frontMat} attach="material-0" />
      <primitive object={sideMat} attach="material-2" />
      <primitive object={sideMat} attach="material-3" />
      <primitive object={sideMat} attach="material-4" />
      <primitive object={sideMat} attach="material-5" />
    </mesh>
  );
}

// ─── Outline edge effect ────────────────────────────────────────────────────────
// Renders white edges on depth layer boundaries for paper-cut look
interface OutlineEdgeProps {
  layer: DepthLayerKey;
  texture: THREE.Texture;
  outlineEnabled: boolean;
}

function OutlineEdge({ layer, texture, outlineEnabled }: OutlineEdgeProps) {
  if (!outlineEnabled) return null;

  const z = DEPTH_LAYER_Z[layer];
  // z + 0.01：将描边平面放置在该层正前方极小距离处，避免 z-fighting（深度冲突）
  // 这个偏移量足够小，肉眼不会察觉，但能确保描边始终"贴"在该层前面显示
  const color = layer === 'foreground' ? '#ffffff' : '#e0ddd8';

  return (
    <mesh position={[0, 0, z + 0.01]}>
      <planeGeometry args={[SCENE_WIDTH, SCENE_HEIGHT]} />
      <meshBasicMaterial
        map={texture}
        transparent
        // alphaTest=0.05：只显示 alpha 值 > 0.05 的像素，过滤掉描边纹理中近乎透明的边缘像素
        // 这样只有实际的"线条"部分可见，产生干净的剪纸描边效果
        alphaTest={0.05}
        depthWrite={false}
        color={new THREE.Color(color)}
        opacity={0.3}
      />
    </mesh>
  );
}

// ─── Background plane ───────────────────────────────────────────────────────────
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

// ─── Scene content ──────────────────────────────────────────────────────────────
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
  const parallaxEnabled = useAppStore((s) => s.parallaxEnabled);
  const parallaxIntensity = useAppStore((s) => s.parallaxIntensity);
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
      <ParallaxCamera enabled={isPaperMode && parallaxEnabled} intensity={parallaxIntensity} />

      {/* ── Paper Diorama Mode ────────────────────────────────────────────── */}
      {/* 纹理优先级设计原则：
          1. outlinedUrl：最完整——包含卡通化+描边+切口阴影，完全符合纸雕风格
          2. paperStyleUrl：卡通化但无描边，作为降级选项
          3. rgbaUrl：原图透明背景，作为进一步降级
          4. billboardAsset.rgbaUrl：billboard 模式的资产兜底
          越靠前的选项视觉效果越完整；优先使用 outlinedUrl 是因为它提供了纸雕最核心的"剪纸边缘"效果。 */}
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
      {/* Paper 模式：每个 assignedObject 渲染为独立 BoxGeometry（带厚度），
          与 PaperLayerMesh 共同构成"层叠纸片"效果。BoxGeometry 让物体有真实的 3D 厚度。 */}
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

      {/* ── Billboard Mode ────────────────────────────────────────────────── */}
      {/* 与 Paper 模式的核心差异：
          - 几何体：使用 PlaneGeometry（扁平）而非 BoxGeometry，无 3D 厚度
          - 材质：MeshBasicMaterial（无光照）配合 opacity 透明度叠加
          - 适用场景：不需要纸雕厚度感的轻量展示模式 */}
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
      {/* Billboard 模式下每个物体使用 PlaneGeometry（扁平）而非 BoxGeometry。
          z 位置计算：obj.depth 范围 0-50（归一化深度），映射到 [-5, 5] 世界单位。
          这将检测到的"深度值"（语义深度）转换为可感知的 z 轴位置偏移。 */}
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

// ─── Expose WebGL canvas DOM element via ref ─────────────────────────────────────
interface GlDomElementProps {
  onDomReady: (el: HTMLCanvasElement) => void;
}

function GlDomElement({ onDomReady }: GlDomElementProps) {
  const { gl } = useThree();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { onDomReady(gl.domElement); }, []);
  return null;
}

// ─── Camera controller ─────────────────────────────────────────────────────────
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

// ─── Main export ────────────────────────────────────────────────────────────────
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
      // 切换选择：点击已选中物体则取消选中（id === null），避免误操作后物体一直保持高亮
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
        // antialias=true：平滑几何体边缘
        // alpha=false：禁用 WebGL 透明背景，使背景色完全由 CSS (#0a0a0f) 控制，避免透明混合开销
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
          {dioramaMode === 'paper' ? '纸雕模式' : '层片模式'}
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

      {/* Paper mode parallax hint */}
      {dioramaMode === 'paper' && (
        <div className="absolute top-3 left-3 text-[10px] text-amber-500/60 bg-black/40 rounded px-2 py-1">
          移动鼠标触发视差动画
        </div>
      )}

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
