#!/usr/bin/env node
// @ts-check
/**
 * check:schema — CI guard. Regenerates the typed client into a temp dir
 * under the frontend/ subtree from the committed frontend/openapi.json and
 * compares it against the checked-in src/services/generated/. Exits non-zero
 * if they differ, so a PR that changes the backend schema without
 * regenerating the client is caught.
 *
 * This does NOT require the backend to be running.
 *
 * Why the temp dir lives under frontend/ (not os.tmpdir()):
 *   openapi-typescript-codegen refuses to write outside the current working
 *   directory ("Output folder is not a subdirectory of the current working
 *   directory"). Putting the temp dir inside frontend/ satisfies that guard.
 *
 * Why we don't use `git diff --no-index`:
 *   This project may not be a git repo (and CI runners sometimes disable
 *   `git diff --no-index` for non-repo paths). We instead walk both trees
 *   with Node's fs, hash every file with SHA-256, and compare the
 *   (relative-path → hash) maps. Pure Node, no git/diff dependency.
 */
import { spawnSync } from 'node:child_process';
import {
  mkdirSync,
  rmSync,
  existsSync,
  readdirSync,
  readFileSync,
  statSync,
} from 'node:fs';
import { createHash } from 'node:crypto';
import { join, resolve, dirname, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const frontendDir = resolve(__dirname, '..');
const openapiPath = resolve(frontendDir, 'openapi.json');
const committed = resolve(frontendDir, 'src', 'services', 'generated');

// Temp dir MUST live under frontend/ so openapi-typescript-codegen's
// "output must be a subdirectory of cwd" guard is satisfied.
const tmp = resolve(frontendDir, '.schema-check-tmp');

if (!existsSync(openapiPath)) {
  console.error('[check:schema] openapi.json missing');
  process.exit(1);
}
if (!existsSync(committed)) {
  console.error('[check:schema] src/services/generated/ missing — run `npm run gen:api` first');
  process.exit(1);
}

// Always start from a clean temp dir so stale files from a previous run
// can't make the comparison falsely pass.
rmSync(tmp, { recursive: true, force: true });
mkdirSync(tmp, { recursive: true });

try {
  // Codegen args MUST stay aligned with scripts/gen-api.mjs. The only
  // difference is --output (temp dir here vs src/services/generated there).
  const args = [
    'openapi',
    '--input', openapiPath,
    '--output', tmp,
    '--client', 'axios',
    '--useOptions',
    '--useUnionTypes',
    '--exportCore', 'true',
    '--exportSchemas', 'true',
    '--exportServices', 'true',
    '--indent', '2',
    '--name', 'AicssClient',
  ];
  const r = spawnSync('npx', args, { shell: true, cwd: frontendDir });
  if (r.status !== 0) {
    console.error('[check:schema] codegen failed');
    if (r.stdout) console.log(r.stdout.toString());
    if (r.stderr) console.error(r.stderr.toString());
    process.exit(r.status ?? 1);
  }

  const tmpMap = collectFileHashes(tmp);
  const committedMap = collectFileHashes(committed);

  const diffs = compareMaps(tmpMap, committedMap);

  if (diffs.length === 0) {
    console.log(`[check:schema] generated client is up to date (${tmpMap.size} files matched).`);
    process.exit(0);
  } else {
    console.error('[check:schema] generated client is stale. Differences:');
    for (const d of diffs) {
      console.error(`  ${d.kind.padEnd(10)} ${d.path}`);
    }
    console.error('');
    console.error('[check:schema] Run `npm run gen:api` and commit the result.');
    process.exit(1);
  }
} finally {
  rmSync(tmp, { recursive: true, force: true });
}

// ─── helpers ───────────────────────────────────────────────────────────────

/**
 * Recursively walk a directory and return a Map of relative-posix-path → SHA-256
 * hex digest of the file contents. Symlinks/dirs are skipped; only regular
 * files are hashed.
 * @param {string} root  Absolute directory to walk.
 * @returns {Map<string, string>}
 */
function collectFileHashes(root) {
  /** @type {Map<string, string>} */
  const map = new Map();
  const stack = [root];
  while (stack.length > 0) {
    const cur = stack.pop();
    let entries;
    try {
      entries = readdirSync(cur);
    } catch {
      continue;
    }
    for (const name of entries) {
      const full = join(cur, name);
      let st;
      try {
        st = statSync(full);
      } catch {
        continue;
      }
      if (st.isDirectory()) {
        stack.push(full);
      } else if (st.isFile()) {
        const rel = relative(root, full).split('\\').join('/');
        const buf = readFileSync(full);
        const hash = createHash('sha256').update(buf).digest('hex');
        map.set(rel, hash);
      }
    }
  }
  return map;
}

/**
 * Compare two (path → hash) maps and return a list of differences.
 * @param {Map<string, string>} generated
 * @param {Map<string, string>} committed
 * @returns {{ kind: 'added' | 'removed' | 'modified', path: string }[]}
 */
function compareMaps(generated, committed) {
  /** @type {{ kind: 'added' | 'removed' | 'modified', path: string }[]} */
  const diffs = [];
  for (const [path, hash] of generated) {
    const other = committed.get(path);
    if (other === undefined) {
      diffs.push({ kind: 'added', path });
    } else if (other !== hash) {
      diffs.push({ kind: 'modified', path });
    }
  }
  for (const path of committed.keys()) {
    if (!generated.has(path)) {
      diffs.push({ kind: 'removed', path });
    }
  }
  diffs.sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0));
  return diffs;
}
