"""
Test script for DashScope API - saves images to disk
"""
import requests
import json
import base64
from pathlib import Path
from datetime import datetime

BASE_URL = "http://localhost:8000/api/aicss/v2/scripts"
OUTPUT_DIR = Path(r"F:\AICinematicSpatialSystem\backend\test_outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

def save_b64_image(b64_str: str, filepath: Path):
    """Decode base64 and save to file."""
    if not b64_str:
        return False
    try:
        img_data = base64.b64decode(b64_str)
        filepath.write_bytes(img_data)
        size_kb = len(img_data) / 1024
        print(f"    SAVED {filepath.name} ({size_kb:.1f} KB)")
        return True
    except Exception as e:
        print(f"    ERROR saving {filepath}: {e}")
        return False

# ── Test 1: Parse script ──────────────────────────────────────────────────────
print("=" * 60)
print("Test 1: Parse Script")
print("=" * 60)
script_content = """
EXT. ANCIENT FOREST - DAY
The hero walks through a misty forest. A dragon flies overhead.

INT. DARK CAVE - NIGHT
The hero enters a dark cave. Treasure glimmers in the distance.
"""
try:
    response = requests.post(
        f"{BASE_URL}/parse",
        json={"raw_text": script_content, "language": "english"}
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        # Save normalized script and parsed data
        norm_path = OUTPUT_DIR / f"{timestamp}_normalized.txt"
        norm_path.write_text(result.get("normalized_script", ""), encoding="utf-8")
        data_path = OUTPUT_DIR / f"{timestamp}_script_data.json"
        data_path.write_text(json.dumps(result.get("script_data", {}), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  Saved normalized script -> {norm_path.name}")
        print(f"  Saved script_data       -> {data_path.name}")
    else:
        print(f"  Error: {response.text[:500]}")
except Exception as e:
    print(f"  Error: {e}")

# ── Test 2: Generate character three-view ──────────────────────────────────────
print("\n" + "=" * 60)
print("Test 2: Generate Character Three-View")
print("=" * 60)
try:
    response = requests.post(
        f"{BASE_URL}/characters/generate-three-view",
        json={
            "character_id": "char_hero_001",
            "character_name": "Hero Knight",
            "character_gender": "male",
            "character_personality": "brave and noble, warrior spirit",
            "project_id": "test_project_cloud"
        }
    )
    print(f"Status: {response.status_code}")
    result = response.json()
    if response.status_code == 200 and "three_view_images" in result:
        print(f"  Visual prompt: {result.get('visual_prompt', '')[:120]}...")
        char_dir = OUTPUT_DIR / f"{timestamp}_hero_knight"
        char_dir.mkdir(parents=True, exist_ok=True)
        for view in ("front", "side", "back"):
            img_b64 = result["three_view_images"].get(view)
            if img_b64:
                save_b64_image(img_b64, char_dir / f"{view}.png")
        # Save manifest
        manifest = {
            "character_id": result.get("character_id"),
            "visual_prompt": result.get("visual_prompt"),
            "views": list(result["three_view_images"].keys()),
        }
        (char_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  Saved character asset folder -> {char_dir.name}/")
except Exception as e:
    print(f"  Error: {e}")

# ── Test 3: Generate scene asset ──────────────────────────────────────────────
print("\n" + "=" * 60)
print("Test 3: Generate Scene Asset")
print("=" * 60)
try:
    response = requests.post(
        f"{BASE_URL}/scenes/generate-asset",
        json={
            "scene_id": "scene_forest_001",
            "location": "Ancient Mystic Forest",
            "time": "Day",
            "atmosphere": "foggy, golden sunlight through canopy, mysterious",
            "project_id": "test_project_cloud"
        }
    )
    print(f"Status: {response.status_code}")
    result = response.json()
    if response.status_code == 200 and "keyframe_images" in result:
        print(f"  Visual prompt: {result.get('visual_prompt', '')[:120]}...")
        scene_dir = OUTPUT_DIR / f"{timestamp}_scene_forest"
        scene_dir.mkdir(parents=True, exist_ok=True)
        for key in ("wide", "closeup", "mood"):
            img_b64 = result["keyframe_images"].get(key)
            if img_b64:
                save_b64_image(img_b64, scene_dir / f"{key}.png")
        manifest = {
            "scene_id": result.get("scene_id"),
            "visual_prompt": result.get("visual_prompt"),
            "keyframes": list(result["keyframe_images"].keys()),
        }
        (scene_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  Saved scene asset folder -> {scene_dir.name}/")
except Exception as e:
    print(f"  Error: {e}")

print("\n" + "=" * 60)
print(f"All outputs saved to: {OUTPUT_DIR}")
print("=" * 60)
