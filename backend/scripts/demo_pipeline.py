#!/usr/bin/env python3
"""
E2E demo: script text -> playable MP4.

Drives the full AICSS pre-production -> render -> compose pipeline through
the v2 HTTP API. Each step is checkpointed to
``backend/.workspace/projects/<pid>/pipeline_state.json`` so an interrupted
run can be resumed with ``--resume <project_id>``.

Pipeline:
  parse -> shots -> characters(generate-three-view) -> scenes(generate-asset)
    -> motion(generate) -> archive -> render-queue -> compose

Usage:
  python scripts/demo_pipeline.py --script "剧本文本" --output out.mp4
  python scripts/demo_pipeline.py --script-file 剧本.txt --output out.mp4
  python scripts/demo_pipeline.py --resume <project_id> --output out.mp4
  python scripts/demo_pipeline.py --help

Notes:
  - Only depends on the Python standard library + ``requests``
    (already in backend/requirements.txt).
  - Never imports ``app.main`` (would pull in torch). Talks to the API
    over HTTP only.
  - Start the backend first: ``python backend/run.py`` (default port 8000).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Optional

# Resolve backend root (this file lives at backend/scripts/demo_pipeline.py).
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_WORKSPACE_DIR = _BACKEND_ROOT / ".workspace" / "projects"

STEPS = ["parse", "shots", "characters", "scenes", "motion", "archive", "render", "compose"]

STEP_TIMEOUTS = {
    "parse": 300, "shots": 300, "characters": 600, "scenes": 600,
    "motion": 1800, "archive": 300, "render": 1800, "compose": 600,
}

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8000
DEFAULT_LANGUAGE = "chinese"
DEFAULT_SHOTS_PER_SCENE = 3
DEFAULT_TRANSITION = "dissolve"
DEFAULT_TRANSITION_DURATION = 0.5
DEFAULT_POLL_INTERVAL = 5.0
DEFAULT_POLL_MAX = 240
DEFAULT_VIDEO_PROVIDER = "dashscope"
DEFAULT_RENDER_SAMPLES = 32
DEFAULT_RENDER_DEVICE = "GPU"
DEFAULT_RENDER_FPS = 24


# --- Helpers ---------------------------------------------------------------

def _log(msg: str) -> None:
    print(msg, flush=True)


def _step_done(idx: int, total: int, name: str, extra: str = "") -> None:
    suffix = f" -- {extra}" if extra else ""
    _log(f"[{idx}/{total}] {name}...done{suffix}")


def _state_path(project_id: str) -> Path:
    return _WORKSPACE_DIR / project_id / "pipeline_state.json"


def _load_state(project_id: str) -> dict:
    p = _state_path(project_id)
    if not p.is_file():
        raise FileNotFoundError(
            f"No pipeline state for project {project_id} at {p}. "
            f"Cannot resume -- start a fresh run without --resume."
        )
    return json.loads(p.read_text(encoding="utf-8"))


def _save_state(project_id: str, state: dict) -> None:
    p = _state_path(project_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


class PipelineError(RuntimeError):
    """Raised when a pipeline step fails. Carries the step name for resume hint."""

    def __init__(self, step: str, project_id: Optional[str], message: str):
        self.step = step
        self.project_id = project_id
        resume_hint = (
            f"  -> resume with: python scripts/demo_pipeline.py "
            f"--resume {project_id} --output <out.mp4>"
            if project_id
            else "  (no project_id yet -- cannot resume, restart from scratch)"
        )
        super().__init__(f"[step={step}] {message}\n{resume_hint}")


# --- HTTP client wrapper ---------------------------------------------------

class Client:
    """Thin wrapper over urllib.request with base URL + timeouts.

    Uses only the Python standard library so the script runs even when
    ``requests`` / ``httpx`` are not installed in the active environment.
    """

    def __init__(self, host: str, port: int, timeout: int):
        self.base = f"http://{host}:{port}/api/aicss/v2"
        self.health_base = f"http://{host}:{port}"
        self.timeout = timeout
        import urllib.request
        self._urllib = urllib.request

    def _request(self, method: str, url: str, body: Any = None,
                 params: Optional[dict] = None, timeout: Optional[int] = None) -> dict:
        from urllib.parse import urlencode, quote, urlsplit, urlunsplit
        full = url
        if params:
            qs = urlencode({k: v for k, v in params.items() if v is not None})
            if qs:
                full = f"{url}?{qs}"
        # 对含非 ASCII（如中文 project_id）的 URL 做百分号编码
        if any(ord(c) > 127 for c in full):
            sp = urlsplit(full)
            sp = sp._replace(path=quote(sp.path, safe="/%"),
                             query=quote(sp.query, safe="=&%"))
            full = urlunsplit(sp)
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = self._urllib.Request(full, data=data, headers=headers, method=method)
        try:
            with self._urllib.urlopen(req, timeout=timeout or self.timeout) as resp:
                raw = resp.read()
                status = resp.getcode()
        except self._urllib.URLError as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, ConnectionRefusedError) or "Connection refused" in str(reason):
                raise PipelineError(
                    "<unknown>", None,
                    f"Cannot reach backend at {full}.\n"
                    f"  Underlying error: {reason}\n"
                    f"  Start the backend first:  python backend/run.py",
                )
            raise PipelineError("<unknown>", None, f"Cannot reach {full}: {reason}")
        except Exception as exc:
            raise PipelineError("<unknown>", None, f"Request failed: {exc}")
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            payload = {"raw": raw.decode("utf-8", errors="replace")[:500]}
        if status >= 400:
            detail = payload.get("detail") if isinstance(payload, dict) else str(payload)
            raise PipelineError("<unknown>", None, f"HTTP {status}: {detail}")
        return payload

    def health(self) -> bool:
        try:
            with self._urllib.urlopen(f"{self.health_base}/health", timeout=10) as resp:
                return resp.getcode() == 200
        except Exception:
            return False

    def post(self, path: str, body: Any, timeout: Optional[int] = None,
             params: Optional[dict] = None) -> dict:
        return self._request("POST", self.base + path, body=body,
                             params=params, timeout=timeout)

    def get(self, path: str, params: Optional[dict] = None,
             timeout: Optional[int] = None) -> dict:
        return self._request("GET", self.base + path, params=params, timeout=timeout)


# --- Pipeline steps --------------------------------------------------------

def step_parse(client: Client, raw_text: str, language: str,
               project_id: Optional[str]) -> dict:
    """POST /scripts/parse -> {project_id, script_data, normalized_script}."""
    body = {"raw_text": raw_text, "language": language}
    if project_id:
        body["project_id"] = project_id
    resp = client.post("/scripts/parse", body, timeout=STEP_TIMEOUTS["parse"])
    pid = resp.get("project_id") or project_id
    if not pid:
        raise PipelineError("parse", None, "parse response missing project_id")
    return {
        "project_id": pid,
        "script_data": resp.get("script_data") or {},
        "normalized_script": resp.get("normalized_script") or "",
    }


def step_shots(client: Client, project_id: str, script_data: dict,
               language: str, shots_per_scene: int) -> list:
    """POST /scripts/shots -> shots list."""
    body = {
        "script_data": script_data,
        "shots_per_scene": shots_per_scene,
        "project_id": project_id,
    }
    if language:
        body["language"] = language
    resp = client.post("/scripts/shots", body, timeout=STEP_TIMEOUTS["shots"])
    shots = resp.get("shots") or []
    if not shots:
        raise PipelineError("shots", project_id, "no shots returned by /scripts/shots")
    return shots


def _poll_batch(client: Client, project_id: str, kind: str,
                poll_interval: float, poll_max: int) -> dict:
    """Poll batch-status until all entries terminal (done|failed) or max hit."""
    path = f"/scripts/{kind}/batch-status"
    last = {}
    for _ in range(poll_max):
        status = client.get(path, params={"project_id": project_id})
        last = status
        key = "characters" if kind == "characters" else "scenes"
        entries = status.get(key) or {}
        if not entries:
            time.sleep(poll_interval)
            continue
        if all(e.get("status") in ("done", "failed") for e in entries.values()):
            return status
        time.sleep(poll_interval)
    return last


def step_characters(client: Client, project_id: str, script_data: dict,
                    poll_interval: float, poll_max: int) -> dict:
    """Ensure every character has a three-view asset.

    /scripts/parse auto-kicks off an auto-batch, so we poll batch-status
    first. Any character that ends up `failed` or never queued is retried
    manually via /characters/generate-three-view.
    """
    characters = script_data.get("characters") or []
    if not characters:
        _log("  (no characters in script -- skipping three-view)")
        return {"characters": {}, "summary": {}}

    _log(f"  polling batch-status for {len(characters)} character(s)...")
    status = _poll_batch(client, project_id, "characters", poll_interval, poll_max)
    entries = status.get("characters") or {}

    for c in characters:
        cid = c.get("id") or c.get("character_id") or ""
        if not cid:
            continue
        st = (entries.get(cid) or {}).get("status")
        if st == "done":
            continue
        _log(f"  character {cid} status={st!r} -- retrying via generate-three-view")
        body = {
            "character_id": cid,
            "character_name": c.get("name") or cid,
            "character_gender": c.get("gender", ""),
            "character_age": c.get("age", ""),
            "character_personality": c.get("personality", ""),
            "visual_prompt": c.get("visual_prompt") or None,
            "project_id": project_id,
        }
        try:
            client.post("/scripts/characters/generate-three-view",
                        body, timeout=STEP_TIMEOUTS["characters"])
        except PipelineError as exc:
            _log(f"  ! manual three-view for {cid} failed: {exc}")
    return _poll_batch(client, project_id, "characters", poll_interval, poll_max)


def step_scenes(client: Client, project_id: str, script_data: dict,
                poll_interval: float, poll_max: int) -> dict:
    """Same pattern as step_characters but for scene keyframe assets."""
    scenes = script_data.get("scenes") or []
    if not scenes:
        _log("  (no scenes in script -- skipping scene-asset)")
        return {"scenes": {}, "summary": {}}

    _log(f"  polling batch-status for {len(scenes)} scene(s)...")
    status = _poll_batch(client, project_id, "scenes", poll_interval, poll_max)
    entries = status.get("scenes") or {}

    for s in scenes:
        sid = s.get("id") or ""
        if not sid:
            continue
        st = (entries.get(sid) or {}).get("status")
        if st == "done":
            continue
        _log(f"  scene {sid} status={st!r} -- retrying via generate-asset")
        body = {
            "scene_id": sid,
            "location": s.get("location", ""),
            "time": s.get("time", "Day"),
            "atmosphere": s.get("atmosphere", ""),
            "visual_prompt": s.get("visual_prompt") or None,
            "project_id": project_id,
        }
        try:
            client.post("/scripts/scenes/generate-asset",
                        body, timeout=STEP_TIMEOUTS["scenes"])
        except PipelineError as exc:
            _log(f"  ! manual scene-asset for {sid} failed: {exc}")
    return _poll_batch(client, project_id, "scenes", poll_interval, poll_max)


def _character_name_map(script_data: dict) -> dict:
    return {
        (c.get("id") or c.get("character_id") or ""): (c.get("name") or "")
        for c in (script_data.get("characters") or [])
    }


def step_motion(client: Client, project_id: str, shots: list,
                script_data: dict, video_provider: str) -> list:
    """For every (shot, character) pair, POST /scripts/motion/generate."""
    name_map = _character_name_map(script_data)
    pairs = []
    for shot in shots:
        sid = shot.get("id") or ""
        for cid in (shot.get("characters") or []):
            pairs.append((sid, cid))
    if not pairs:
        _log("  (no (shot, character) pairs -- skipping motion)")
        return []
    _log(f"  generating motion for {len(pairs)} (shot, character) pair(s)...")
    results = []
    for i, (sid, cid) in enumerate(pairs, 1):
        shot = next((s for s in shots if s.get("id") == sid), {})
        action_prompt = ((shot.get("visual_prompts") or {}).get("action_prompt")
                         or shot.get("action_summary") or "")
        body = {
            "shot_id": sid,
            "character_id": cid,
            "character_name": name_map.get(cid, cid),
            "action_prompt": action_prompt,
            "duration_seconds": float(shot.get("duration_seconds") or 5.0),
            "video_provider": video_provider,
            "project_id": project_id,
        }
        try:
            resp = client.post("/scripts/motion/generate", body,
                               timeout=STEP_TIMEOUTS["motion"])
            results.append(resp)
            _log(f"  ({i}/{len(pairs)}) {sid} x {cid} -> status={resp.get('status')}")
        except PipelineError as exc:
            _log(f"  ({i}/{len(pairs)}) motion failed for {sid} x {cid}: {exc}")
    return results


def step_archive(client: Client, project_id: str, shots: list) -> list:
    """POST /projects/{pid}/shots/{shot_id}/archive for each shot."""
    results = []
    for i, shot in enumerate(shots, 1):
        sid = shot.get("id") or ""
        if not sid:
            continue
        scene_id = shot.get("scene_id") or None
        params = {"scene_id": scene_id} if scene_id else None
        try:
            resp = client.post(f"/projects/{project_id}/shots/{sid}/archive",
                               body=None, params=params,
                               timeout=STEP_TIMEOUTS["archive"])
            results.append(resp)
            _log(f"  ({i}/{len(shots)}) archived {sid} -> {resp.get('fileName')}")
        except PipelineError as exc:
            _log(f"  ({i}/{len(shots)}) archive failed for {sid}: {exc}")
    if not results:
        raise PipelineError("archive", project_id, "no shot archives were created")
    return results


def step_render(client: Client, project_id: str, shot_ids: list,
                samples: int, device: str, fps: int) -> dict:
    """POST /projects/{pid}/render-queue -> per-shot MP4 paths."""
    body = {"shotIds": shot_ids, "samples": samples, "device": device, "fps": fps}
    resp = client.post(f"/projects/{project_id}/render-queue", body,
                       timeout=STEP_TIMEOUTS["render"])
    if not resp.get("blenderAvailable", True):
        raise PipelineError("render", project_id,
                            "Blender not available on the backend. Set BLENDER_EXECUTABLE "
                            "or install Blender, then re-run with --resume.")
    results = resp.get("results") or []
    succeeded = [r for r in results if r.get("status") == "succeeded"]
    failed = [r for r in results if r.get("status") == "failed"]
    if not succeeded:
        raise PipelineError("render", project_id,
                           f"no shots rendered successfully. failed={len(failed)}; "
                           f"first error: {failed[0].get('error') if failed else 'n/a'}")
    if failed:
        _log(f"  ! {len(failed)} shot(s) failed to render (continuing with the "
             f"{len(succeeded)} that succeeded)")
    return resp


def step_compose(client: Client, project_id: str, clip_paths: list,
                 durations: list, transition: str, transition_duration: float) -> dict:
    """POST /projects/{pid}/compose -> final MP4 path."""
    body = {
        "clipPaths": clip_paths,
        "durations": durations,
        "transition": transition,
        "transitionDuration": transition_duration,
    }
    return client.post(f"/projects/{project_id}/compose", body,
                       timeout=STEP_TIMEOUTS["compose"])


# --- Orchestration ---------------------------------------------------------

def _run_pipeline(args: argparse.Namespace) -> int:
    total = len(STEPS)
    client = Client(host=args.host, port=args.port, timeout=300)

    # Health check
    if not client.health():
        _log("ERROR: backend is not reachable. Start it first with:")
        _log("  python backend/run.py")
        return 2

    # Resume or fresh start
    if args.resume:
        try:
            state = _load_state(args.resume)
        except FileNotFoundError as exc:
            _log(f"ERROR: {exc}")
            return 2
        project_id = state.get("project_id") or args.resume
        completed = set(state.get("completed_steps") or [])
        _log(f"Resuming project {project_id}; completed steps: "
             f"{sorted(completed) if completed else '(none)'}")
        script_data = state.get("script_data") or {}
        shots = state.get("shots") or []
        raw_text = state.get("raw_text") or ""
    else:
        if args.script_file:
            raw_text = Path(args.script_file).read_text(encoding="utf-8")
        elif args.script:
            raw_text = args.script
        else:
            _log("ERROR: provide --script, --script-file, or --resume.")
            return 2
        if not args.output:
            _log("ERROR: --output is required for a fresh run.")
            return 2
        project_id = None
        completed = set()
        script_data = {}
        shots = []
        state = {"completed_steps": []}

    try:
        # 1. parse
        if "parse" not in completed:
            _log(f"[1/{total}] parse...")
            res = step_parse(client, raw_text, args.language, project_id)
            project_id = res["project_id"]
            script_data = res["script_data"]
            state.update({
                "step": "parse", "project_id": project_id,
                "script_data": script_data,
                "normalized_script": res["normalized_script"],
                "raw_text": raw_text,
                "completed_steps": sorted(completed | {"parse"}),
            })
            _save_state(project_id, state)
            completed.add("parse")
            _step_done(1, total, "parse", f"project_id={project_id}")
        else:
            _log(f"[1/{total}] parse...skipped (already done)")

        # 2. shots
        if "shots" not in completed:
            _log(f"[2/{total}] shots...")
            shots = step_shots(client, project_id, script_data,
                               args.language, args.shots_per_scene)
            state["shots"] = shots
            state["completed_steps"] = sorted(completed | {"shots"})
            _save_state(project_id, state)
            completed.add("shots")
            _step_done(2, total, "shots", f"{len(shots)} shot(s)")
        else:
            _log(f"[2/{total}] shots...skipped (already done, {len(shots)} shot(s))")

        # 3. characters
        if "characters" not in completed:
            _log(f"[3/{total}] characters (three-view)...")
            step_characters(client, project_id, script_data,
                            args.poll_interval, args.poll_max)
            state["completed_steps"] = sorted(completed | {"characters"})
            _save_state(project_id, state)
            completed.add("characters")
            _step_done(3, total, "characters")
        else:
            _log(f"[3/{total}] characters...skipped (already done)")

        # 4. scenes
        if "scenes" not in completed:
            _log(f"[4/{total}] scenes (generate-asset)...")
            step_scenes(client, project_id, script_data,
                        args.poll_interval, args.poll_max)
            state["completed_steps"] = sorted(completed | {"scenes"})
            _save_state(project_id, state)
            completed.add("scenes")
            _step_done(4, total, "scenes")
        else:
            _log(f"[4/{total}] scenes...skipped (already done)")

        # 5. motion
        if "motion" not in completed:
            _log(f"[5/{total}] motion (generate)...")
            step_motion(client, project_id, shots, script_data, args.video_provider)
            state["completed_steps"] = sorted(completed | {"motion"})
            _save_state(project_id, state)
            completed.add("motion")
            _step_done(5, total, "motion")
        else:
            _log(f"[5/{total}] motion...skipped (already done)")

        # 6. archive
        if "archive" not in completed:
            _log(f"[6/{total}] archive...")
            step_archive(client, project_id, shots)
            state["completed_steps"] = sorted(completed | {"archive"})
            _save_state(project_id, state)
            completed.add("archive")
            _step_done(6, total, "archive")
        else:
            _log(f"[6/{total}] archive...skipped (already done)")

        # 7. render
        if "render" not in completed:
            _log(f"[7/{total}] render-queue...")
            shot_ids = [s.get("id") for s in shots if s.get("id")]
            render_resp = step_render(client, project_id, shot_ids,
                                      args.render_samples, args.render_device,
                                      args.render_fps)
            render_paths = {}
            for r in render_resp.get("results") or []:
                if r.get("status") == "succeeded" and r.get("outputPath"):
                    render_paths[r.get("shotId")] = r["outputPath"]
            state["render_paths"] = render_paths
            state["completed_steps"] = sorted(completed | {"render"})
            _save_state(project_id, state)
            completed.add("render")
            _step_done(7, total, "render", f"{len(render_paths)} MP4(s)")
        else:
            _log(f"[7/{total}] render...skipped (already done)")

        # 8. compose
        if "compose" not in completed:
            _log(f"[8/{total}] compose...")
            render_paths = state.get("render_paths") or {}
            # Preserve shot order from the storyboard.
            clip_paths = [render_paths[s["id"]] for s in shots
                          if s.get("id") in render_paths]
            if not clip_paths:
                raise PipelineError("compose", project_id,
                                    "no rendered MP4 paths available to compose")
            durations = [float(s.get("duration_seconds") or 0.0) for s in shots
                         if s.get("id") in render_paths]
            comp = step_compose(client, project_id, clip_paths, durations,
                                args.transition, args.transition_duration)
            final_path = comp.get("outputPath")
            if not final_path or not Path(final_path).is_file():
                raise PipelineError("compose", project_id,
                                    f"compose returned missing output: {comp}")
            state["final_output"] = final_path
            state["completed_steps"] = sorted(completed | {"compose"})
            _save_state(project_id, state)
            completed.add("compose")
            _step_done(8, total, "compose",
                       f"duration={comp.get('durationSeconds', 0):.1f}s")
        else:
            _log(f"[8/{total}] compose...skipped (already done)")
            final_path = state.get("final_output")

        # Copy final MP4 to --output
        if args.output and final_path:
            out = Path(args.output)
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(final_path, out)
            _log(f"\nOK: copied final MP4 to {out}")
            _log(f"    project_id = {project_id}")
            _log(f"    backend output = {final_path}")
        else:
            _log(f"\nOK: pipeline complete (project_id={project_id})")
            _log(f"    backend output = {final_path}")

        return 0

    except PipelineError as exc:
        _log(f"\nFAILED at step '{exc.step}':\n{exc}")
        return 1
    except Exception as exc:
        _log(f"\nFAILED (unexpected): {type(exc).__name__}: {exc}")
        if project_id:
            _log(f"  -> resume with: python scripts/demo_pipeline.py "
                 f"--resume {project_id} --output <out.mp4>")
        return 1


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="demo_pipeline.py",
        description="AICSS E2E demo: script text -> playable MP4.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/demo_pipeline.py --script-file test/剧本.md --output out.mp4\n"
            "  python scripts/demo_pipeline.py --script \"内景·客厅·日\\n...\" --output out.mp4\n"
            "  python scripts/demo_pipeline.py --resume 20260926_xxx --output out.mp4\n"
        ),
    )
    p.add_argument("--script", default=None, help="Raw script text (inline).")
    p.add_argument("--script-file", default=None,
                   help="Path to a UTF-8 script file (e.g. test/剧本.md).")
    p.add_argument("--output", "-o", default=None,
                   help="Destination MP4 path for the final composed video.")
    p.add_argument("--resume", default=None,
                   help="Resume an interrupted run from its project_id.")
    p.add_argument("--host", default=DEFAULT_HOST, help="Backend host.")
    p.add_argument("--port", type=int, default=DEFAULT_PORT, help="Backend port.")
    p.add_argument("--language", default=DEFAULT_LANGUAGE,
                   help="Script language: chinese | english | japanese.")
    p.add_argument("--shots-per-scene", type=int, default=DEFAULT_SHOTS_PER_SCENE,
                   help="Lower bound on shots per scene.")
    p.add_argument("--transition", default=DEFAULT_TRANSITION,
                   choices=["cut", "dissolve", "fade", "wipe"],
                   help="Transition kind between adjacent shots.")
    p.add_argument("--transition-duration", type=float,
                   default=DEFAULT_TRANSITION_DURATION,
                   help="Transition duration in seconds.")
    p.add_argument("--video-provider", default=DEFAULT_VIDEO_PROVIDER,
                   help="Motion video provider: dashscope | local_wan | svd.")
    p.add_argument("--render-samples", type=int, default=DEFAULT_RENDER_SAMPLES,
                   help="Cycles sample count for the render-queue step.")
    p.add_argument("--render-device", default=DEFAULT_RENDER_DEVICE,
                   choices=["GPU", "CPU"], help="Cycles device.")
    p.add_argument("--render-fps", type=int, default=DEFAULT_RENDER_FPS,
                   help="Timeline frame rate for the render-queue step.")
    p.add_argument("--poll-interval", type=float, default=DEFAULT_POLL_INTERVAL,
                   help="Seconds between batch-status polls.")
    p.add_argument("--poll-max", type=int, default=DEFAULT_POLL_MAX,
                   help="Max batch-status polls before giving up.")
    return p


def main(argv: Optional[list] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    return _run_pipeline(args)


if __name__ == "__main__":
    sys.exit(main())




