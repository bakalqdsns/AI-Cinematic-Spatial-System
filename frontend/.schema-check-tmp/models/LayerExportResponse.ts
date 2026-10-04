/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GroundAssetSummary } from './GroundAssetSummary';
import type { LayerDataUri } from './LayerDataUri';
import type { LayerZOffset } from './LayerZOffset';
import type { ObjectAssetSummary } from './ObjectAssetSummary';
export type LayerExportResponse = {
  /**
   * Image width in pixels
   */
  width: number;
  /**
   * Image height in pixels
   */
  height: number;
  /**
   * Per-layer RGBA PNG data URIs keyed by layer name
   */
  layers: Record<string, LayerDataUri>;
  /**
   * Z-axis offset table for the Blender plugin
   */
  zOffsets: Array<LayerZOffset>;
  /**
   * Per-object RGBA cutouts + metadata (Phase 2)
   */
  objects?: Array<ObjectAssetSummary>;
  /**
   * Reconstructed ground plane asset (Phase 2)
   */
  ground?: (GroundAssetSummary | null);
  /**
   * Map layer → list of object_ids in that layer (Phase 2)
   */
  layer_assignment?: Record<string, Array<string>>;
};

