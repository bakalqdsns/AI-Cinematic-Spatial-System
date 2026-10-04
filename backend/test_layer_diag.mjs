/**
 * Diagnostic: dumps the 4 layer PNGs from `/layers/export` to disk, computes
 * SHA256 per layer, decodes the alpha channel, and reports:
 *   - which layers are byte-identical (BUG indicator)
 *   - per-layer alpha distribution (visible vs transparent pixel counts)
 *   - alpha histogram entropy
 *
 * A correct run: 4 different SHA256, alpha varying per layer (some ~10%, some
 * ~30%, etc.). The bug: 4 same SHA256 + alpha all 100%.
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import zlib from 'node:zlib';

const BACKEND = process.env.BACKEND_URL || 'http://127.0.0.1:8000';
const FIXTURE = 'backend/test_outputs/20260728_184938_scene_forest/wide.png';
const OUT_DIR = path.resolve('backend/test_outputs/_layer_diag');

const buf = fs.readFileSync(FIXTURE);
const b64 = buf.toString('base64');

const res = await fetch(`${BACKEND}/api/aicss/layers/export`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ imageUrl: b64 }),
});
const text = await res.text();
let json;
try { json = JSON.parse(text); } catch { json = null; }
if (!res.ok) {
  console.log(`HTTP ${res.status}`);
  console.log('Body:', text.slice(0, 500));
  process.exit(1);
}

fs.mkdirSync(OUT_DIR, { recursive: true });
const summary = {};

for (const [name, layer] of Object.entries(json.layers)) {
  const raw = Buffer.from(layer.dataUri.split(',', 2)[1], 'base64');
  const sha = crypto.createHash('sha256').update(raw).digest('hex').slice(0, 16);
  fs.writeFileSync(path.join(OUT_DIR, `${name}.png`), raw);

  // Decode PNG IDAT chunks manually to extract the alpha channel without
  // pulling in a PNG library.
  const decoded = decodePngRgba(raw);
  const alpha = decoded.alpha; // Uint8Array length h*w
  let visible = 0;
  const histo = new Array(8).fill(0); // bins: 0, 32, 64, 96, 128, 160, 192, 224-255
  for (const a of alpha) {
    if (a > 8) visible++;
    histo[Math.min(7, a >> 5)]++;
  }
  summary[name] = {
    sha,
    bytes: raw.length,
    width: decoded.width,
    height: decoded.height,
    visibleRatio: (visible / alpha.length).toFixed(3),
    histo: histo.map(c => Math.round((c / alpha.length) * 100) + '%'),
  };
}

console.log('\n=== Layer diagnostic ===');
console.log('Fixture:', FIXTURE, `(${buf.length} bytes)`);
console.log('Output:', OUT_DIR);
console.log();
for (const [name, s] of Object.entries(summary)) {
  console.log(`  ${name.padEnd(11)} sha=${s.sha}  bytes=${String(s.bytes).padStart(7)}  visible=${s.visibleRatio}  histo=[${s.histo.join(', ')}]`);
}
const shas = Object.values(summary).map(s => s.sha);
const uniqueShas = new Set(shas).size;
console.log();
if (uniqueShas === 1) {
  console.log('❌ BUG: All 4 layers are byte-identical. export_layers was called with mask = ones((h,w)) — no depth bucketing happened.');
} else if (uniqueShas === 4) {
  console.log('✅ OK: All 4 layers have distinct content.');
} else {
  console.log(`⚠️  PARTIAL: ${uniqueShas}/4 unique layers. Some layers may still share content.`);
}

const visRatios = Object.values(summary).map(s => parseFloat(s.visibleRatio));
const allFullOpacity = visRatios.every(v => v >= 0.99);
const allSameRatio = visRatios.every(v => v === visRatios[0]);
console.log();
if (allFullOpacity) {
  console.log('❌ BUG: Every layer is 100% opaque — no transparent pixels anywhere.');
} else if (allSameRatio) {
  console.log('❌ BUG: All layers have identical alpha distributions.');
} else {
  console.log('✅ OK: Alpha distributions differ per layer.');
  console.log('   visible ratios:', visRatios.map(v => (v * 100).toFixed(1) + '%').join(', '));
}

// ── minimal PNG decoder (RGBA only) ─────────────────────────────────────────
function decodePngRgba(buf) {
  if (buf[0] !== 0x89 || buf[1] !== 0x50) throw new Error('not PNG');
  let i = 8;
  let width, height, bitDepth, colorType;
  let idatChunks = [];
  while (i < buf.length) {
    const len = buf.readUInt32BE(i); i += 4;
    const type = buf.slice(i, i + 4).toString('ascii'); i += 4;
    const data = buf.slice(i, i + len); i += len;
    i += 4; // crc
    if (type === 'IHDR') {
      width = data.readUInt32BE(0);
      height = data.readUInt32BE(4);
      bitDepth = data[8];
      colorType = data[9];
    } else if (type === 'IDAT') {
      idatChunks.push(data);
    } else if (type === 'IEND') {
      break;
    }
  }
  if (bitDepth !== 8 || colorType !== 6) throw new Error(`unsupported: bitDepth=${bitDepth} colorType=${colorType}`);
  const inflated = zlib.inflateSync(Buffer.concat(idatChunks));
  // un-filter rows
  const rowSize = width * 4 + 1;
  const pixels = Buffer.alloc(width * height * 4);
  let prevRow = Buffer.alloc(width * 4);
  for (let y = 0; y < height; y++) {
    const filter = inflated[y * rowSize];
    const row = inflated.slice(y * rowSize + 1, (y + 1) * rowSize);
    const outRow = Buffer.alloc(width * 4);
    for (let x = 0; x < width * 4; x++) {
      const cur = row[x];
      const left = x >= 4 ? outRow[x - 4] : 0;
      const up = prevRow[x];
      const upLeft = x >= 4 ? prevRow[x - 4] : 0;
      let v;
      switch (filter) {
        case 0: v = cur; break;
        case 1: v = (cur + left) & 0xff; break;
        case 2: v = (cur + up) & 0xff; break;
        case 3: v = (cur + Math.floor((left + up) / 2)) & 0xff; break;
        case 4: {
          const p = left + up - upLeft;
          const pa = Math.abs(p - left), pb = Math.abs(p - up), pc = Math.abs(p - upLeft);
          const pred = pa <= pb && pa <= pc ? left : pb <= pc ? up : upLeft;
          v = (cur + pred) & 0xff;
          break;
        }
        default: throw new Error(`unknown filter ${filter}`);
      }
      outRow[x] = v;
    }
    outRow.copy(pixels, y * width * 4);
    prevRow = outRow;
  }
  const alpha = new Uint8Array(width * height);
  for (let p = 0; p < width * height; p++) alpha[p] = pixels[p * 4 + 3];
  return { width, height, alpha };
}