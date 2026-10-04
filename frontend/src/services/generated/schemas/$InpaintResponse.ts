/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $InpaintResponse = {
  description: `\`POST /api/aicss/inpaint\` response.`,
  properties: {
    imageUrl: {
      type: 'string',
      description: `Base64 data URI of the inpainted PNG`,
      isRequired: true,
    },
    inpaintResultUrl: {
      type: 'any-of',
      description: `Alias of imageUrl, kept for backward compat`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    width: {
      type: 'number',
      isRequired: true,
    },
    height: {
      type: 'number',
      isRequired: true,
    },
    model: {
      type: 'any-of',
      description: `Model identifier used for inpainting`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
    maskWhiteRatio: {
      type: 'any-of',
      description: `Ratio of white pixels in the mask`,
      contains: [{
        type: 'number',
      }, {
        type: 'null',
      }],
    },
    warnings: {
      type: 'any-of',
      contains: [{
        type: 'null',
      }],
    },
    savedArtifacts: {
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
    usedFallback: {
      type: 'boolean',
      description: `True when the call fell back from cloud to local LaMa.`,
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
