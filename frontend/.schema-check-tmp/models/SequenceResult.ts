/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CrossFrameObject } from './CrossFrameObject';
import type { FrameResult } from './FrameResult';
import type { SceneLink } from './SceneLink';
import type { SequenceMetadata } from './SequenceMetadata';
export type SequenceResult = {
  sequenceId: string;
  shotId: string;
  projectId?: (string | null);
  createdAt: string;
  frameCount: number;
  frames: Array<FrameResult>;
  sceneLinks: Array<SceneLink>;
  crossFrameObjects: Array<CrossFrameObject>;
  metadata: SequenceMetadata;
};

