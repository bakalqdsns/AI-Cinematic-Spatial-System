// ─────────────────────────────────────────────────────────────────────────────
// Viewer3D — Babylon.js Paper Diorama 3D Scene
// Migrated from Three.js / React Three Fiber
// Supports: Billboard mode (flat planes) | Paper Diorama mode (BoxGeometry with thickness)
// ─────────────────────────────────────────────────────────────────────────────
import { useRef, useEffect, useCallback, useState } from 'react';
import * as BABYLON from '@babylonjs/core';
import { useAppStore } from '../store/useAppStore';
import { LAYER_COLORS } from '../types';
import type { DepthLayerKey, DetectedObject } from '../types';
import { ExportPanel } from './ExportPanel';

// Scene dimensions (world units)
const SCENE_WIDTH = 20;
const SCENE_HEIGHT = 15;

const DEPTH_LAYER_Z: Record<DepthLayerKey, number> = {
  sky: -20,
  background: -12,
  midground: -6,
  foreground: -2,
};

const LAYER_THICKNESS: Record<DepthLayerKey, number> = {
  sky: 0.08,
  background: 0.12,
  midground: 0.20,
  foreground: 0.30,
};

const DEPTH_LAYER_ORDER: DepthLayerKey[] = ['foreground', 'midground', 'background', 'sky'];

const DEFAULT_CAMERA_POS = new BABYLON.Vector3(0, 0, 15);

// ─── Shared color constants ────────────────────────────────────────────────────
const PAPER_SIDE_COLOR = BABYLON.Color3.FromHexString('#f5f0e8');
const PAPER_OBJ_SIDE_COLOR = BABYLON.Color3.FromHexString('#f0ebe0');

// ─── Helper: build a Babylon StandardMaterial ──────────────────────────────────
function makeMat(scene: BABYLON.Scene, name: string): BABYLON.StandardMaterial {
  const mat = new BABYLON.StandardMaterial(name, scene);
  mat.specularColor = BABYLON.Color3.Black();
  return mat;
}

function makePaperFrontMat(
  scene: BABYLON.Scene,
  texUrl: string,
  normalUrl?: string,
  name = 'paperFront',
): BABYLON.StandardMaterial {
  const mat = makeMat(scene, name);
  const tex = new BABYLON.Texture(texUrl, scene, true, true);
  tex.gammaSpace = false;
  tex.wrapU = BABYLON.Texture.CLAMP_ADDRESSMODE;
  tex.wrapV = BABYLON.Texture.CLAMP_ADDRESSMODE;
  mat.diffuseTexture = tex;
  mat.backFaceCulling = true;
  if (normalUrl) {
    mat.bumpTexture = new BABYLON.Texture(normalUrl, scene, true, true);
  }
  return mat;
}

function makePaperSideMat(
  scene: BABYLON.Scene,
  texUrl?: string,
  name = 'paperSide',
): BABYLON.StandardMaterial {
  const mat = makeMat(scene, name);
  if (texUrl) {
    const tex = new BABYLON.Texture(texUrl, scene, true, true);
    tex.gammaSpace = false;
    tex.wrapU = BABYLON.Texture.CLAMP_ADDRESSMODE;
    tex.wrapV = BABYLON.Texture.CLAMP_ADDRESSMODE;
    mat.diffuseTexture = tex;
  } else {
    mat.diffuseColor = PAPER_SIDE_COLOR;
  }
  mat.backFaceCulling = true;
  return mat;
}

function makeColorMat(
  scene: BABYLON.Scene,
  hexColor: string,
  alpha = 0.5,
): BABYLON.StandardMaterial {
  const mat = makeMat(scene, `colorMat_${hexColor}`);
  mat.diffuseColor = BABYLON.Color3.FromHexString(hexColor);
  mat.alpha = alpha;
  mat.backFaceCulling = false;
  return mat;
}

function makeBillboardMat(
  scene: BABYLON.Scene,
  texUrl?: string,
  color?: string,
  alpha = 1.0,
): BABYLON.StandardMaterial {
  const mat = makeMat(
    scene,
    `billboard_${texUrl?.slice(0, 20) ?? color ?? 'fallback'}`,
  );
  if (texUrl) {
    const tex = new BABYLON.Texture(texUrl, scene, true, true);
    tex.gammaSpace = false;
    tex.wrapU = BABYLON.Texture.CLAMP_ADDRESSMODE;
    tex.wrapV = BABYLON.Texture.CLAMP_ADDRESSMODE;
    mat.diffuseTexture = tex;
    mat.emissiveTexture = tex;
    mat.useAlphaFromDiffuseTexture = true;
  } else if (color) {
    mat.diffuseColor = BABYLON.Color3.FromHexString(color);
    mat.emissiveColor = BABYLON.Color3.FromHexString(color);
  }
  mat.alpha = alpha;
  mat.backFaceCulling = false;
  return mat;
}

function makeOutlineMat(
  scene: BABYLON.Scene,
  texUrl: string,
  hexColor: string,
  alpha = 0.3,
): BABYLON.StandardMaterial {
  const mat = makeMat(scene, `outline_${hexColor}`);
  const tex = new BABYLON.Texture(texUrl, scene, true, true);
  tex.gammaSpace = false;
  tex.wrapU = BABYLON.Texture.CLAMP_ADDRESSMODE;
  tex.wrapV = BABYLON.Texture.CLAMP_ADDRESSMODE;
  mat.diffuseTexture = tex;
  mat.useAlphaFromDiffuseTexture = true;
  mat.alpha = alpha;
  mat.diffuseColor = BABYLON.Color3.FromHexString(hexColor);
  mat.backFaceCulling = false;
  return mat;
}

// ─── Helper: compute 3D position from object bounding box ───────────────────────
function objectPosition(obj: DetectedObject, offsetX = 0): BABYLON.Vector3 {
  const cx = obj.boundingBox.x + obj.boundingBox.w / 2;
  const cy = 1 - (obj.boundingBox.y + obj.boundingBox.h / 2);
  const clampedDepth = Math.max(0, Math.min(obj.depth, 50));
  const posZ = (clampedDepth / 50) * 10 - 5;
  return new BABYLON.Vector3(
    (cx - 0.5) * SCENE_WIDTH + offsetX,
    (cy - 0.5) * SCENE_HEIGHT,
    posZ,
  );
}

// ─── Scene ref type ────────────────────────────────────────────────────────────
interface SceneObjects {
  engine: BABYLON.Engine;
  scene: BABYLON.Scene;
  camera: BABYLON.ArcRotateCamera;
  hemiLight: BABYLON.HemisphericLight;
  dirLight: BABYLON.DirectionalLight;
  fillLight: BABYLON.DirectionalLight;
  shadowGenerator: BABYLON.ShadowGenerator;
  paperLayerMeshes: BABYLON.Mesh[];
  paperObjectMeshes: BABYLON.Mesh[];
  billboardMeshes: BABYLON.Mesh[];
  outlineMeshes: BABYLON.Mesh[];
  bgPlane: BABYLON.Mesh | null;
  gridMesh: BABYLON.Mesh;
  baseCameraPos: BABYLON.Vector3;
  parallaxEnabled: boolean;
  parallaxIntensity: number;
  outlineEnabled: boolean;
  dioramaMode: 'billboard' | 'paper';
  // Live pointer for parallax
  pointerNDC: { x: number; y: number };
}

// ─── Main component ────────────────────────────────────────────────────────────
export function Viewer3D() {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const sceneRef = useRef<SceneObjects | null>(null);
  const [glCanvas, setGlCanvas] = useState<HTMLCanvasElement | null>(null);

  const analysisResult = useAppStore((s) => s.analysisResult);
  const selectedObjectId = useAppStore((s) => s.selectedObjectId);
  const setSelectedObjectId = useAppStore((s) => s.setSelectedObjectId);
  const editMode = useAppStore((s) => s.editMode);
  const dioramaMode = useAppStore((s) => s.dioramaMode);
  const assignments = useAppStore((s) => s.assignments);
  const billboardAssets = useAppStore((s) => s.billboardAssets);
  const depthLayerBillboardAssets = useAppStore((s) => s.depthLayerBillboardAssets);
  const depthLayerDioramaAssets = useAppStore((s) => s.depthLayerDioramaAssets);
  const objectDioramaAssets = useAppStore((s) => s.objectDioramaAssets);
  const outlineEnabled = useAppStore((s) => s.outlineEnabled);
  const parallaxEnabled = useAppStore((s) => s.parallaxEnabled);
  const parallaxIntensity = useAppStore((s) => s.parallaxIntensity);
  const dioramaParams = useAppStore((s) => s.dioramaParams);

  const objects = analysisResult?.objects ?? [];
  const assignedObjects = objects.filter((o) => assignments[o.id] !== undefined);

  // ─── Build/update scene when state changes ─────────────────────────────────
  const buildScene = useCallback(() => {
    const s = sceneRef.current;
    if (!s) return;

    // #region agent log
    console.log('[AICSS-DEBUG] buildScene called', {
      dioramaMode: s.dioramaMode,
      depthLayerKeys: Object.keys(depthLayerDioramaAssets),
      billboardKeys: Object.keys(billboardAssets),
      objectAssetKeys: Object.keys(objectDioramaAssets),
      assignedCount: assignedObjects.length,
      hasDepthMap: !!analysisResult?.depthMapUrl,
    });
    // #endregion

    const isPaper = s.dioramaMode === 'paper';

    // ── Paper layer meshes ─────────────────────────────────────────────────
    if (isPaper) {
      const layerMeshes: BABYLON.Mesh[] = [];

      DEPTH_LAYER_ORDER.forEach((layer) => {
        const dioramaAsset = depthLayerDioramaAssets[layer];
        const billboardAsset = depthLayerBillboardAssets[layer];
        const frontUrl =
          dioramaAsset?.outlinedUrl
          || dioramaAsset?.paperStyleUrl
          || dioramaAsset?.rgbaUrl
          || billboardAsset?.rgbaUrl;

        if (!frontUrl) {
          // #region agent log
          console.log('[AICSS-DEBUG] layer-skip-no-url', { layer, hasDiorama: !!dioramaAsset, dioramaKeys: dioramaAsset ? Object.keys(dioramaAsset) : [], hasBillboard: !!billboardAsset });
          // #endregion
          return;
        }
        // #region agent log
        console.log('[AICSS-DEBUG] layer-creating-mesh', { layer, frontUrlPrefix: frontUrl?.slice(0, 60) });
        // #endregion

        const thicknessWorld =
          LAYER_THICKNESS[layer] * (dioramaParams.thicknessMax / 5.0);
        const z = DEPTH_LAYER_Z[layer];

        const oldMesh = s.paperLayerMeshes.find(
          (m) => m.name === `paperLayer_${layer}`,
        );
        if (oldMesh) oldMesh.dispose();

        const mesh = BABYLON.MeshBuilder.CreateBox(
          `paperLayer_${layer}`,
          { width: SCENE_WIDTH, height: SCENE_HEIGHT, depth: thicknessWorld },
          s.scene,
        );
        mesh.position.set(0, 0, z);

        const frontMat = makePaperFrontMat(
          s.scene,
          frontUrl,
          dioramaAsset?.normalMapUrl,
          `paperFront_${layer}`,
        );
        const sideMat = makePaperSideMat(
          s.scene,
          dioramaAsset?.thicknessGrayUrl,
          `paperSide_${layer}`,
        );

        // BoxBuilder face order: 0=back, 1=front, 2=right, 3=left, 4=top, 5=bottom
        mesh.material = null;
        const multiMat = new BABYLON.MultiMaterial(`multi_${layer}`, s.scene);
        multiMat.subMaterials.push(frontMat); // back
        multiMat.subMaterials.push(frontMat); // front
        multiMat.subMaterials.push(sideMat);  // right
        multiMat.subMaterials.push(sideMat);  // left
        multiMat.subMaterials.push(sideMat);  // top
        multiMat.subMaterials.push(sideMat);  // bottom
        mesh.material = multiMat;

        mesh.subMeshes.forEach((sm) => sm.dispose());
        const verticesCount = mesh.getTotalVertices();
        [0, 1, 2, 3, 4, 5].forEach((i) => {
          new BABYLON.SubMesh(i, 0, verticesCount, i * 2, 2, mesh);
        });

        mesh.receiveShadows = true;
        s.shadowGenerator.addShadowCaster(mesh);
        layerMeshes.push(mesh);

        // Outline edge plane
        if (s.outlineEnabled) {
          const oldOutline = s.outlineMeshes.find(
            (m) => m.name === `outline_${layer}`,
          );
          if (oldOutline) oldOutline.dispose();

          const outlineColor = layer === 'foreground' ? '#ffffff' : '#e0ddd8';
          const outlineMat = makeOutlineMat(s.scene, frontUrl, outlineColor, 0.3);
          const outlinePlane = BABYLON.MeshBuilder.CreatePlane(
            `outline_${layer}`,
            { width: SCENE_WIDTH, height: SCENE_HEIGHT },
            s.scene,
          );
          outlinePlane.position.set(0, 0, z + 0.01);
          outlinePlane.material = outlineMat;
          outlinePlane.isPickable = false;
          s.outlineMeshes.push(outlinePlane);
        }
      });

      s.paperLayerMeshes = layerMeshes;
      // #region agent log
      console.log('[AICSS-DEBUG] buildScene-complete', {
        paperLayerMeshCount: layerMeshes.length,
        totalSceneMeshes: s.scene.meshes.length,
        sceneMeshNames: s.scene.meshes.map((m: BABYLON.Mesh) => m.name),
      });
      // #endregion
    }

    // ── Paper object meshes ─────────────────────────────────────────────────
    if (isPaper) {
      s.paperObjectMeshes.forEach((m) => m.dispose());
      s.paperObjectMeshes = [];

      assignedObjects.forEach((obj) => {
        const colorIndex = assignments[obj.id];
        const dioramaAsset = objectDioramaAssets[obj.id];
        const bbAsset = billboardAssets[obj.id];
        const textureUrl =
          dioramaAsset?.paperStyleUrl
          || dioramaAsset?.outlinedUrl
          || dioramaAsset?.rgbaUrl
          || bbAsset?.rgbaUrl;

        const sizeX = obj.boundingBox.w * SCENE_WIDTH;
        const sizeY = obj.boundingBox.h * SCENE_HEIGHT;
        const thicknessWorld =
          LAYER_THICKNESS.foreground * (dioramaParams.thicknessMax / 5.0);
        const pos = objectPosition(obj);

        const mesh = BABYLON.MeshBuilder.CreateBox(
          `paperObj_${obj.id}`,
          { width: sizeX, height: sizeY, depth: thicknessWorld },
          s.scene,
        );
        mesh.position.copyFrom(pos);

        const frontMat = textureUrl
          ? makePaperFrontMat(s.scene, textureUrl, undefined, `objFront_${obj.id}`)
          : makeColorMat(s.scene, LAYER_COLORS[colorIndex], 0.7);
        const sideMat = makeMat(s.scene, `objSide_${obj.id}`);
        sideMat.diffuseColor = PAPER_OBJ_SIDE_COLOR;
        sideMat.backFaceCulling = true;

        mesh.material = null;
        const multiMat = new BABYLON.MultiMaterial(`objMulti_${obj.id}`, s.scene);
        [0, 1, 2, 3, 4, 5].forEach((i) => {
          multiMat.subMaterials.push(i < 2 ? frontMat : sideMat);
        });
        mesh.material = multiMat;
        mesh.subMeshes.forEach((sm) => sm.dispose());
        const verticesCount = mesh.getTotalVertices();
        [0, 1, 2, 3, 4, 5].forEach((i) => {
          new BABYLON.SubMesh(i, 0, verticesCount, i * 2, 2, mesh);
        });

        mesh.receiveShadows = true;
        s.shadowGenerator.addShadowCaster(mesh);

        mesh.actionManager = new BABYLON.ActionManager(s.scene);
        mesh.actionManager.registerAction(
          new BABYLON.ExecuteCodeAction(
            BABYLON.ActionManager.OnPickTrigger,
            () => {
              setSelectedObjectId(
                selectedObjectId === obj.id ? null : obj.id,
              );
            },
          ),
        );

        s.paperObjectMeshes.push(mesh);
      });
    }

    // ── Billboard mode ─────────────────────────────────────────────────────
    if (!isPaper) {
      const bbMeshes: BABYLON.Mesh[] = [];

      DEPTH_LAYER_ORDER.forEach((layer) => {
        const asset = depthLayerBillboardAssets[layer];
        if (!asset?.rgbaUrl) return;

        const oldMesh = s.billboardMeshes.find(
          (m) => m.name === `bbLayer_${layer}`,
        );
        if (oldMesh) oldMesh.dispose();

        const mat = makeBillboardMat(s.scene, asset.rgbaUrl, undefined, 0.92);
        const plane = BABYLON.MeshBuilder.CreatePlane(
          `bbLayer_${layer}`,
          { width: SCENE_WIDTH, height: SCENE_HEIGHT },
          s.scene,
        );
        plane.position.set(0, 0, DEPTH_LAYER_Z[layer]);
        plane.material = mat;
        plane.isPickable = false;
        bbMeshes.push(plane);
      });

      assignedObjects.forEach((obj) => {
        const colorIndex = assignments[obj.id];
        const asset = billboardAssets[obj.id];
        const sizeX = obj.boundingBox.w * SCENE_WIDTH;
        const sizeY = obj.boundingBox.h * SCENE_HEIGHT;
        const pos = objectPosition(obj);

        const oldMesh = s.billboardMeshes.find(
          (m) => m.name === `bbObj_${obj.id}`,
        );
        if (oldMesh) oldMesh.dispose();

        const mat = asset?.rgbaUrl
          ? makeBillboardMat(s.scene, asset.rgbaUrl, undefined, 1.0)
          : makeColorMat(s.scene, LAYER_COLORS[colorIndex], 0.5);

        const plane = BABYLON.MeshBuilder.CreatePlane(
          `bbObj_${obj.id}`,
          { width: sizeX, height: sizeY },
          s.scene,
        );
        plane.position.copyFrom(pos);
        plane.material = mat;

        plane.actionManager = new BABYLON.ActionManager(s.scene);
        plane.actionManager.registerAction(
          new BABYLON.ExecuteCodeAction(
            BABYLON.ActionManager.OnPickTrigger,
            () => {
              setSelectedObjectId(
                selectedObjectId === obj.id ? null : obj.id,
              );
            },
          ),
        );

        bbMeshes.push(plane);
      });

      s.billboardMeshes.forEach((m) => m.dispose());
      s.billboardMeshes = bbMeshes;
    }
  }, [
    depthLayerDioramaAssets,
    depthLayerBillboardAssets,
    objectDioramaAssets,
    billboardAssets,
    assignments,
    assignedObjects,
    dioramaParams,
    selectedObjectId,
    setSelectedObjectId,
  ]);

  // ─── Init Babylon engine on mount ─────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return;
    // #region agent log
    console.log('[AICSS-DEBUG] useEffect-mount-start');
    // #endregion

    const canvas = document.createElement('canvas');
    canvas.style.width = '100%';
    canvas.style.height = '100%';
    canvas.style.display = 'block';
    containerRef.current.appendChild(canvas);
    canvasRef.current = canvas;
    setGlCanvas(canvas);

    const engine = new BABYLON.Engine(canvas, true, {
      antialias: true,
      preserveDrawingBuffer: true,
      stencil: true,
    });
    // #region agent log
    console.log('[AICSS-DEBUG] engine-created', { engineOk: !!engine, webglVersion: engine.webGLVersion, sceneCount: engine.scenes.length });
    // #endregion

    const scene = new BABYLON.Scene(engine);
    scene.clearColor = new BABYLON.Color4(0.039, 0.039, 0.059, 1);

    const camera = new BABYLON.ArcRotateCamera(
      'mainCam',
      -Math.PI / 2,
      Math.PI / 3,
      15,
      BABYLON.Vector3.Zero(),
      scene,
    );
    camera.attachControl(canvas, true);
    camera.lowerRadiusLimit = 3;
    camera.upperRadiusLimit = 60;
    camera.lowerBetaLimit = 0.1;
    camera.upperBetaLimit = Math.PI - 0.1;
    camera.inertia = 0.9;
    camera.panningInertia = 0.9;
    camera.wheelPrecision = 20;

    const hemiLight = new BABYLON.HemisphericLight(
      'hemi',
      new BABYLON.Vector3(0, 1, 0),
      scene,
    );
    hemiLight.intensity = 0.8;

    const dirLight = new BABYLON.DirectionalLight(
      'dir',
      new BABYLON.Vector3(-1, -2, -1),
      scene,
    );
    dirLight.position.set(5, 8, 10);
    dirLight.intensity = 1.2;
    dirLight.diffuse = BABYLON.Color3.FromHexString('#fff8e1');

    const fillLight = new BABYLON.DirectionalLight(
      'fill',
      new BABYLON.Vector3(1, 0.75, -1),
      scene,
    );
    fillLight.position.set(-4, -3, 5);
    fillLight.intensity = 0.3;
    fillLight.diffuse = BABYLON.Color3.FromHexString('#e3f2fd');

    const shadowGenerator = new BABYLON.ShadowGenerator(1024, dirLight);
    shadowGenerator.useBlurExponentialShadowMap = true;
    shadowGenerator.blurKernel = 32;

    let bgPlane: BABYLON.Mesh | null = null;
    const depthUrl = analysisResult?.depthMapUrl;
    if (depthUrl) {
      const bgMat = makeMat(scene, 'bgPlane');
      const tex = new BABYLON.Texture(depthUrl, scene, true, true);
      tex.gammaSpace = false;
      bgMat.diffuseTexture = tex;
      bgMat.emissiveTexture = tex;
      bgMat.alpha = 0.25;
      bgMat.backFaceCulling = false;
      bgPlane = BABYLON.MeshBuilder.CreatePlane(
        'bgPlane',
        { width: SCENE_WIDTH, height: SCENE_HEIGHT },
        scene,
      );
      bgPlane.position.set(0, 0, DEPTH_LAYER_Z.sky - 0.5);
      bgPlane.material = bgMat;
      bgPlane.isPickable = false;
    }

    const gridMesh = BABYLON.MeshBuilder.CreateGround(
      'grid',
      { width: SCENE_WIDTH, height: SCENE_HEIGHT },
      scene,
    );
    const gridMat = makeMat(scene, 'gridMat');
    gridMat.wireframe = true;
    gridMat.alpha = 0.3;
    gridMat.diffuseColor = BABYLON.Color3.FromHexString('#333333');
    gridMesh.position.set(0, -SCENE_HEIGHT / 2, 0);
    gridMesh.material = gridMat;
    gridMesh.isPickable = false;

    // Live pointer position for parallax
    const pointerNDC = { x: 0, y: 0 };

    sceneRef.current = {
      engine,
      scene,
      camera,
      hemiLight,
      dirLight,
      fillLight,
      shadowGenerator,
      paperLayerMeshes: [],
      paperObjectMeshes: [],
      billboardMeshes: [],
      outlineMeshes: [],
      bgPlane,
      gridMesh,
      baseCameraPos: DEFAULT_CAMERA_POS.clone(),
      parallaxEnabled: false,
      parallaxIntensity: 0.5,
      outlineEnabled: true,
      dioramaMode: 'billboard',
      pointerNDC,
    };

    // Parallax before-render
    scene.onBeforeRenderObservable.add(() => {
      const s = sceneRef.current;
      if (!s) return;

      if (s.parallaxEnabled && s.dioramaMode === 'paper') {
        const nx = s.pointerNDC.x - 0.5;
        const ny = s.pointerNDC.y - 0.5;
        camera.position.x = s.baseCameraPos.x + nx * s.parallaxIntensity * 2;
        camera.position.y = s.baseCameraPos.y + ny * s.parallaxIntensity * 1.5;
      } else {
        camera.position.x = BABYLON.Scalar.Lerp(
          camera.position.x,
          s.baseCameraPos.x,
          0.05,
        );
        camera.position.y = BABYLON.Scalar.Lerp(
          camera.position.y,
          s.baseCameraPos.y,
          0.05,
        );
      }
    });

    // Pointer move → update NDC coords
    canvas.addEventListener('pointermove', (e: PointerEvent) => {
      const s = sceneRef.current;
      if (!s) return;
      s.pointerNDC.x = e.clientX / (canvas.clientWidth || 1);
      s.pointerNDC.y = e.clientY / (canvas.clientHeight || 1);
    });

    engine.runRenderLoop(() => {
      scene.render();
      // #region agent log
      console.log('[AICSS-DEBUG] render-loop', { sceneReady: !!scene, meshCount: scene.meshes.length, canvasSize: canvas.width + ',' + canvas.height, dioramaMode: sceneRef.current?.dioramaMode });
      // #endregion
    });

    const handleResize = () => engine.resize();
    window.addEventListener('resize', handleResize);

    buildScene();
    // #region agent log
    console.log('[AICSS-DEBUG] init-complete', { sceneMeshCount: scene.meshes.length, sceneRefSet: !!sceneRef.current });
    // #endregion

    return () => {
      window.removeEventListener('resize', handleResize);
      scene.dispose();
      engine.dispose();
      if (
        containerRef.current
        && canvas.parentNode === containerRef.current
      ) {
        containerRef.current.removeChild(canvas);
      }
      sceneRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Diorama mode → rebuild
  useEffect(() => {
    const s = sceneRef.current;
    if (!s) return;
    s.dioramaMode = dioramaMode;

    if (dioramaMode === 'paper') {
      s.hemiLight.intensity = 0.8;
      s.dirLight.intensity = 1.2;
      s.fillLight.intensity = 0.3;
    } else {
      s.hemiLight.intensity = 1.0;
      s.dirLight.intensity = 0;
      s.fillLight.intensity = 0;
    }

    buildScene();
  }, [dioramaMode, buildScene]);

  // Assets / assignments → rebuild
  useEffect(() => {
    const s = sceneRef.current;
    if (!s) return;
    if (s.dioramaMode !== 'paper') return;
    buildScene();
  }, [
    buildScene,
    depthLayerDioramaAssets,
    depthLayerBillboardAssets,
    objectDioramaAssets,
    billboardAssets,
    assignments,
    assignedObjects,
    dioramaParams,
  ]);

  // Parallax settings
  useEffect(() => {
    const s = sceneRef.current;
    if (!s) return;
    s.parallaxEnabled = parallaxEnabled;
    s.parallaxIntensity = parallaxIntensity;
  }, [parallaxEnabled, parallaxIntensity]);

  // Outline toggle
  useEffect(() => {
    const s = sceneRef.current;
    if (!s) return;
    s.outlineEnabled = outlineEnabled;
    s.outlineMeshes.forEach((m) => m.setEnabled(outlineEnabled));
  }, [outlineEnabled]);

  // Depth map change
  useEffect(() => {
    const s = sceneRef.current;
    if (!s) return;
    const depthUrl = analysisResult?.depthMapUrl;
    if (s.bgPlane) {
      s.bgPlane.dispose();
      s.bgPlane = null;
    }
    if (depthUrl) {
      const bgMat = makeMat(s.scene, 'bgPlane');
      const tex = new BABYLON.Texture(depthUrl, s.scene, true, true);
      tex.gammaSpace = false;
      bgMat.diffuseTexture = tex;
      bgMat.emissiveTexture = tex;
      bgMat.alpha = 0.25;
      bgMat.backFaceCulling = false;
      const bg = BABYLON.MeshBuilder.CreatePlane(
        'bgPlane',
        { width: SCENE_WIDTH, height: SCENE_HEIGHT },
        s.scene,
      );
      bg.position.set(0, 0, DEPTH_LAYER_Z.sky - 0.5);
      bg.material = bgMat;
      bg.isPickable = false;
      s.bgPlane = bg;
    }
  }, [analysisResult?.depthMapUrl]);

  const hasAssignments =
    objects.length > 0 && Object.keys(assignments).length > 0;

  return (
    <div className="relative w-full h-full bg-gray-950">
      <div ref={containerRef} className="w-full h-full" />

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

      {dioramaMode === 'paper' && (
        <div className="absolute top-3 left-3 text-[10px] text-amber-500/60 bg-black/40 rounded px-2 py-1">
          移动鼠标触发视差动画
        </div>
      )}

      {selectedObjectId && analysisResult && (
        <div className="absolute bottom-3 left-3 bg-black/70 text-white text-xs px-3 py-2 rounded-lg">
          Selected:
          {selectedObjectId}
        </div>
      )}

      {!hasAssignments && analysisResult && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <p className="text-gray-600 text-sm">
            Assign objects to layers to see them here
          </p>
        </div>
      )}

      <ExportPanel canvasRef={{ current: glCanvas }} />
    </div>
  );
}
