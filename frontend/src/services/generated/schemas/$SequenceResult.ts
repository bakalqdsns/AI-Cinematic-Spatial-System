/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $SequenceResult = {
  properties: {
    sequenceId: {
      type: 'string',
      isRequired: true,
    },
    shotId: {
      type: 'string',
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
    createdAt: {
      type: 'string',
      isRequired: true,
    },
    frameCount: {
      type: 'number',
      isRequired: true,
    },
    frames: {
      type: 'array',
      contains: {
        type: 'FrameResult',
      },
      isRequired: true,
    },
    sceneLinks: {
      type: 'array',
      contains: {
        type: 'SceneLink',
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
    metadata: {
      type: 'SequenceMetadata',
      isRequired: true,
    },
  },
} as const;
