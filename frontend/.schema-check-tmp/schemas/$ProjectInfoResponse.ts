/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $ProjectInfoResponse = {
  properties: {
    projectId: {
      type: 'string',
      isRequired: true,
    },
    shotId: {
      type: 'string',
      isRequired: true,
    },
    createdAt: {
      type: 'string',
      isRequired: true,
    },
    inputHash: {
      type: 'string',
      isRequired: true,
    },
    imageWidth: {
      type: 'any-of',
      contains: [{
        type: 'number',
      }, {
        type: 'null',
      }],
    },
    imageHeight: {
      type: 'any-of',
      contains: [{
        type: 'number',
      }, {
        type: 'null',
      }],
    },
  },
} as const;
