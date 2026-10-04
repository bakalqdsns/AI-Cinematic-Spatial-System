/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $PaperStyleResponse = {
  description: `\`POST /api/aicss/paper-style\` response.
  Single-image cartoonisation — the input RGB image gets a flat paper-style
  texture applied. Distinct from \`PaperDioramaResponse\` which adds
  thickness/normal maps.`,
  properties: {
    paperStyleUrl: {
      type: 'any-of',
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
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
