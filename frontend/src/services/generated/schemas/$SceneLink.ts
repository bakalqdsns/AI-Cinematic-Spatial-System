/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $SceneLink = {
  properties: {
    sourceFrameId: {
      type: 'string',
      isRequired: true,
    },
    targetFrameId: {
      type: 'string',
      isRequired: true,
    },
    linkType: {
      type: 'Enum',
      isRequired: true,
    },
    confidence: {
      type: 'number',
      isRequired: true,
    },
  },
} as const;
