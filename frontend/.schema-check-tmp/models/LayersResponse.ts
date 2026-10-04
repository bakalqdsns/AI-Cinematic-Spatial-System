/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * `POST /api/aicss/layers` response.
 */
export type LayersResponse = {
  /**
   * Per-layer entries with `name`, `zMin`, `zMax`, `objects`.
   */
  layers: Array<Record<string, any>>;
  width: number;
  height: number;
  savedFiles?: (Array<string> | null);
};

