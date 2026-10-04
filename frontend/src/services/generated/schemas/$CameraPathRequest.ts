/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $CameraPathRequest = {
  description: `Request body for the camera-path generator.`,
  properties: {
    cameraMovement: {
      type: 'string',
      description: `One of the 13 CameraMovement values (Static, Dolly In, …)`,
      isRequired: true,
    },
    shotSize: {
      type: 'string',
      description: `One of the 10 ShotSize values (Wide Shot, Close-up, …)`,
      isRequired: true,
    },
    durationSeconds: {
      type: 'number',
      description: `Shot duration in seconds. Drives nothing in the keyframes themselves but is echoed back so the client can sanity-check.`,
      maximum: 60,
      minimum: 0.1,
    },
  },
} as const;
