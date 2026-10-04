/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export const $Body_create_project_api_aicss_projects_post = {
  properties: {
    shotId: {
      type: 'string',
      isRequired: true,
    },
    image: {
      type: 'string',
      isRequired: true,
    },
    imageWidth: {
      type: 'any-of',
      contains: [{
        type: 'number',
      }, {
        type: 'null',
      }],
    },
    imageHeight: {
      type: 'any-of',
      contains: [{
        type: 'number',
      }, {
        type: 'null',
      }],
    },
  },
} as const;
