/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $CameraPathResponse = {
  description: `Response — 1 or 2 keyframes (Phase 1: linear start/end interpolation).`,
  properties: {
    movement: {
      type: 'string',
      isRequired: true,
    },
    shotSize: {
      type: 'string',
      isRequired: true,
    },
    durationSeconds: {
      type: 'number',
      isRequired: true,
    },
    keyframes: {
      type: 'array',
      contains: {
        type: 'CameraKeyframeDTO',
      },
      isRequired: true,
    },
  },
} as const;
