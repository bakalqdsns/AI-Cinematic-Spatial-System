"""从剧本录入走系统接口，做到一个镜头的归档和渲染。

顺序与界面一致：
解析剧本、抽取人物、补视觉提示词、生成分镜、
场景出图、人物三视图、动作视频、归档、渲染。
不复用旧项目，也不手写人物或场景提示词。
"""
from __future__ import annotations

import base64
import json
import sys
import time
import traceback
from pathlib import Path

import httpx

OUT = Path(r"F:/AICinematicSpatialSystem/backend/test_outputs/script_e2e")
STATE_PATH = OUT / "state.json"
BASE = "http://127.0.0.1:8000"
TIMEOUT = httpx.Timeout(connect=30.0, read=1800.0, write=120.0, pool=30.0)

RAW_SCRIPT = """《纸间行》操场一幕

外景。学校操场 - 白天

纸雕风格的学校操场（paper diorama，papercraft layered paper-cut），红色跑道和白色球场线一层层铺开，纸质的看台、旗杆和树影层层叠叠，操场上没有其他人。

白衣少女（16岁，黑色长发，米色皮肤，一身素白的连衣裙，人物同样是纸雕质感，papercraft layered paper-cut）从画面左侧慢慢走向画面右侧，步伐自然，手臂轻轻摆动。
"""


def log(msg: str) -> None:
    print(msg, flush=True)


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def fail(state: dict, step: str, summary: dict) -> None:
    state["failed_step"] = step
    state["failure"] = summary
    save_state(state)
    log("PIPELINE_FAIL step=" + step)
    log(json.dumps(summary, ensure_ascii=False)[:4000])
    sys.exit(1)


def post(client: httpx.Client, state: dict, step: str, url: str, **kwargs) -> httpx.Response:
    log(f"{step} START {url}")
    t0 = time.time()
    try:
        resp = client.post(url, **kwargs)
        resp.raise_for_status()
    except Exception as exc:
        body = ""
        status = None
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            body = exc.response.text[:4000]
        fail(state, step, {
            "error": type(exc).__name__ + ": " + str(exc)[:1500],
            "status_code": status,
            "body": body,
        })
    log(f"{step} HTTP_OK status={resp.status_code} elapsed={time.time() - t0:.1f}s bytes={len(resp.content)}")
    return resp


def slim(value, limit: int = 180):
    if isinstance(value, dict):
        return {k: slim(v, limit) for k, v in value.items() if k not in {"image", "reference_image", "referenceImage"}}
    if isinstance(value, list):
        return [slim(v, limit) for v in value[:8]]
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + f"...<{len(value)} chars>"
    return value


def image_bytes(raw: str) -> bytes:
    text = (raw or "").strip()
    if text.startswith("data:"):
        text = text.split(",", 1)[1]
    if len(text) < 500 and ("\\" in text or "/" in text or text.lower().endswith(".png")):
        path = Path(text)
        if not path.is_file():
            path = Path(r"F:/AICinematicSpatialSystem/backend/.workspace") / text
        if not path.is_file():
            path = Path(r"F:/AICinematicSpatialSystem/backend/.workspace/projects") / text
        return path.read_bytes()
    return base64.b64decode(text)


def save_image(raw: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(image_bytes(raw))


def as_b64(raw: str) -> str:
    return base64.b64encode(image_bytes(raw)).decode("ascii")


def alpha_stats(path: Path) -> dict:
    from PIL import Image

    im = Image.open(path)
    info = {"path": str(path), "mode": im.mode, "size": list(im.size)}
    if "A" not in im.getbands():
        info["background_transparent"] = False
        return info
    hist = im.getchannel("A").histogram()
    total = im.size[0] * im.size[1]
    info.update({
        "transparent_ratio": round(hist[0] / max(1, total), 3),
        "opaque_pixels": hist[255],
        "background_transparent": hist[0] > total * 0.05,
    })
    return info


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    state = load_state()
    client = httpx.Client(timeout=TIMEOUT)

    try:
        info = client.get("http://127.0.0.1:8188/system_stats", timeout=20.0)
        info.raise_for_status()
        log("COMFY_OK")
    except Exception as exc:
        fail(state, "comfy", {"error": str(exc)})

    if not state.get("settings"):
        resp = post(client, state, "SETTINGS", BASE + "/api/aicss/settings", json={
            "image_mode": "local",
            "local_image_backend": "comfyui",
            "video_mode": "local",
            "video_provider": "comfyui",
            "comfyui_base_url": "http://127.0.0.1:8188",
        })
        data = resp.json()
        state["settings"] = {
            "image_mode": data.get("image_mode"),
            "local_image_backend": data.get("local_image_backend"),
            "video_mode": data.get("video_mode"),
            "video_provider": data.get("video_provider"),
            "comfyui_base_url": data.get("comfyui_base_url"),
        }
        save_state(state)
        log("SETTINGS_OK " + json.dumps(state["settings"], ensure_ascii=False))
    else:
        log("SETTINGS_SKIP " + json.dumps(state["settings"], ensure_ascii=False))

    if not state.get("parse"):
        resp = post(client, state, "PARSE", BASE + "/api/aicss/v2/scripts/parse", json={
            "raw_text": RAW_SCRIPT,
            "language": "chinese",
        })
        data = resp.json()
        script = data.get("script_data") or {}
        state["script_data"] = script
        state["parse"] = {
            "project_id": data.get("project_id"),
            "title": script.get("title"),
            "genre": script.get("genre"),
            "characters": script.get("characters") or [],
            "scenes": script.get("scenes") or [],
            "paragraph_count": len(script.get("story_paragraphs") or []),
        }
        save_state(state)
        log("PARSE_OK " + json.dumps(slim(state["parse"]), ensure_ascii=False))
    else:
        log("PARSE_SKIP " + json.dumps(slim(state["parse"]), ensure_ascii=False))

    project_id = state["parse"].get("project_id")
    if not project_id:
        fail(state, "PARSE", {"error": "parse did not return project_id", "parse": state["parse"]})

    if not state.get("characters"):
        resp = post(client, state, "EXTRACT", BASE + "/api/aicss/v2/scripts/characters/extract", json={
            "raw_text": RAW_SCRIPT,
            "language": "chinese",
            "project_id": project_id,
        })
        extracted = resp.json().get("characters") or []
        parsed = state["parse"].get("characters") or []
        characters = parsed if parsed else extracted
        if not characters:
            fail(state, "EXTRACT", {"error": "no characters", "extracted": slim(extracted)})
        state["characters"] = characters
        save_state(state)
        log("EXTRACT_OK " + json.dumps(slim(characters), ensure_ascii=False))
    else:
        log("EXTRACT_SKIP")

    character = state["characters"][0]
    if not character.get("visual_prompt") and not state.get("visual_prompt"):
        resp = post(
            client, state, "VISUAL",
            BASE + "/api/aicss/v2/scripts/visual-prompt",
            params={
                "character_name": character.get("name") or "小女孩",
                "gender": character.get("gender") or "",
                "age": character.get("age") or "",
                "personality": character.get("personality") or "",
                "genre": state["parse"].get("genre") or "",
                "language": "chinese",
            },
        )
        state["visual_prompt"] = resp.json().get("visual_prompt") or ""
        character["visual_prompt"] = state["visual_prompt"]
        save_state(state)
        log("VISUAL_OK " + state["visual_prompt"][:300])
    else:
        state["visual_prompt"] = character.get("visual_prompt") or state.get("visual_prompt") or ""
        log("VISUAL_SKIP " + str(state["visual_prompt"])[:300])

    scenes = state["parse"].get("scenes") or []
    if not scenes:
        fail(state, "PARSE", {"error": "parse returned no scenes"})
    scene = scenes[0]

    if not state.get("scene_prompt"):
        resp = post(
            client, state, "SCENE_PROMPT",
            BASE + "/api/aicss/v2/scripts/scene-visual-prompt",
            params={
                "location": scene.get("location") or "学校操场",
                "time": scene.get("time") or "Day",
                "atmosphere": scene.get("atmosphere") or "",
                "genre": state["parse"].get("genre") or "",
                "language": "chinese",
            },
        )
        state["scene_prompt"] = resp.json().get("visual_prompt") or ""
        save_state(state)
        log("SCENE_PROMPT_OK " + state["scene_prompt"][:400])
    else:
        log("SCENE_PROMPT_SKIP " + str(state["scene_prompt"])[:400])

    if not state.get("shots"):
        script_data = dict(state.get("script_data") or {})
        script_data["characters"] = state["characters"]
        resp = post(client, state, "SHOTS", BASE + "/api/aicss/v2/scripts/shots", json={
            "script_data": script_data,
            "shots_per_scene": 6,
            "language": "chinese",
            "project_id": project_id,
        })
        data = resp.json()
        shots = data.get("shots") or []
        if not shots:
            fail(state, "SHOTS", {"error": "no shots", "body": slim(data)})
        state["shots"] = shots
        save_state(state)
        log("SHOTS_OK count=" + str(len(shots)) + " first=" + json.dumps(slim(shots[0]), ensure_ascii=False))
    else:
        log("SHOTS_SKIP count=" + str(len(state["shots"])))

    shot = state["shots"][0]
    shot_id = shot.get("id")
    scene_id = shot.get("scene_id") or scene.get("id")
    prompts = shot.get("visual_prompts") or {}
    action_prompt = prompts.get("action_prompt") or ""
    if not shot_id or not action_prompt:
        fail(state, "SHOTS", {"error": "first shot has no id or action_prompt", "shot": slim(shot)})

    if not state.get("scene_asset"):
        resp = post(client, state, "SCENE_ASSET", BASE + "/api/aicss/v2/scripts/scenes/generate-asset", json={
            "scene_id": scene.get("id") or scene_id,
            "location": scene.get("location") or "学校操场",
            "time": scene.get("time") or "Day",
            "atmosphere": scene.get("atmosphere") or "",
            "visual_prompt": state.get("scene_prompt") or "",
            "project_id": project_id,
        })
        data = resp.json()
        frames = data.get("keyframe_images") or {}
        saved = {}
        for name in ("wide", "closeup", "mood"):
            raw = frames.get(name)
            if not raw:
                continue
            path = OUT / f"scene_{name}.png"
            save_image(raw, path)
            saved[name] = str(path)
        if "wide" not in saved:
            fail(state, "SCENE_ASSET", {"error": "no wide keyframe", "keys": list(frames)})
        state["scene_asset"] = {"paths": saved, "visual_prompt": data.get("visual_prompt")}
        save_state(state)
        log("SCENE_ASSET_OK " + json.dumps(slim(state["scene_asset"]), ensure_ascii=False))
    else:
        log("SCENE_ASSET_SKIP")

    if not state.get("three_view"):
        resp = post(client, state, "THREE_VIEW", BASE + "/api/aicss/v2/scripts/characters/generate-three-view", json={
            "character_id": character.get("id"),
            "character_name": character.get("name"),
            "character_gender": character.get("gender") or "",
            "character_age": character.get("age") or "",
            "character_personality": character.get("personality") or "",
            "visual_prompt": state.get("visual_prompt") or "",
            "project_id": project_id,
        })
        data = resp.json()
        views = data.get("three_view_images") or {}
        saved = {}
        for name in ("front", "side", "back"):
            raw = views.get(name)
            if not raw:
                continue
            path = OUT / f"char_{name}.png"
            save_image(raw, path)
            saved[name] = str(path)
        if "front" not in saved:
            fail(state, "THREE_VIEW", {"error": "no front view", "keys": list(views)})
        state["three_view"] = {
            "paths": saved,
            "front_b64": as_b64(views["front"]),
            "back_b64": as_b64(views["back"]) if views.get("back") else None,
            "visual_prompt": data.get("visual_prompt"),
        }
        save_state(state)
        log("THREE_VIEW_OK " + json.dumps({k: v for k, v in state["three_view"].items() if not k.endswith("_b64")}, ensure_ascii=False))
    else:
        log("THREE_VIEW_SKIP")

    if not state.get("motion"):
        body = {
            "shot_id": shot_id,
            "character_id": character.get("id"),
            "character_name": character.get("name"),
            "action_prompt": action_prompt,
            "start_image": state["three_view"]["front_b64"],
            "video_provider": state["settings"]["video_provider"],
            "project_id": project_id,
        }
        if state["three_view"].get("back_b64"):
            body["end_image"] = state["three_view"]["back_b64"]
        resp = post(client, state, "MOTION", BASE + "/api/aicss/v2/scripts/motion/generate", json=body)
        data = resp.json()
        summary = {
            "status": data.get("status"),
            "video_path": data.get("video_path"),
            "frame_count": data.get("frame_count"),
            "segmented_count": len(data.get("segmented_frames") or []),
            "shot_id": shot_id,
            "action_prompt": action_prompt,
        }
        state["motion"] = summary
        save_state(state)
        log("MOTION_HTTP " + json.dumps(summary, ensure_ascii=False))
        if summary["status"] != "done":
            fail(state, "MOTION", {"error": "motion status is not done", "response": summary})
    else:
        log("MOTION_SKIP " + json.dumps(state["motion"], ensure_ascii=False))

    if not state.get("frame_check"):
        motions = Path(r"F:/AICinematicSpatialSystem/backend/.workspace/projects") / project_id / "motions"
        found = sorted(motions.rglob("frame_0001.png")) if motions.is_dir() else []
        if not found:
            fail(state, "MOTION", {"error": "frame_0001.png missing", "motions": str(motions)})
        state["frame_check"] = alpha_stats(found[0])
        save_state(state)
        log("FRAME_OK " + json.dumps(state["frame_check"], ensure_ascii=False))
    else:
        log("FRAME_SKIP")

    if not state.get("archive"):
        resp = post(
            client, state, "ARCHIVE",
            f"{BASE}/api/aicss/v2/projects/{project_id}/shots/{shot_id}/archive",
            params={"scene_id": scene_id},
        )
        data = resp.json()
        state["archive"] = {
            "layerCount": data.get("layerCount"),
            "fileCount": data.get("fileCount"),
            "fileName": data.get("fileName"),
            "meshCount": data.get("meshCount"),
        }
        save_state(state)
        log("ARCHIVE_OK " + json.dumps(state["archive"], ensure_ascii=False))
    else:
        log("ARCHIVE_SKIP")

    if not state.get("render"):
        resp = post(
            client, state, "RENDER",
            f"{BASE}/api/aicss/v2/projects/{project_id}/render-queue",
            json={
                "shotIds": [shot_id],
                "samples": 16,
                "resolution": [960, 540],
                "device": "GPU",
                "fps": 24,
            },
        )
        data = resp.json()
        state["render"] = data
        save_state(state)
        log("RENDER_OK " + json.dumps(slim(data), ensure_ascii=False))
        results = data.get("results") or []
        ok = [r for r in results if r.get("status") == "succeeded" and r.get("outputPath")]
        if not data.get("blenderAvailable") or not ok:
            fail(state, "RENDER", {"error": "render did not succeed", "response": slim(data)})
    else:
        log("RENDER_SKIP")

    if not state.get("midframe"):
        import cv2
        output = None
        for row in (state.get("render") or {}).get("results") or []:
            if row.get("outputPath"):
                output = row["outputPath"]
                break
        if not output:
            fail(state, "MID", {"error": "no render output"})
        dest = OUT / "render_mid.png"
        cap = cv2.VideoCapture(output)
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, n // 2))
        ok, frame = cap.read()
        cap.release()
        if not ok or not cv2.imwrite(str(dest), frame):
            fail(state, "MID", {"error": "could not write mid frame", "output": output})
        state["midframe"] = {"path": str(dest), "frame_index": n // 2, "frame_count": n}
        save_state(state)
        log("MID_OK " + json.dumps(state["midframe"], ensure_ascii=False))

    log("PIPELINE_DONE projectId=" + project_id + " shotId=" + shot_id)
    client.close()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        log("PIPELINE_FAIL step=uncaught")
        traceback.print_exc()
        sys.exit(1)
