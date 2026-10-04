/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $AnalyzeResponse = {
  description: `\`POST /api/aicss/analyze\` response — full pipeline output.
  The handler returns extra diagnostic fields (\`analysisId\`,
  \`vlmDetectedClasses\`, \`vlmDetectedScene\`) that aren't part of the
  core pipeline output but are useful for debugging and for the
  frontend to show the user which classes VLM detected. FastAPI's
  \`\`response_model_exclude_none=True\`\` would hide them on None; we
  instead expose them as Optional so the OpenAPI schema documents the
  real shape including diagnostic fields.`,
  properties: {
    analysisId: {
      type: 'any-of',
      description: `Unique analysis run ID (for log correlation)`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    shotId: {
      type: 'any-of',
      description: `Echoes the request's shotId so the frontend can correlate`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    depthMapUrl: {
      type: 'any-of',
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    objects: {
      type: 'array',
      contains: {
        type: 'dictionary',
        contains: {
          properties: {
          },
        },
      },
    },
    layers: {
      type: 'array',
      contains: {
        type: 'dictionary',
        contains: {
          properties: {
          },
        },
      },
    },
    sceneGraph: {
      type: 'any-of',
      contains: [{
        type: 'dictionary',
        contains: {
          properties: {
          },
        },
      }, {
        type: 'null',
      }],
    },
    width: {
      type: 'number',
    },
    height: {
      type: 'number',
    },
    savedFiles: {
      type: 'any-of',
      contains: [{
        type: 'array',
        contains: {
          type: 'string',
        },
      }, {
        type: 'null',
      }],
    },
    vlmDetectedClasses: {
      type: 'any-of',
      description: `Classes detected by the Qwen3-VL scene classifier (diagnostic)`,
      contains: [{
        type: 'array',
        contains: {
          type: 'string',
        },
      }, {
        type: 'null',
      }],
    },
    vlmDetectedScene: {
      type: 'any-of',
      description: `Scene type detected by VLM (outdoor/indoor/night/nature, diagnostic)`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
  },
} as const;
