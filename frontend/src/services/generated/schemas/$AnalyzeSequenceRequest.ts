/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $AnalyzeSequenceRequest = {
  description: `Analyze an image sequence (multiple frames from the same shot).`,
  properties: {
    shotId: {
      type: 'string',
      description: `Shot ID`,
      isRequired: true,
    },
    frameIds: {
      type: 'array',
      contains: {
        type: 'string',
      },
      isRequired: true,
    },
    imageUrls: {
      type: 'array',
      contains: {
        type: 'string',
      },
      isRequired: true,
    },
    projectId: {
      type: 'any-of',
      description: `Optional project ID for persistence`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    enableTracking: {
      type: 'boolean',
      description: `Enable cross-frame object tracking`,
    },
    trackingMode: {
      type: 'Enum',
    },
    frameTypes: {
      type: 'any-of',
      description: `Optional per-frame types (same length as frameIds)`,
      contains: [{
        type: 'array',
        contains: {
          type: 'Enum',
        },
      }, {
        type: 'null',
      }],
    },
    frameDescriptions: {
      type: 'any-of',
      description: `Optional per-frame descriptions`,
      contains: [{
        type: 'array',
        contains: {
          type: 'string',
        },
      }, {
        type: 'null',
      }],
    },
    matchingThreshold: {
      type: 'number',
      description: `Matching threshold`,
      maximum: 1,
    },
    maxCandidatesPerObject: {
      type: 'number',
      description: `Max tracking candidates`,
      maximum: 50,
      minimum: 1,
    },
  },
} as const;
