/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $ArchiveShotResponse = {
  properties: {
    projectId: {
      type: 'string',
      isRequired: true,
    },
    shotId: {
      type: 'string',
      isRequired: true,
    },
    fileName: {
      type: 'string',
      isRequired: true,
    },
    fileSize: {
      type: 'number',
      isRequired: true,
    },
    fileCount: {
      type: 'number',
      isRequired: true,
    },
    downloadUrl: {
      type: 'string',
      isRequired: true,
    },
    layerCount: {
      type: 'number',
    },
    meshCount: {
      type: 'number',
    },
  },
} as const;
