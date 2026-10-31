"""把本机 ComfyUI 当作本地出图和出视频的执行器。

工作流 JSON 来自仓库里的 `workflows/comfy/`。调用方只改提示词、尺寸、
时长、种子和参考图，其余采样节点保持工作流原样。
"""
from __future__ import annotations

import asyncio
import copy
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from app.services.settings_manager import get as get_setting

logger = logging.getLogger("aicss.comfyui")

_REPO_ROOT = Path(__file__).resolve().parents[3]
_WORKFLOW_DIR = _REPO_ROOT / "workflows" / "comfy"
ZIMAGE_WORKFLOW = _WORKFLOW_DIR / "zimage.json"
MINIMAX_WORKFLOW = _WORKFLOW_DIR / "minimax_h3_selflift.json"

_ZIMAGE_POSITIVE = "67"
_ZIMAGE_NEGATIVE = "71"
_ZIMAGE_LATENT = "68"
_ZIMAGE_SAMPLER = "70"

_VIDEO_PROMPT = "232"
_VIDEO_SECONDS = "132"
_VIDEO_SAMPLER = "235"
_VIDEO_CONDITION = "136"
_VIDEO_REF_NODE = "9001"


def comfyui_base_url() -> str:
    raw = str(get_setting("comfyui_base_url", "http://127.0.0.1:8188") or "").strip()
    return raw.rstrip("/") or "http://127.0.0.1:8188"


def load_workflow(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"ComfyUI 工作流不是对象: {path}")
    return data


def apply_zimage_prompt(
    workflow: dict[str, Any],
    prompt: str,
    *,
    width: int,
    height: int,
    seed: int,
    negative: str | None = None,
) -> dict[str, Any]:
    graph = copy.deepcopy(workflow)
    graph[_ZIMAGE_POSITIVE]["inputs"]["text"] = prompt
    if negative is not None:
        graph[_ZIMAGE_NEGATIVE]["inputs"]["text"] = negative
    graph[_ZIMAGE_LATENT]["inputs"]["width"] = int(width)
    graph[_ZIMAGE_LATENT]["inputs"]["height"] = int(height)
    graph[_ZIMAGE_SAMPLER]["inputs"]["seed"] = int(seed)
    return graph


def apply_minimax_prompt(
    workflow: dict[str, Any],
    prompt: str,
    *,
    duration_seconds: float,
    seed: int,
    reference_filename: str | None = None,
) -> dict[str, Any]:
    graph = copy.deepcopy(workflow)
    seconds = max(1.0, min(float(duration_seconds), 15.0))
    graph[_VIDEO_PROMPT]["inputs"]["value"] = prompt
    graph[_VIDEO_SECONDS]["inputs"]["value"] = seconds
    graph[_VIDEO_SAMPLER]["inputs"]["seed"] = int(seed)
    if reference_filename:
        graph[_VIDEO_REF_NODE] = {
            "inputs": {"image": reference_filename},
            "class_type": "LoadImage",
            "_meta": {"title": "参考图"},
        }
        graph[_VIDEO_CONDITION]["inputs"]["ref_images.ref_image_0"] = [_VIDEO_REF_NODE, 0]
    return graph


def output_files(history_entry: dict[str, Any]) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    for node_out in (history_entry.get("outputs") or {}).values():
        if not isinstance(node_out, dict):
            continue
        for key in ("images", "gifs", "videos"):
            for item in node_out.get(key) or []:
                if isinstance(item, dict) and item.get("filename"):
                    found.append({
                        "filename": str(item["filename"]),
                        "subfolder": str(item.get("subfolder") or ""),
                        "type": str(item.get("type") or "output"),
                    })
    return found


def _history_error(entry: dict[str, Any]) -> str | None:
    status = entry.get("status") or {}
    if status.get("status_str") != "error":
        return None
    messages = status.get("messages") or []
    return str(messages)[:800] or "ComfyUI 执行失败"


async def upload_image(image_bytes: bytes, filename: str) -> str:
    base = comfyui_base_url()
    async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
        response = await client.post(
            f"{base}/upload/image",
            data={"overwrite": "true"},
            files={"image": (filename, image_bytes, "image/png")},
        )
        response.raise_for_status()
        name = response.json().get("name")
        if not name:
            raise RuntimeError("ComfyUI 没有返回上传后的文件名")
        return str(name)


async def run_workflow(workflow: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    base = comfyui_base_url()
    async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
        queued = await client.post(
            f"{base}/prompt",
            json={"prompt": workflow, "client_id": str(uuid.uuid4())},
        )
        queued.raise_for_status()
        body = queued.json()
        if body.get("node_errors"):
            raise RuntimeError(f"ComfyUI 拒绝了工作流: {str(body['node_errors'])[:800]}")
        prompt_id = body.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI 没有返回 prompt_id: {str(body)[:400]}")

    deadline = time.monotonic() + timeout
    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        while time.monotonic() < deadline:
            history = await client.get(f"{base}/history/{prompt_id}")
            history.raise_for_status()
            payload = history.json()
            entry = payload.get(prompt_id) if isinstance(payload, dict) else None
            if isinstance(entry, dict) and entry.get("outputs"):
                error = _history_error(entry)
                if error:
                    raise RuntimeError(error)
                return entry
            if isinstance(entry, dict):
                error = _history_error(entry)
                if error:
                    raise RuntimeError(error)
            await asyncio.sleep(1.5)
    raise TimeoutError(f"ComfyUI 在 {int(timeout)} 秒内没有完成")


async def download_file(item: dict[str, str]) -> bytes:
    base = comfyui_base_url()
    async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
        response = await client.get(
            f"{base}/view",
            params={
                "filename": item["filename"],
                "subfolder": item.get("subfolder") or "",
                "type": item.get("type") or "output",
            },
        )
        response.raise_for_status()
        return response.content


def comfy_image_selected() -> bool:
    return str(get_setting("local_image_backend", "diffusers")) == "comfyui"


def workflow_path(kind: str) -> Path:
    if kind == "image":
        configured = get_setting("comfyui_image_workflow", "")
        return Path(configured) if configured else ZIMAGE_WORKFLOW
    configured = get_setting("comfyui_video_workflow", "")
    return Path(configured) if configured else MINIMAX_WORKFLOW


def _default_seed(seed: int | None) -> int:
    if seed is not None:
        return int(seed)
    return int(uuid.uuid4().int % (2**31))


def _pick_output(files: list[dict[str, str]], suffixes: tuple[str, ...]) -> dict[str, str]:
    for item in files:
        if item["filename"].lower().endswith(suffixes):
            return item
    if files:
        return files[0]
    raise RuntimeError("ComfyUI 完成了，但没有输出文件")


async def generate_zimage_png(
    prompt: str,
    *,
    width: int = 1024,
    height: int = 1024,
    seed: int | None = None,
    negative: str | None = None,
) -> bytes:
    path = workflow_path("image")
    graph = apply_zimage_prompt(
        load_workflow(path),
        prompt,
        width=max(64, int(width)),
        height=max(64, int(height)),
        seed=_default_seed(seed),
        negative=negative,
    )
    entry = await run_workflow(graph, timeout=300)
    item = _pick_output(output_files(entry), (".png", ".jpg", ".jpeg", ".webp"))
    return await download_file(item)


async def generate_minimax_video(
    prompt: str,
    *,
    duration_seconds: float = 5.0,
    seed: int | None = None,
    reference_png: bytes | None = None,
) -> bytes:
    path = workflow_path("video")
    reference_name = None
    if reference_png:
        reference_name = await upload_image(reference_png, f"aicss_ref_{uuid.uuid4().hex[:8]}.png")
    graph = apply_minimax_prompt(
        load_workflow(path),
        prompt,
        duration_seconds=duration_seconds,
        seed=_default_seed(seed),
        reference_filename=reference_name,
    )
    entry = await run_workflow(graph, timeout=1800)
    item = _pick_output(output_files(entry), (".mp4", ".webm", ".mkv", ".gif"))
    return await download_file(item)
