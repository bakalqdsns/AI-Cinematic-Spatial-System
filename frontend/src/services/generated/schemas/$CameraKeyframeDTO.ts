/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $CameraKeyframeDTO = {
  description: `One keyframe in the camera path.`,
  properties: {
    time: {
      type: 'number',
      isRequired: true,
      maximum: 1,
    },
    position: {
      type: 'array',
      contains: {
        type: 'number',
      },
      isRequired: true,
    },
    target: {
      type: 'array',
      contains: {
        type: 'number',
      },
      isRequired: true,
    },
    fov: {
      type: 'number',
      description: `Vertical FOV in degrees`,
      isRequired: true,
    },
  },
} as const;
