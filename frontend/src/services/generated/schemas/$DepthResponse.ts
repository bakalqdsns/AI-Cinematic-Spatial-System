/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $DepthResponse = {
  description: `\`POST /api/aicss/depth\` response.`,
  properties: {
    depthMapUrl: {
      type: 'string',
      description: `Base64 data URI of the depth map PNG (grayscale)`,
      isRequired: true,
    },
    width: {
      type: 'number',
      description: `Depth map width in pixels`,
      isRequired: true,
    },
    height: {
      type: 'number',
      description: `Depth map height in pixels`,
      isRequired: true,
    },
    minDepth: {
      type: 'number',
      description: `Minimum depth value (meters)`,
      isRequired: true,
    },
    maxDepth: {
      type: 'number',
      description: `Maximum depth value (meters)`,
      isRequired: true,
    },
    savedFiles: {
      type: 'any-of',
      description: `Filenames persisted under the project's \`depth/\` dir (when projectId was provided)`,
      contains: [{
        type: 'array',
        contains: {
          type: 'string',
        },
      }, {
        type: 'null',
      }],
    },
  },
} as const;
