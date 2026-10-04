#!/usr/bin/env node
// @ts-check
/**
 * gen:api — refresh frontend/openapi.json from the running backend (if
 * reachable) and regenerate the typed client into src/services/generated/.
 *
 * Fallback: if the backend is not running, the existing frontend/openapi.json
 * (committed) is used as the input so the command still works offline / in CI.
 *
 * Backend port is read from VITE_AICSS_BACKEND or defaults to 8000 (matches
 * backend/app/config.py `Settings.port`).
 */
import { spawnSync } from 'node:child_process';
import { writeFileSync, readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import process from 'node:process';

const __dirname = dirname(fileURLToPath(import.meta.url));
const frontendDir = resolve(__dirname, '..');
const openapiPath = resolve(frontendDir, 'openapi.json');

// Resolve backend URL. Strip any trailing path; we append /openapi.json.
const backendEnv = process.env.VITE_AICSS_BACKEND || process.env.AICSS_BACKEND;
const backendBase = (backendEnv && backendEnv.replace(/\/$/, '')) || 'http://localhost:8000';
const openapiUrl = `${backendBase}/openapi.json`;

async function fetchOpenApi() {
  try {
    const controller = new AbortController();
    const t = setTimeout(() => controller.abort(), 4000);
    const resp = await fetch(openapiUrl, { signal: controller.signal });
    clearTimeout(t);
    if (!resp.ok) {
      console.warn(`[gen:api] backend returned HTTP ${resp.status} — keeping local openapi.json`);
      return false;
    }
    const text = await resp.text();
    const json = JSON.parse(text);
    writeFileSync(openapiPath, JSON.stringify(json, null, 2), 'utf8');
    console.log(`[gen:api] fetched openapi.json from ${openapiUrl} (${json.paths ? Object.keys(json.paths).length : '?'} paths)`);
    return true;
  } catch (err) {
    console.warn(`[gen:api] backend not reachable at ${openapiUrl}: ${err.message}`);
    return false;
  }
}

async function main() {
  if (!existsSync(openapiPath)) {
    console.error(`[gen:api] ${openapiPath} not found. Starting backend or commit a snapshot.`);
    process.exit(1);
  }
  const fetched = await fetchOpenApi();
  if (!fetched) {
    console.log(`[gen:api] using committed ${openapiPath}`);
  }

  // Run openapi-typescript-codegen via npx (uses local devDependency).
  const args = [
    'openapi',
    '--input', openapiPath,
    '--output', resolve(frontendDir, 'src', 'services', 'generated'),
    '--client', 'axios',
    '--useOptions',
    '--useUnionTypes',
    '--exportCore', 'true',
    '--exportSchemas', 'true',
    '--exportServices', 'true',
    '--indent', '2',
    '--name', 'AicssClient',
  ];
  console.log(`[gen:api] $ npx ${args.join(' ')}`);
  const r = spawnSync('npx', args, { stdio: 'inherit', shell: true, cwd: frontendDir });
  if (r.status !== 0) {
    console.error(`[gen:api] codegen failed (exit ${r.status})`);
    process.exit(r.status ?? 1);
  }
  console.log('[gen:api] done.');
}

main();
