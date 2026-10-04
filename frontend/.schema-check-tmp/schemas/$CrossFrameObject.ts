/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $CrossFrameObject = {
  properties: {
    globalId: {
      type: 'string',
      isRequired: true,
    },
    classLabel: {
      type: 'string',
      isRequired: true,
    },
    appearances: {
      type: 'array',
      contains: {
        type: 'ObjectAppearance',
      },
      isRequired: true,
    },
  },
} as const;
