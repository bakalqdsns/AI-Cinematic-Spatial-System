/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $MultifaceResponse = {
  description: `\`POST /api/aicss/multiface\` response.
  Returns 6 RGBA PNGs — one per cube face. Useful for 3D viewers that
  need a quick pseudo-3D representation of a 2D object without
  running a full 3D reconstruction.`,
  properties: {
    faces: {
      type: 'dictionary',
      contains: {
        type: 'string',
      },
    },
    width: {
      type: 'number',
    },
    height: {
      type: 'number',
    },
    savedFiles: {
      type: 'any-of',
      contains: [{
        type: 'array',
        contains: {
          type: 'string',
        },
      }, {
        type: 'null',
      }],
    },
  },
} as const;
