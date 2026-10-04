/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CrossFrameObject } from './CrossFrameObject';
import type { FrameLink } from './FrameLink';
export type SceneLinksResponse = {
  sequenceId: string;
  shotId: string;
  frameLinks: Array<FrameLink>;
  crossFrameObjects: Array<CrossFrameObject>;
  statistics: Record<string, any>;
};

