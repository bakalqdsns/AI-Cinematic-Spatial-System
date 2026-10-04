/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * `POST /api/aicss/analyze` response — full pipeline output.
 *
 * The handler returns extra diagnostic fields (`analysisId`,
 * `vlmDetectedClasses`, `vlmDetectedScene`) that aren't part of the
 * core pipeline output but are useful for debugging and for the
 * frontend to show the user which classes VLM detected. FastAPI's
 * ``response_model_exclude_none=True`` would hide them on None; we
 * instead expose them as Optional so the OpenAPI schema documents the
 * real shape including diagnostic fields.
 */
export type AnalyzeResponse = {
  /**
   * Unique analysis run ID (for log correlation)
   */
  analysisId?: (string | null);
  /**
   * Echoes the request's shotId so the frontend can correlate
   */
  shotId?: (string | null);
  depthMapUrl?: (string | null);
  objects?: Array<Record<string, any>>;
  layers?: Array<Record<string, any>>;
  sceneGraph?: (Record<string, any> | null);
  width?: number;
  height?: number;
  savedFiles?: (Array<string> | null);
  /**
   * Classes detected by the Qwen3-VL scene classifier (diagnostic)
   */
  vlmDetectedClasses?: (Array<string> | null);
  /**
   * Scene type detected by VLM (outdoor/indoor/night/nature, diagnostic)
   */
  vlmDetectedScene?: (string | null);
};

