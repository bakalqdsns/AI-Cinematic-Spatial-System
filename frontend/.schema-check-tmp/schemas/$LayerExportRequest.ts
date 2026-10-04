/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $LayerExportRequest = {
  properties: {
    imageUrl: {
      type: 'string',
      description: `Image URL (http/https), base64 data URL, or plain base64 string`,
      isRequired: true,
    },
    depthMapUrl: {
      type: 'any-of',
      description: `Optional depth map URL/base64 (H×W grayscale). When provided, pixels are bucketed into layers via the depth ranges in \`layer_exporter.LAYER_Z_RANGES\`.`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    layers: {
      type: 'any-of',
      description: `Optional subset of layer names to export. Defaults to all five: sky / background / midground / foreground / ground.`,
      contains: [{
        type: 'array',
        contains: {
          type: 'string',
        },
      }, {
        type: 'null',
      }],
    },
    featherPx: {
      type: 'number',
      description: `Edge feathering radius in pixels (0 = hard edges).`,
      maximum: 10,
    },
    autoAnchor: {
      type: 'boolean',
      description: `When True, run GroundingDINO + SAM2 to produce per-object assets and merge them into the layer masks.`,
    },
    anchorPrompts: {
      type: 'any-of',
      description: `Optional list of class names to override the scene-type fallback prompt (e.g. ['person','car','lamp']).`,
      contains: [{
        type: 'array',
        contains: {
          type: 'string',
        },
      }, {
        type: 'null',
      }],
    },
    sceneType: {
      type: 'string',
      description: `Scene category for selecting the default GroundingDINO prompt. One of 'outdoor', 'indoor', 'night', 'nature'.`,
    },
    reconstructGround: {
      type: 'boolean',
      description: `When True (and autoAnchor is True), fit a RANSAC ground plane to detected ground region and emit a dedicated ground layer.`,
    },
    intrinsics: {
      type: 'any-of',
      description: `Optional 3×3 camera intrinsics matrix flattened to 9 floats (row-major). When omitted we use focal=1.2*max(w,h), principal point at the image centre.`,
      contains: [{
        type: 'array',
        contains: {
          type: 'number',
        },
      }, {
        type: 'null',
      }],
    },
    saveArchive: {
      type: 'boolean',
      description: `When True, persist all assets to backend/test_outputs/objects/<sceneId>/.`,
    },
    sceneId: {
      type: 'any-of',
      description: `Required when saveArchive=True; names the archive directory.`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
  },
} as const;
