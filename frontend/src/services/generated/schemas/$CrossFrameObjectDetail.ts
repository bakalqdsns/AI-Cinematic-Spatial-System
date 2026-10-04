/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $CrossFrameObjectDetail = {
  properties: {
    globalId: {
      type: 'string',
      isRequired: true,
    },
    classLabel: {
      type: 'string',
      isRequired: true,
    },
    totalAppearances: {
      type: 'number',
      isRequired: true,
    },
    appearances: {
      type: 'array',
      contains: {
        type: 'ObjectAppearanceDetail',
      },
      isRequired: true,
    },
    trajectory: {
      type: 'dictionary',
      contains: {
        properties: {
        },
      },
      isRequired: true,
    },
    layerHistory: {
      type: 'array',
      contains: {
        type: 'dictionary',
        contains: {
          properties: {
          },
        },
      },
      isRequired: true,
    },
  },
} as const;
