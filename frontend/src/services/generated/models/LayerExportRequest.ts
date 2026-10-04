/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type LayerExportRequest = {
  /**
   * Image URL (http/https), base64 data URL, or plain base64 string
   */
  imageUrl: string;
  /**
   * Optional depth map URL/base64 (H×W grayscale). When provided, pixels are bucketed into layers via the depth ranges in `layer_exporter.LAYER_Z_RANGES`.
   */
  depthMapUrl?: (string | null);
  /**
   * Optional subset of layer names to export. Defaults to all five: sky / background / midground / foreground / ground.
   */
  layers?: (Array<string> | null);
  /**
   * Edge feathering radius in pixels (0 = hard edges).
   */
  featherPx?: number;
  /**
   * When True, run GroundingDINO + SAM2 to produce per-object assets and merge them into the layer masks.
   */
  autoAnchor?: boolean;
  /**
   * Optional list of class names to override the scene-type fallback prompt (e.g. ['person','car','lamp']).
   */
  anchorPrompts?: (Array<string> | null);
  /**
   * Scene category for selecting the default GroundingDINO prompt. One of 'outdoor', 'indoor', 'night', 'nature'.
   */
  sceneType?: string;
  /**
   * When True (and autoAnchor is True), fit a RANSAC ground plane to detected ground region and emit a dedicated ground layer.
   */
  reconstructGround?: boolean;
  /**
   * Optional 3×3 camera intrinsics matrix flattened to 9 floats (row-major). When omitted we use focal=1.2*max(w,h), principal point at the image centre.
   */
  intrinsics?: (Array<number> | null);
  /**
   * When True, persist all assets to backend/test_outputs/objects/<sceneId>/.
   */
  saveArchive?: boolean;
  /**
   * Required when saveArchive=True; names the archive directory.
   */
  sceneId?: (string | null);
};

