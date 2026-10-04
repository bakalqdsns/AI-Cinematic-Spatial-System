// ─────────────────────────────────────────────────────────────────────────────
// Generated OpenAPI client singleton.
//
// All handwritten service modules (`aicssService.ts`, `scriptService.ts`, ...)
// import `generatedClient` from here and delegate HTTP calls to the typed
// service methods produced by `openapi-typescript-codegen`. This keeps the
// service files as thin wrappers that only own camelCase ↔ snake_case field
// mapping and signature stability for their callers (stores / components).
//
// The BASE URL is read from `VITE_AICSS_BACKEND` (same env var the handwritten
// axios clients used) so behaviour is unchanged.
// ─────────────────────────────────────────────────────────────────────────────
import { AicssClient } from './generated';

const DEFAULT_BACKEND =
  import.meta.env.VITE_AICSS_BACKEND || 'http://localhost:8000';

export const generatedClient = new AicssClient({
  BASE: DEFAULT_BACKEND,
});

export { DEFAULT_BACKEND };
