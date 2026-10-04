/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * `POST /api/aicss/paper-style` response.
 *
 * Single-image cartoonisation — the input RGB image gets a flat paper-style
 * texture applied. Distinct from `PaperDioramaResponse` which adds
 * thickness/normal maps.
 */
export type PaperStyleResponse = {
  paperStyleUrl?: (string | null);
  width?: number;
  height?: number;
  savedFiles?: (Array<string> | null);
};

