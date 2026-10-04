/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GenerateShotsRequest = {
  /**
   * Serialized ScriptData from parse step
   */
  script_data: Record<string, any>;
  /**
   * Lower bound per scene. Total shot count is also driven by story_paragraph count — see /shots endpoint doc.
   */
  shots_per_scene?: number;
  language?: (string | null);
  project_id?: (string | null);
};

