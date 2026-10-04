/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $ExtractCharactersRequest = {
  properties: {
    raw_text: {
      type: 'string',
      description: `Raw script text`,
      isRequired: true,
    },
    language: {
      type: 'string',
      description: `chinese, english, japanese`,
    },
    project_id: {
      type: 'any-of',
      description: `Optional project ID for persistence`,
      contains: [{
        type: 'string',
      }, {
        type: 'null',
      }],
    },
  },
} as const;
