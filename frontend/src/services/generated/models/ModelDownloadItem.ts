/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ModelDownloadItem = {
  name: string;
  model_id: string;
  status: string;
  size_gb?: number;
  path?: string;
  progress?: (number | null);
  bytes_done?: (number | null);
  bytes_total?: (number | null);
  current_file?: (string | null);
  files_done?: (number | null);
  files_total?: (number | null);
  speed_bps?: (number | null);
  eta_seconds?: (number | null);
  attempt?: (number | null);
  max_attempts?: (number | null);
  error_message?: (string | null);
};

