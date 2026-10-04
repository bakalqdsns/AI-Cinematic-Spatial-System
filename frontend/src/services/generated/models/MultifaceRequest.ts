/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MultifaceRequest = {
  imageUrl: string;
  objectId: string;
  /**
   * {x, y, w, h} normalized 0-1
   */
  boundingBox: Record<string, any>;
  /**
   * [[x,y],...] normalized 0-1, overrides boundingBox for precise cropping
   */
  polygon?: Array<Array<number>>;
  /**
   * Optional project ID — when set, 6 face textures are persisted
   */
  projectId?: (string | null);
};

