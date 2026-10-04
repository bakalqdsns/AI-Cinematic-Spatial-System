/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GenerateThreeViewRequest = {
  character_id: string;
  character_name: string;
  character_gender?: string;
  character_age?: string;
  character_personality?: string;
  visual_prompt?: (string | null);
  /**
   * Base64 or URL
   */
  reference_image?: (string | null);
  project_id?: (string | null);
};

