/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * `POST /api/aicss/paper-layer` response.
 *
 * Same texture set as `PaperDioramaResponse` but for an entire depth layer
 * (e.g. the foreground layer of a scene). Adds a `layerKey` echo so the
 * frontend can route the response back to the right layer.
 */
export type PaperLayerResponse = {
  paperStyleUrl?: (string | null);
  normalMapUrl?: (string | null);
  thicknessGrayUrl?: (string | null);
  outlinedUrl?: (string | null);
  width?: number;
  height?: number;
  savedFiles?: (Array<string> | null);
  layerKey?: (string | null);
};

