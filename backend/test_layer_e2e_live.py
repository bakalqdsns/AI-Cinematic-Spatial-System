"""
E2E Layer Export Test — runs against the live backend (no TestClient).
Loads the test image (f:\\AICinematicSpatialSystem\\test\\背景.png), sends it to
POST /api/aicss/layers/export, and validates the 4-layer RGBA PNG response.

All model modes are forced to "local" via the settings API so no DashScope
API key is needed — DepthAnything runs on CPU/GPU locally.

Usage:
    python test_layer_e2e_live.py [N]
        N  — number of loop iterations (default 3)
"""
from __future__ import annotations

import base64
import io
import hashlib
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

# ── Project root ──────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).parent.resolve()
TEST_IMAGE_PATH = Path(r"F:\AICinematicSpatialSystem\test\背景.png")
OUTPUT_DIR = BACKEND_DIR / "test_outputs" / "layer_e2e_live"
BASE_URL = "http://127.0.0.1:8000"
SETTINGS_URL = f"{BASE_URL}/api/aicss/settings"
LAYERS_URL = f"{BASE_URL}/api/aicss/layers/export"
STATUS_URL = f"{BASE_URL}/api/aicss/models/status"
STARTUP_TIMEOUT = 300   # seconds — first DepthAnything load can be slow
REQUEST_TIMEOUT = 300  # seconds — depth inference on large images

# ── Helpers ───────────────────────────────────────────────────────────────────

def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def eq(actual, expected, label: str) -> bool:
    ok = actual == expected
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {label}: got {actual!r}, expected {expected!r}", flush=True)
    return ok


def ok_(cond, label: str) -> bool:
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {label}", flush=True)
    return bool(cond)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def decode_png_bytes(data_uri: str) -> bytes:
    """Strip data:image/png;base64, prefix and decode base64 to bytes."""
    if "," in data_uri:
        b64 = data_uri.split(",", 1)[1]
    else:
        b64 = data_uri
    return base64.b64decode(b64)


def validate_png_header(data: bytes, label: str) -> tuple[int, int, int]:
    """Return (width, height, color_type) from PNG IHDR. Raises on invalid PNG."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{label}: not a valid PNG (bad signature)")
    import struct
    # IHDR chunk starts at byte 8; length is bytes 8-11 (big-endian)
    length = struct.unpack(">I", data[8:12])[0]
    if length != 13:
        raise ValueError(f"{label}: IHDR length is {length}, expected 13")
    # Chunk type is 4 bytes after length
    chunk_type = data[12:16]
    if chunk_type != b"IHDR":
        raise ValueError(f"{label}: first chunk is {chunk_type!r}, expected b'IHDR'")
    # Width: bytes 16-19, Height: bytes 20-23, bit depth+color type: bytes 24-25
    width = struct.unpack(">I", data[16:20])[0]
    height = struct.unpack(">I", data[20:24])[0]
    color_type = data[25]
    return width, height, color_type


def load_image_as_base64(path: Path) -> str:
    """Return plain base64 string (no data: prefix) — matches frontend pattern."""
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def http_post(url: str, body: dict, timeout: int = 60) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read())


def http_get(url: str, timeout: int = 30) -> tuple[int, dict]:
    req = urllib.request.Request(url, headers={}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read())


def http_patch(url: str, body: dict, timeout: int = 30) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read())


# ── Wait for server ───────────────────────────────────────────────────────────

def wait_for_server(timeout: int = STARTUP_TIMEOUT) -> None:
    log(f"Waiting up to {timeout}s for backend to be ready at {BASE_URL}...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            status, _ = http_get(STATUS_URL, timeout=10)
            log(f"  Backend ready after {time.time() - start:.1f}s (status={status})")
            return
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            elapsed = time.time() - start
            if elapsed < 5:
                log(f"  Not ready yet ({type(e).__name__}: {e}), retrying...")
            time.sleep(5)
    raise RuntimeError(f"Backend did not become ready within {timeout}s")


# ── Configure all-local mode ───────────────────────────────────────────────────

def configure_local_mode() -> None:
    log("Configuring all model modes to 'local'...")
    try:
        status, resp = http_get(SETTINGS_URL)
        log(f"  Current settings: model_mode={resp.get('model_mode')}, "
            f"vlm_mode={resp.get('vlm_mode')}, image_mode={resp.get('image_mode')}, "
            f"video_mode={resp.get('video_mode')}")
    except Exception as e:
        log(f"  Warning: could not read settings: {e}")

    try:
        status, resp = http_post(
            SETTINGS_URL,
            {
                "model_mode": "local",
                "vlm_mode": "local",
                "image_mode": "local",
                "video_mode": "local",
            },
        )
        log(f"  Settings updated: model_mode={resp.get('model_mode')}")
    except Exception as e:
        log(f"  Warning: could not patch settings: {e}")


# ── Core test ─────────────────────────────────────────────────────────────────

def run_layer_export_test(image_b64: str, iteration: int) -> bool:
    log(f"\n{'='*60}")
    log(f"  Layer Export E2E Test — iteration {iteration}")
    log(f"{'='*60}")

    passed = 0
    failed = 0

    # ── 1. Happy path: plain base64 input ────────────────────────────────────
    log("\n[Test 1] Plain base64 input")
    try:
        status, resp = http_post(
            LAYERS_URL,
            {"imageUrl": image_b64, "featherPx": 1},
            timeout=REQUEST_TIMEOUT,
        )
    except Exception as e:
        log(f"  [FAIL] Request raised: {type(e).__name__}: {e}")
        failed += 1
        return False

    if not eq(status, 200, "HTTP 200"):
        failed += 1
        return False
    passed += 1

    layers = resp.get("layers", {})
    z_offsets = resp.get("zOffsets", [])
    w, h = resp.get("width"), resp.get("height")

    # Basic envelope
    if not eq(isinstance(layers, dict) and len(layers) == 4, True, "4 layers returned"):
        failed += 1
        return False
    passed += 1

    if not eq(len(z_offsets), 4, "4 zOffset entries"):
        failed += 1
        return False
    passed += 1

    if not ok_(w and h and w > 0 and h > 0, f"Valid dimensions: {w}x{h}"):
        failed += 1
        return False
    passed += 1

    # ── 2. Validate RGBA PNG for each layer ───────────────────────────────────
    log("\n[Test 2] Layer PNG validation")
    layer_names = ["sky", "background", "midground", "foreground"]
    sha256s = []

    for name in layer_names:
        uri = layers.get(name, {}).get("dataUri", "")
        if not ok_(uri and uri.startswith("data:image"), f"{name}: has data URI"):
            failed += 1
            sha256s.append(None)
            continue
        passed += 1

        try:
            raw = decode_png_bytes(uri)
            pw, ph, ct = validate_png_header(raw, name)
            if not eq(ct, 6, f"{name}: color_type == 6 (RGBA)"):
                failed += 1
            else:
                passed += 1
            if not eq(pw, w, f"{name}: PNG width matches response width"):
                failed += 1
            else:
                passed += 1
            if not eq(ph, h, f"{name}: PNG height matches response height"):
                failed += 1
            else:
                passed += 1
            log(f"  [OK] {name}: {pw}x{ph} RGBA PNG ({len(raw)//1024} KB)")
            sha256s.append(sha256_bytes(raw))
        except Exception as e:
            log(f"  [FAIL] {name}: PNG decode error: {type(e).__name__}: {e}")
            failed += 1
            sha256s.append(None)

    # ── 3. Z-offset table ─────────────────────────────────────────────────────
    log("\n[Test 3] Z-offset table")
    expected_z = {
        "sky": {"zOffset": -20.0, "zMin": 50.0, "zMax": 9999.0},
        "background": {"zOffset": -12.0, "zMin": 15.0, "zMax": 50.0},
        "midground": {"zOffset": -6.0, "zMin": 5.0, "zMax": 15.0},
        "foreground": {"zOffset": -2.0, "zMin": 0.0, "zMax": 5.0},
    }
    z_lookup = {entry["layer"]: entry for entry in z_offsets}

    for name, exp in expected_z.items():
        entry = z_lookup.get(name, {})
        for key, val in exp.items():
            if not eq(entry.get(key), val, f"{name}.{key} == {val}"):
                failed += 1
            else:
                passed += 1

    # ── 4. 4 layers must be byte-distinct (SHA256 uniqueness) ─────────────────
    log("\n[Test 4] 4-layer SHA256 uniqueness (depth bucketing regression guard)")
    valid_shas = [s for s in sha256s if s]
    unique_shas = set(valid_shas)
    if not eq(len(unique_shas), 4, f"4 unique SHA256s (got {len(unique_shas)})"):
        log(f"  Layer SHAs: {dict(zip(layer_names, sha256s))}")
        failed += 1
    else:
        passed += 1
        log(f"  Layer SHAs: {dict(zip(layer_names, sha256s))}")

    # ── 5. Save layer PNGs to disk ────────────────────────────────────────────
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in layer_names:
        uri = layers.get(name, {}).get("dataUri", "")
        if uri:
            raw = decode_png_bytes(uri)
            out_path = OUTPUT_DIR / f"iter{iteration:02d}_{name}.png"
            out_path.write_bytes(raw)
            sha = sha256s[layer_names.index(name)]
            log(f"  Saved {out_path.name} (" + str(len(raw)//1024) + f" KB, SHA256={sha})")

    # ── Summary ───────────────────────────────────────────────────────────────
    total = passed + failed
    log(f"\n  Iteration {iteration} — {passed}/{total} checks passed", )
    return failed == 0


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> None:
    n_iterations = int(sys.argv[1]) if len(sys.argv) > 1 else 3

    # Verify test image exists
    if not TEST_IMAGE_PATH.exists():
        log(f"FATAL: Test image not found: {TEST_IMAGE_PATH}")
        sys.exit(1)
    log(f"Test image: {TEST_IMAGE_PATH} ({TEST_IMAGE_PATH.stat().st_size // 1024} KB)")

    # Load image once
    image_b64 = load_image_as_base64(TEST_IMAGE_PATH)
    log(f"Image loaded as base64 ({len(image_b64)} chars)")

    # Wait for backend
    wait_for_server()

    # Configure local mode
    configure_local_mode()

    # Run test loop
    all_passed = True
    for i in range(1, n_iterations + 1):
        ok = run_layer_export_test(image_b64, i)
        if not ok:
            all_passed = False
        if i < n_iterations:
            log(f"\nWaiting 3s before next iteration...")
            time.sleep(3)

    # Final report
    log(f"\n{'='*60}")
    if all_passed:
        log(f"  ALL {n_iterations} ITERATION(S) PASSED")
        log(f"{'='*60}")
        sys.exit(0)
    else:
        log(f"  SOME ITERATION(S) FAILED — see above for details")
        log(f"{'='*60}")
        sys.exit(1)


if __name__ == "__main__":
    main()
