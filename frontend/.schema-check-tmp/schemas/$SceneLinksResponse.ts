/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $SceneLinksResponse = {
  properties: {
    sequenceId: {
      type: 'string',
      isRequired: true,
    },
    shotId: {
      type: 'string',
      isRequired: true,
    },
    frameLinks: {
      type: 'array',
      contains: {
        type: 'FrameLink',
      },
      isRequired: true,
    },
    crossFrameObjects: {
      type: 'array',
      contains: {
        type: 'CrossFrameObject',
      },
      isRequired: true,
    },
    statistics: {
      type: 'dictionary',
      contains: {
        properties: {
        },
      },
      isRequired: true,
    },
  },
} as const;
