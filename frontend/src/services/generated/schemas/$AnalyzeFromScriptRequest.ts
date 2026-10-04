/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $AnalyzeFromScriptRequest = {
  description: `Analyze frames defined by script scenes.`,
  properties: {
    shotId: {
      type: 'string',
      isRequired: true,
    },
    scenes: {
      type: 'array',
      contains: {
        type: 'ScriptScene',
      },
      isRequired: true,
    },
    projectId: {
      type: 'any-of',
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    enableTracking: {
      type: 'boolean',
    },
    trackingMode: {
      type: 'Enum',
    },
  },
} as const;
