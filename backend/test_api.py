"""
Test script for DashScope API integration - Detailed version
"""
import requests
import json

BASE_URL = "http://localhost:8000/api/aicss/v2/scripts"

# Test 1: Parse script
print("=" * 60)
print("Test 1: Parse Script")
print("=" * 60)
script_content = """
[Scene 1] Exterior - Ancient Forest - Day
The hero walks through a misty forest. A dragon flies overhead.

[Scene 2] Interior - Dark Cave - Night
The hero enters a dark cave. Treasure glimmers in the distance.
"""
try:
    response = requests.post(
        f"{BASE_URL}/parse",
        json={"raw_text": script_content, "language": "chinese"}
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"Success! Keys: {result.keys()}")
        print(f"Normalized script preview: {result.get('normalized_script', '')[:200]}...")
    else:
        print(f"Error: {response.text[:800]}")
except Exception as e:
    print(f"Error: {e}")

# Test 2: Generate character three-view
print("\n" + "=" * 60)
print("Test 2: Generate Character Three-View")
print("=" * 60)
try:
    response = requests.post(
        f"{BASE_URL}/characters/generate-three-view",
        json={
            "character_id": "char_001",
            "character_name": "Hero Knight",
            "character_gender": "male",
            "character_personality": "brave and noble",
            "project_id": "test_project_001"
        }
    )
    print(f"Status: {response.status_code}")
    result = response.json()
    print(f"Result keys: {result.keys()}")
    if "three_view_images" in result:
        images = result["three_view_images"]
        print(f"Generated views: {list(images.keys())}")
        for view, img in images.items():
            if img:
                print(f"  {view}: {img[:80]}...")
            else:
                print(f"  {view}: None (FAILED)")
    if "error" in result:
        print(f"Error: {result['error']}")
    if "detail" in result:
        print(f"Detail: {result['detail']}")
    print(f"\nFull response preview: {json.dumps(result, indent=2)[:500]}")
except Exception as e:
    print(f"Error: {e}")

# Test 3: Generate scene asset
print("\n" + "=" * 60)
print("Test 3: Generate Scene Asset")
print("=" * 60)
try:
    response = requests.post(
        f"{BASE_URL}/scenes/generate-asset",
        json={
            "scene_id": "scene_001",
            "location": "Ancient Forest",
            "time": "Day",
            "atmosphere": "misty, mystical",
            "project_id": "test_project_001"
        }
    )
    print(f"Status: {response.status_code}")
    result = response.json()
    print(f"Result keys: {result.keys()}")
    if "keyframe_images" in result:
        images = result["keyframe_images"]
        print(f"Generated keyframes: {list(images.keys())}")
        for key, img in images.items():
            if img:
                print(f"  {key}: {img[:80]}...")
            else:
                print(f"  {key}: None (FAILED)")
    if "error" in result:
        print(f"Error: {result['error']}")
    if "detail" in result:
        print(f"Detail: {result['detail']}")
except Exception as e:
    print(f"Error: {e}")

print("\n" + "=" * 60)
print("Tests completed")
print("=" * 60)
