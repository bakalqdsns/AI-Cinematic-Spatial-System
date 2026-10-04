/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $OcclusionHolesRequest = {
  description: `从 Analyze 物体列表自动生成遮挡空洞 mask（不跑 LaMa）。`,
  properties: {
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
    imageWidth: {
      type: 'number',
      isRequired: true,
    },
    imageHeight: {
      type: 'number',
      isRequired: true,
    },
    targetObjectIds: {
      type: 'any-of',
      description: `仅对这些 objectId 生成空洞；省略则全部`,
      contains: [{
        type: 'array',
        contains: {
          type: 'string',
        },
      }, {
        type: 'null',
      }],
    },
    mode: {
      type: 'string',
      description: `peel=整物体 mask；occluded_interior=仅被更近物体遮挡的重叠区`,
    },
  },
} as const;
