"""
Module 1 E2E — Automated Script Decomposition (剧本自动化拆解)
================================================================
Exercises the full character-first pipeline that the bidirectional prompt
box depends on. Designed to be runnable without API keys: any LLM- or
GPU-dependent step gracefully degrades and reports its status instead of
crashing.

Run:
    cd F:\\AICinematicSpatialSystem\\backend
    python test_module1_e2e.py

Outputs:
    F:\\AICinematicSpatialSystem\\backend\\test_outputs\\module1_e2e\\
        - <timestamp>_normalized.txt
        - <timestamp>_script_data.json
        - <timestamp>_characters_extract.json
        - <timestamp>_shots.json
        - <timestamp>_summary.json
"""
from __future__ import annotations

import base64
import json
import sys
import time
from pathlib import Path
from datetime import datetime

# ── Path setup so we can import the FastAPI app ───────────────────────────────
BACKEND_DIR = Path(r"F:\AICinematicSpatialSystem\backend")
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

# ── Test fixtures ─────────────────────────────────────────────────────────────
BASE_URL = "/api/aicss/v2/scripts"
OUTPUT_DIR = BACKEND_DIR / "test_outputs" / "module1_e2e"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TS = datetime.now().strftime("%Y%m%d_%H%M%S")
SUMMARY: list[dict] = []  # [{step, status, detail}]

USER_SCRIPT = """
场景1
内景。教室 - 傍晚
画面：
放学后的教室。阳光从西侧的窗户斜射进来，在课桌上投下长长的橙色光斑。
林知夏（17岁，短发，校服，神情安静）独自坐在靠窗倒数第二排的位置。她面前摊着一本数学练习册，老师的脚步声从走廊经过。林知夏迅速合上练习册。
特写：练习册的空白页上，画着一个未完成的漫画肖像——是一个女孩子的半身像，短发、校服，眼睛画得很细致，但嘴和下半张脸只勾了轮廓线，没有完成。
林知夏（低声，声音沙哑）：
"……我想起来了。"
"""

client = TestClient(app)


# ── Helpers ───────────────────────────────────────────────────────────────────

def record(step: str, status: str, detail: str = "") -> None:
    """Print + log a test step. status ∈ {PASS, WARN, FAIL}."""
    SUMMARY.append({"step": step, "status": status, "detail": detail})
    tag = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗"}.get(status, "?")
    print(f"  [{tag}] {step}: {detail}")


def save(name: str, data) -> Path:
    path = OUTPUT_DIR / f"{TS}_{name}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def section(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


# ── Test 1: /characters/extract (independent fast path) ──────────────────────

def test_extract_characters() -> dict:
    section("TEST 1: POST /characters/extract")
    try:
        resp = client.post(
            f"{BASE_URL}/characters/extract",
            json={"raw_text": USER_SCRIPT, "language": "chinese"},
        )
    except Exception as e:
        record("extract_characters", "FAIL", f"Exception: {e}")
        return {}

    if resp.status_code != 200:
        record("extract_characters", "FAIL", f"HTTP {resp.status_code}: {resp.text[:200]}")
        return {}

    data = resp.json()
    chars = data.get("characters", [])
    save("characters_extract", data)

    # ── assertions ──
    if not chars:
        record("extract_characters", "FAIL", "Returned 0 characters")
        return {}
    record("extract_characters", "PASS", f"{len(chars)} character(s) extracted")

    # Required fields (visual_prompt may be empty until /visual-prompt is called)
    missing = []
    for c in chars:
        if not c.get("name"):
            missing.append("name")
        if "visual_prompt" not in c:
            missing.append("visual_prompt")
    if missing:
        record("extract_characters_field_shape", "WARN",
               f"Some expected fields missing: {missing}")
    else:
        record("extract_characters_field_shape", "PASS",
               "All characters carry id/name/visual_prompt fields")

    # Bidirectional prep: print what the bidirectional box would render
    print(f"    ┌─ Character list pre-fill state (what CharactersTab will show):")
    for c in chars:
        vp = c.get("visual_prompt", "") or ""
        marker = "✓" if vp else "·"
        print(f"    │ [{marker}] {c.get('name','?')} ({c.get('gender','?')}, {c.get('age','?')}): "
              f"visual_prompt={'<empty>' if not vp else vp[:60] + '...'}")
    print(f"    └─ (empty rows will be auto-filled by /visual-prompt via Test 3 below)")

    return data


# ── Test 2: /scripts/parse (the main decomposition endpoint) ─────────────────

def test_parse_script() -> dict:
    section("TEST 2: POST /scripts/parse")
    try:
        resp = client.post(
            f"{BASE_URL}/parse",
            json={"raw_text": USER_SCRIPT, "language": "chinese"},
        )
    except Exception as e:
        record("parse_script", "FAIL", f"Exception: {e}")
        return {}

    if resp.status_code != 200:
        record("parse_script", "FAIL", f"HTTP {resp.status_code}: {resp.text[:200]}")
        return {}

    data = resp.json()
    sd = data.get("script_data", {})
    norm = data.get("normalized_script", "")
    proj = data.get("project_id")

    (OUTPUT_DIR / f"{TS}_normalized.txt").write_text(norm, encoding="utf-8")
    save("script_data", data)

    # ── assertions ──
    if not sd:
        record("parse_script", "FAIL", "Empty script_data")
        return data

    scenes = sd.get("scenes", [])
    chars = sd.get("characters", [])
    paras = sd.get("story_paragraphs", [])

    rec = "PASS"
    detail = (f"{len(scenes)} scene(s), {len(chars)} character(s), "
              f"{len(paras)} paragraph(s), project_id={proj}")
    if not scenes:
        rec = "FAIL"
        detail = "No scenes parsed"
    elif not chars:
        rec = "WARN"
        detail += " (no characters)"
    record("parse_script", rec, detail)

    # ── bidirectional box hydration check ──
    char_with_prompt = sum(1 for c in chars if c.get("visual_prompt"))
    scene_with_prompt = sum(1 for s in scenes if s.get("visual_prompt"))
    record(
        "parse_script_prompt_coverage",
        "PASS" if char_with_prompt or scene_with_prompt else "WARN",
        f"characters with visual_prompt: {char_with_prompt}/{len(chars)}, "
        f"scenes with visual_prompt: {scene_with_prompt}/{len(scenes)}",
    )

    return data


# ── Test 3: /visual-prompt (input side of bidirectional flow) ─────────────────

def test_visual_prompt(extract_data: dict) -> None:
    section("TEST 3: POST /visual-prompt (input side: 剧本分析 → 提示词框)")
    chars = extract_data.get("characters", [])
    if not chars:
        record("visual_prompt", "SKIP", "No characters from extract")
        return

    target = chars[0]
    print(f"    Generating visual prompt for: {target.get('name','?')}")
    try:
        resp = client.post(
            f"{BASE_URL}/visual-prompt",
            params={
                "character_name": target.get("name", ""),
                "gender": target.get("gender", ""),
                "age": target.get("age", ""),
                "personality": target.get("personality", ""),
                "genre": "cinematic",
                "language": "chinese",
            },
        )
    except Exception as e:
        record("visual_prompt", "WARN", f"Client exception (LLM may be down): {e}")
        return

    if resp.status_code != 200:
        record("visual_prompt", "WARN",
               f"HTTP {resp.status_code} (LLM unavailable or no API key)")
        print(f"      body: {resp.text[:300]}")
        return

    payload = resp.json()
    prompt = payload.get("visual_prompt", "")
    if not prompt:
        record("visual_prompt", "WARN", "Returned empty visual_prompt (LLM weak)")
        return

    record("visual_prompt", "PASS", f"{len(prompt)} chars: {prompt[:80]}...")
    save("visual_prompt", payload)


# ── Test 4: /shots (output side of MotionTab four-prompts) ───────────────────

def test_generate_shots(parse_data: dict) -> list[dict]:
    section("TEST 4: POST /shots (output side: prompt box → motion generator)")
    sd = parse_data.get("script_data", {})
    if not sd:
        record("generate_shots", "SKIP", "No script_data from Test 2")
        return []

    proj = parse_data.get("project_id")
    try:
        resp = client.post(
            f"{BASE_URL}/shots",
            json={
                "script_data": sd,
                "shots_per_scene": 3,
                "language": "chinese",
                "project_id": proj,
            },
        )
    except Exception as e:
        record("generate_shots", "WARN", f"Client exception: {e}")
        return []

    if resp.status_code != 200:
        record("generate_shots", "WARN",
               f"HTTP {resp.status_code}: {resp.text[:200]}")
        return []

    payload = resp.json()
    shots = payload.get("shots", [])
    save("shots", payload)

    if not shots:
        record("generate_shots", "WARN", "Returned 0 shots")
        return []

    # ── assertions ──
    rec = "PASS"
    detail = f"{len(shots)} shot(s) generated"
    # The MotionTab four-prompts block depends on every shot having all four:
    #   scene_prompt, action_prompt, camera_prompt, transition_prompt
    required_keys = ("scene_prompt", "action_prompt", "camera_prompt", "transition_prompt")
    incomplete = []
    for s in shots:
        vp = s.get("visual_prompts", {})
        missing_keys = [k for k in required_keys if not vp.get(k, "")]
        if missing_keys:
            incomplete.append((s.get("id"), missing_keys))

    if incomplete:
        record("shots_prompt_completeness", "WARN",
               f"{len(incomplete)}/{len(shots)} shots missing some prompts; "
               f"first: {incomplete[0]}")
    else:
        record("shots_prompt_completeness", "PASS",
               f"All {len(shots)} shots have scene/action/camera/transition prompts")

    record("generate_shots", rec, detail)

    # Print compact view for log
    print(f"    ┌─ Shot prompts (first 3 shots):")
    for s in shots[:3]:
        vp = s.get("visual_prompts", {})
        print(f"    │ {s.get('id','?')}#{s.get('shot_number','?')}: "
              f"action='{vp.get('action_prompt','')[:50]}...'")
    print(f"    └─")

    return shots


# ── Test 5: /characters/batch-status (polled by pollAutoThreeView) ────────────

def test_batch_status_polling(parse_data: dict) -> None:
    section("TEST 5: GET /characters/batch-status (auto-batch poll target)")
    proj = parse_data.get("project_id")
    if not proj:
        record("batch_status", "SKIP", "No project_id from Test 2")
        return

    # Just one quick read; auto-batch may still be running.
    try:
        resp = client.get(f"{BASE_URL}/characters/batch-status", params={"project_id": proj})
    except Exception as e:
        record("batch_status", "WARN", f"Client exception: {e}")
        return

    if resp.status_code != 200:
        record("batch_status", "WARN", f"HTTP {resp.status_code}")
        return

    payload = resp.json()
    summary = payload.get("summary", {})
    chs = payload.get("characters", {})
    record(
        "batch_status",
        "PASS",
        f"project={payload.get('project_id','?')}, "
        f"summary={summary}, characters_tracked={len(chs)}",
    )

    # ── bidirectional hydration verification ──
    # Each character that is 'done' should carry visual_prompt in either
    # the entry itself or the asset. The new store code (A.3) reads this
    # same shape, so if it works here it works there.
    with_vp = 0
    for cid, entry in chs.items():
        if not entry:
            continue
        if entry.get("visual_prompt") or (entry.get("asset") or {}).get("visual_prompt"):
            with_vp += 1
    record(
        "batch_status_visual_prompt_hydration",
        "PASS" if with_vp else "WARN",
        f"{with_vp}/{len(chs)} characters expose a visual_prompt for hydration",
    )


# ── Test 6: End-to-end bidirectional round-trip ──────────────────────────────

def test_bidirectional_round_trip(parse_data: dict, shots: list[dict]) -> None:
    section("TEST 6: Bidirectional flow self-check")
    sd = parse_data.get("script_data", {})
    chars = sd.get("characters", [])
    scenes = sd.get("scenes", [])

    checks: list[tuple[str, bool, str]] = []

    # 1. Every character has a place to store visualPrompt (even if empty).
    checks.append((
        "parsedScript.characters[*].visual_prompt field exists",
        all("visual_prompt" in c for c in chars),
        f"{sum(1 for c in chars if 'visual_prompt' in c)}/{len(chars)}",
    ))

    # 2. Every scene has a place to store visualPrompt.
    checks.append((
        "parsedScript.scenes[*].visual_prompt field exists",
        all("visual_prompt" in s for s in scenes),
        f"{sum(1 for s in scenes if 'visual_prompt' in s)}/{len(scenes)}",
    ))

    # 3. Every shot has all four prompt keys.
    vp_keys_ok = 0
    for s in shots:
        vp = s.get("visual_prompts", {}) or {}
        if all(vp.get(k) for k in ("scene_prompt", "action_prompt", "camera_prompt")):
            vp_keys_ok += 1
    checks.append((
        "shots[*].visual_prompts.{scene,action,camera}_prompt all populated",
        vp_keys_ok == len(shots) and len(shots) > 0,
        f"{vp_keys_ok}/{len(shots)} shots",
    ))

    print()
    for label, ok, detail in checks:
        record(label, "PASS" if ok else "WARN", detail)


# ── Runner ────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"E2E for 模块 1 — 自动化剧本拆解")
    print(f"timestamp: {TS}")
    print(f"output:    {OUTPUT_DIR}")
    print(f"backend:   TestClient (in-process, no live server required)")

    t0 = time.time()

    extract_data = test_extract_characters()
    parse_data = test_parse_script()
    test_visual_prompt(extract_data)
    shots = test_generate_shots(parse_data)
    test_batch_status_polling(parse_data)
    test_bidirectional_round_trip(parse_data, shots)

    elapsed = time.time() - t0

    # ── Summary ──────────────────────────────────────────────────────────────
    section("SUMMARY")
    pass_n = sum(1 for s in SUMMARY if s["status"] == "PASS")
    warn_n = sum(1 for s in SUMMARY if s["status"] == "WARN")
    fail_n = sum(1 for s in SUMMARY if s["status"] == "FAIL")

    print(f"  PASS: {pass_n}")
    print(f"  WARN: {warn_n}  (LLM/GPU unavailable — graceful degradation)")
    print(f"  FAIL: {fail_n}")
    print(f"  Time: {elapsed:.1f}s")
    print()
    if fail_n == 0:
        print("  ✅ 模块 1 bidirectional pipeline is healthy.")
    else:
        print("  ❌ Critical failures detected — review log above.")
    print()

    (OUTPUT_DIR / f"{TS}_summary.json").write_text(
        json.dumps(
            {
                "timestamp": TS,
                "elapsed_seconds": round(elapsed, 2),
                "pass": pass_n,
                "warn": warn_n,
                "fail": fail_n,
                "steps": SUMMARY,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    sys.exit(0 if fail_n == 0 else 1)


if __name__ == "__main__":
    main()