/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * `POST /api/aicss/scene-graph` response.
 */
export type SceneGraphResponse = {
  shotId: string;
  /**
   * Object nodes with relations (`leftOf`, `rightOf`, `inFrontOf`, `behind`, `above`, `below`).
   */
  nodes: Array<Record<string, any>>;
  savedFiles?: (Array<string> | null);
};

