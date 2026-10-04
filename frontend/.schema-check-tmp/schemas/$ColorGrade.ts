/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $ColorGrade = {
  description: `Optional color grade applied as the final composition step.`,
  properties: {
    lut_path: {
      type: 'any-of',
      description: `Path to a .cube LUT file. When set, lut3d is applied first.`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    brightness: {
      type: 'number',
      description: `eq brightness.`,
      maximum: 1,
      minimum: -1,
    },
    contrast: {
      type: 'number',
      description: `eq contrast (1.0 = unity).`,
      maximum: 10,
    },
    saturation: {
      type: 'number',
      description: `eq saturation (1.0 = unity).`,
      maximum: 3,
    },
  },
} as const;
