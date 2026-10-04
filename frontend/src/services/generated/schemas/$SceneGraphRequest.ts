/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $SceneGraphRequest = {
  properties: {
    shotId: {
      type: 'string',
      isRequired: true,
    },
    objects: {
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
    projectId: {
      type: 'any-of',
      description: `Optional project ID — when set, scene graph is persisted`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
  },
} as const;
