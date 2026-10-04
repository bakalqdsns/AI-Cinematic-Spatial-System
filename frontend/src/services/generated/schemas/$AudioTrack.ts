/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $AudioTrack = {
  description: `A single audio track layered onto the final video.`,
  properties: {
    kind: {
      type: 'Enum',
      isRequired: true,
    },
    path: {
      type: 'string',
      description: `Absolute path to the audio file (mp3/wav/aac).`,
      isRequired: true,
    },
    volume: {
      type: 'number',
      description: `Volume multiplier applied to this track (1.0 = unity).`,
      maximum: 2,
    },
    start_at: {
      type: 'number',
      description: `Seconds offset into the final timeline where this track begins.`,
    },
  },
} as const;
