"""
DashScope wanx2.1-imageedit 图像编辑工具。

使用异步 API：
  1. POST /services/aigc/image2image/image-synthesis  创建任务，获取 task_id
  2. GET  /tasks/{task_id}                            轮询任务状态直到完成
  3. 下载 output_image_url 并返回 PIL Image

模型文档：https://help.aliyun.com/zh/model-studio/wanx-image-edit
mask 语义：白=待编辑区域（生成内容），黑=保留区域
"""

import base64
import io
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Optional

import httpx
import numpy as np
from PIL import Image

import dashscope

dashscope.base_http_api_url = "https://dashscope.aliyuncs.com/api/v1"

BASE_URL = dashscope.base_http_api_url

# DashScope 对 base64 data URI 的长度限制（留余量）
MAX_BASE64_LEN = 8 * 1024 * 1024  # 8 MB（DashScope 限制 10 MB）
DEBUG_INPAINT_MASK = os.environ.get("DEBUG_INPAINT_MASK") == "1"
DEBUG_INPAINT_OUTPUT_DIR = os.environ.get("AICSS_INPAINT_DEBUG_DIR", "")


def _write_debug_image(filename: str, image: Image.Image, *, format: str | None = None) -> Path | None:
    """在启用调试时，将图像写入临时目录或指定目录。"""
    if not DEBUG_INPAINT_MASK and not DEBUG_INPAINT_OUTPUT_DIR:
        return None

    target_dir = Path(DEBUG_INPAINT_OUTPUT_DIR) if DEBUG_INPAINT_OUTPUT_DIR else Path(tempfile.gettempdir()) / "aicss_inpaint_debug"
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / filename
    image.save(path, format=format)
    return path


def _write_debug_bytes(filename: str, data: bytes) -> Path | None:
    """在启用调试时，将原始 bytes 写入调试目录。"""
    if not DEBUG_INPAINT_MASK and not DEBUG_INPAINT_OUTPUT_DIR:
        return None

    target_dir = Path(DEBUG_INPAINT_OUTPUT_DIR) if DEBUG_INPAINT_OUTPUT_DIR else Path(tempfile.gettempdir()) / "aicss_inpaint_debug"
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / filename
    path.write_bytes(data)
    return path


def _compute_resize_ratio(
    img_size: tuple[int, int],
    target_max_dim: int = 2048,
) -> float:
    """
    计算缩放比例，使得图像不超过 target_max_dim 像素的边长。
    如果图像已经在限制内，返回 1.0。
    """
    w, h = img_size
    longest = max(w, h)
    if longest <= target_max_dim:
        return 1.0
    return target_max_dim / longest


def _find_best_quality_and_size(
    img: Image.Image,
    orig_size: tuple[int, int],
    ratio: float,
    max_b64_len: int,
) -> tuple[str, tuple[int, int]]:
    """
    给定原始图像、缩放比例和 base64 长度限制，
    尝试找到满足限制的编码方案。

    策略：先降质量（95→15），再缩小尺寸。两阶段确保即使极高分辨率图像也能传入 API。
    返回 (base64_data_uri, 最终尺寸)。
    """
    w, h = orig_size
    new_w, new_h = max(512, int(w * ratio)), max(512, int(h * ratio))
    target_size = (new_w, new_h)

    if img.size != target_size:
        img = img.resize(target_size, Image.LANCZOS)

    for quality in (95, 85, 75, 60, 50, 40, 30, 20, 15):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        b64 = base64.b64encode(buf.getvalue()).decode()
        data_uri = f"data:image/jpeg;base64,{b64}"
        if len(data_uri) <= max_b64_len:
            return data_uri, target_size

    # 最低质量仍超限：同步缩小尺寸
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=15)
    b64_est = base64.b64encode(buf.getvalue()).decode()
    scale_down = (max_b64_len / len(b64_est)) ** 0.5
    new_w2 = max(512, int(new_w * scale_down))
    new_h2 = max(512, int(new_h * scale_down))
    img2 = img.resize((new_w2, new_h2), Image.LANCZOS)
    buf2 = io.BytesIO()
    img2.save(buf2, format="JPEG", quality=15)
    b64 = base64.b64encode(buf2.getvalue()).decode()
    return f"data:image/jpeg;base64,{b64}", (new_w2, new_h2)


def _encode_image(img: Image.Image) -> tuple[str, tuple[int, int]]:
    """将 PIL Image 编码为 base64 JPEG data URI，返回 (data_uri, 最终尺寸)。"""
    if img.mode == "RGBA":
        # RGBA → RGB：白色背景合成（alpha 混合），避免透明区域变黑影响 API 识别内容
        rgb = Image.new("RGB", img.size, (255, 255, 255))
        rgb.paste(img, mask=img.split()[3])
        img = rgb
    elif img.mode != "RGB":
        img = img.convert("RGB")

    return _find_best_quality_and_size(img, img.size, 1.0, MAX_BASE64_LEN)


def _encode_mask(mask_img: Image.Image, target_size: tuple[int, int]) -> tuple[str, tuple[int, int]]:
    """
    将 mask 图像编码为灰度 PNG base64 data URI。
    target_size 必须与 image 最终尺寸完全一致。
    返回 (data_uri, target_size)。
    """
    if mask_img.mode == "RGBA":
        alpha = mask_img.split()[3]
    elif mask_img.mode == "L":
        alpha = mask_img
    else:
        alpha = mask_img.convert("L")

    if alpha.size != target_size:
        alpha = alpha.resize(target_size, Image.NEAREST)

    # 入参 mask: 白色笔触 alpha=255（物体=白=待编辑），背景 alpha=0（待保留）
    # 反相后送入 API：物体→255(白=编辑)，背景→0(黑=保留)
    gray = Image.fromarray(255 - np.array(alpha), mode="L")

    # 灰度值直接对应 API mask_image_url 语义：
    #   非零（白）= 待编辑区域（生成内容）
    #   零（黑） = 保留区域
    buf = io.BytesIO()
    gray.save(buf, format="PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode()
    data_uri = f"data:image/png;base64,{b64}"

    return data_uri, target_size


def _create_imageedit_task(
    image_base64: str,
    mask_base64: str | None,
    prompt: str,
    api_key: str,
    function: str = "description_edit_with_mask",
) -> str:
    """
    创建 wanx2.1-imageedit 任务，返回 task_id。

    function: 选择具体图像编辑能力：
      - "description_edit_with_mask": 局部"描述驱动修补"，偏保守，会尽量保持原图结构。
      - "stylization_local":           局部风格迁移，会显著替换 mask 区域为新风格，幅度明显大于前者。
      - 其余可选："stylization_all" / "description_edit" / "remove_watermark" /
        "expand" / "super_resolution" / "colorization" / "doodle" /
        "control_cartoon_feature"
      - mask_base64 在与 mask 无关的 function 下传 None 即可。
    """
    url = f"{BASE_URL}/services/aigc/image2image/image-synthesis"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }
    input_payload: dict = {
        "function": function,
        "base_image_url": image_base64,
        "prompt": prompt,
    }
    if mask_base64 is not None:
        input_payload["mask_image_url"] = mask_base64

    payload = {
        "model": "wanx2.1-imageedit",
        "input": input_payload,
        "parameters": {
            "n": 1,
        },
    }

    print(f"[inpaint] wanx2.1-imageedit payload: function={function}, "
          f"mask={'yes' if mask_base64 is not None else 'no'}, "
          f"prompt={prompt[:120]!r}")

    resp = httpx.post(url, headers=headers, json=payload, timeout=60)
    if resp.status_code != 200:
        try:
            err_body = resp.json()
        except Exception:
            err_body = resp.text
        raise RuntimeError(f"DashScope API error {resp.status_code}: {err_body}")

    data = resp.json()
    if "output" not in data:
        raise RuntimeError(f"Unexpected response creating task: {data}")

    task_id = data["output"].get("task_id")
    if not task_id:
        raise RuntimeError(f"No task_id in response: {data}")

    print(f"[inpaint DEBUG] task created: id={task_id}")
    return task_id


def _poll_task(task_id: str, api_key: str, max_wait: Optional[int] = None) -> str:
    """轮询任务状态，返回结果图片的 URL。"""
    if max_wait is None:
        from ..config import settings as _settings
        max_wait = _settings.inpaint_timeout
    url = f"{BASE_URL}/tasks/{task_id}"
    headers = {"Authorization": f"Bearer {api_key}"}

    elapsed = 0
    interval = 2
    while elapsed < max_wait:
        resp = httpx.get(url, headers=headers, timeout=30)
        if resp.status_code != 200:
            try:
                err_body = resp.json()
            except Exception:
                err_body = resp.text
            raise RuntimeError(f"DashScope poll error {resp.status_code}: {err_body}")

        data = resp.json()
        status = data.get("output", {}).get("task_status")

        if status == "SUCCEEDED":
            print(f"[inpaint DEBUG] task SUCCEEDED, full response:")
            print(f"[inpaint DEBUG] {json.dumps(data, indent=2)}")
            # wanx2.1-imageedit: results[0].url
            results = data.get("output", {}).get("results", [])
            if results:
                result_url = results[0].get("url")
            else:
                result_url = data.get("output", {}).get("output_image_url")
            if not result_url:
                raise RuntimeError(f"Task succeeded but no URL in response: {data}")
            return result_url

        if status == "FAILED":
            code = data["output"].get("code", "Unknown")
            message = data["output"].get("message", "No message")
            raise RuntimeError(f"Task FAILED: [{code}] {message}")

        print(f"[inpaint DEBUG] task status={status}, elapsed={elapsed}s")
        time.sleep(interval)
        elapsed += interval

    raise RuntimeError(f"Task {task_id} did not complete within {max_wait}s")


def generate_inpaint(
    base_image: Image.Image,
    mask_image: Image.Image,
    prompt: str,
    api_key: str,
    poll_timeout: Optional[int] = None,
    function: str = "description_edit_with_mask",
) -> Image.Image:
    """
    使用 wanx2.1-imageedit 模型进行局部重绘。

    base_image:  原始 RGB 图像（PIL Image）
    mask_image:  前端传来的 mask
                  - RGBA: alpha=255（物体=白=待编辑），alpha=0（背景=黑=保留）
                  - L:    255=待编辑, 0=保留
                  编码时会反相，使送入 API 的 mask 语义为：
                    白=编辑区、黑=保留区
    prompt:      描述 mask 白色区域应填充的内容（如 "自然背景"）
    api_key:     DashScope API Key
    poll_timeout: 轮询任务的最大等待秒数；为 None 时回退到 settings.inpaint_timeout
    function:    DashScope wanx2.1-imageedit 的 function 字段；详见 _create_imageedit_task。

    返回：重绘后的 PIL Image
    """
    w, h = base_image.size
    if w < 512 or h < 512:
        raise ValueError(
            f"Image too small: {w}x{h}px. API requires at least 512x512 pixels."
        )

    print(f"[inpaint DEBUG] base_image: {base_image.size}, mode={base_image.mode}")
    print(f"[inpaint DEBUG] mask_image: {mask_image.size}, mode={mask_image.mode}")
    print(f"[inpaint DEBUG] function={function}, prompt_len={len(prompt)}")

    # 分析原始 mask
    if mask_image.mode == "RGBA":
        alpha = mask_image.split()[3]
    else:
        alpha = mask_image.convert("L")
    alpha_arr = np.array(alpha)
    white_ratio = (alpha_arr > 0).mean()
    print(f"[inpaint DEBUG] mask non-zero ratio: {white_ratio:.4f}")

    if white_ratio < 0.001:
        raise ValueError(
            f"Mask is empty or nearly empty ({white_ratio*100:.2f}% non-zero pixels). "
            "Please select an area to inpaint before submitting."
        )

    if white_ratio < 0.05:
        # 小 mask：周围 context 占绝对主导，模型会"照抄四周"，结果几乎看不出变化。
        # 这里只打印日志——真正给前端的反馈由 endpoint 层通过 warnings 字段告知。
        print(f"[inpaint WARNING] mask is very small ({white_ratio*100:.2f}% of pixels). "
              "Diffusion models tend to inpaint as a copy/extension of surroundings "
              "when the mask is tiny. Expect a result close to the original.")

    # -----------------------------------------------------------
    # 关键：image 和 mask 必须使用相同的缩放比例 ratio
    # 步骤：
    #   1. 编码 image → 可能需要缩放
    #   2. 用同样的 ratio 缩放 mask
    # -----------------------------------------------------------

    # 1. 编码 image（可能降质量或缩尺寸）
    image_b64, img_final_size = _encode_image(base_image)
    print(f"[inpaint DEBUG] image: len={len(image_b64)}, size={img_final_size}")

    # 2. 用相同的 target_size 编码 mask
    mask_b64, mask_final_size = _encode_mask(mask_image, img_final_size)
    print(f"[inpaint DEBUG] mask:  len={len(mask_b64)}, size={mask_final_size}")

    # 验证：image 和 mask 尺寸必须一致
    if img_final_size != mask_final_size:
        raise RuntimeError(
            f"Size mismatch: image={img_final_size}, mask={mask_final_size}"
        )

    # 保存调试文件
    try:
        mask_decoded = Image.open(io.BytesIO(base64.b64decode(
            mask_b64.split(",", 1)[1] if "," in mask_b64 else mask_b64
        )))
        debug_mask_path = _write_debug_image("mask_for_api.png", mask_decoded)
        mask_arr = np.array(mask_decoded)
        print(f"[inpaint DEBUG] mask_for_api: {mask_decoded.size}, "
              f"non-zero={(mask_arr > 0).mean():.4f}, mean={mask_arr.mean():.1f}, path={debug_mask_path}")

        img_decoded = Image.open(io.BytesIO(base64.b64decode(
            image_b64.split(",", 1)[1] if "," in image_b64 else image_b64
        )))
        debug_image_path = _write_debug_image("img_for_api.jpg", img_decoded, format="JPEG")
        print(f"[inpaint DEBUG] img_for_api: {img_decoded.size}, path={debug_image_path}")
    except Exception as e:
        print(f"[inpaint DEBUG] debug save failed: {e}")

    # 3. 创建任务
    task_id = _create_imageedit_task(
        image_b64,
        mask_b64,
        prompt,
        api_key,
        function=function,
    )

    # 4. 轮询结果（使用 AICSS_INPAINT_TIMEOUT 控制总等待时长）
    result_url = _poll_task(task_id, api_key, max_wait=poll_timeout)

    # 5. 下载结果（下载阶段使用相同的 timeout 限制，避免长任务超时后还被卡住）
    download_timeout = poll_timeout if poll_timeout is not None else 120
    print(f"[inpaint DEBUG] downloading result_url={result_url}")
    resp = httpx.get(result_url, timeout=download_timeout)
    print(f"[inpaint DEBUG] result resp: status={resp.status_code}, "
          f"content_type={resp.headers.get('Content-Type')}, "
          f"content_length={len(resp.content)}")
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to download result image: {resp.status_code}")

    # 检查是否下载到了非图片内容（如 JSON 错误页）
    content_start = resp.content[:50]
    try:
        text_preview = content_start.decode('utf-8')
        if text_preview.strip().startswith('{'):
            print(f"[inpaint DEBUG] WARNING: result content appears to be JSON: {text_preview}")
    except Exception:
        pass

    # 保存原始 bytes（不经过 PIL）
    raw_path = _write_debug_bytes("raw_result.bin", resp.content)
    if raw_path:
        print(f"[inpaint DEBUG] raw bytes saved: {raw_path} ({len(resp.content)} bytes)")

    # PIL 分析与保存
    result_img = Image.open(io.BytesIO(resp.content))
    try:
        print(f"[inpaint DEBUG] result PIL: size={result_img.size}, mode={result_img.mode}")
        print(f"[inpaint DEBUG] bands={result_img.getbands()}")
        print(f"[inpaint DEBUG] extrema={result_img.getextrema()}")
        print(f"[inpaint DEBUG] info keys={list(result_img.info.keys())}")

        result_ext = "png" if result_img.mode == "RGBA" or resp.headers.get("Content-Type", "").endswith("png") else "jpg"
        result_path = _write_debug_image(
            f"result_from_api.{result_ext}",
            result_img,
            format="PNG" if result_ext == "png" else "JPEG",
        )
        if result_path:
            print(f"[inpaint DEBUG] PIL saved: {result_path}")

        result_arr = np.array(result_img)
        print(f"[inpaint DEBUG] result pixels: "
              f"min={result_arr.min()}, max={result_arr.max()}, mean={result_arr.mean():.1f}")
        if result_img.mode == "RGBA":
            alpha = result_arr[:, :, 3]
            print(f"[inpaint DEBUG] result alpha: min={alpha.min()}, max={alpha.max()}, "
                  f"non-zero={(alpha > 0).mean():.4f}")
    except Exception as e:
        print(f"[inpaint DEBUG] PIL analysis failed: {e}")
        print(f"[inpaint DEBUG] result raw bytes (hex): {resp.content[:200].hex()}")

    return result_img


# ─────────────────────────────────────────────────────────────────────────────
# Prompt & mode guidance
# ─────────────────────────────────────────────────────────────────────────────

# 经验上偏"修补延续"的弱 prompt 关键词。这些词会引导模型"延续上下文"而不是
# "重绘"，导致修复结果与原图差异极小。
WEAK_PROMPT_KEYWORDS_ZH = {
    "补全", "补", "修复", "还原", "自然背景", "背景", "填补",
    "继续", "延伸", "保持原", "原样", "原画面", "原构图",
}
WEAK_PROMPT_KEYWORDS_EN = {
    "inpaint", "fill", "fix", "restore", "natural background",
    "background", "continue", "extend", "keep original", "same as before",
    "repair",
}


def detect_weak_prompt(prompt: str) -> dict | None:
    """
    检测 prompt 是否属于"弱 prompt"——即根据经验几乎只引导模型做延续式修补。

    返回 None 表示 prompt 足够具体；否则返回一个 dict，前端可以原样展示：
      {"code": "weak_prompt", "reason": "...", "matched": [...], "suggested": "..."}

    注意：本函数只诊断、不修改 user prompt。是否自动强化由 endpoint 控制。
    """
    if not prompt:
        return {
            "code": "empty_prompt",
            "reason": "Prompt is empty; model will fall back to context copy/extension.",
            "matched": [],
            "suggested": (
                "Describe the *desired new content* explicitly, e.g. "
                "'replace with a watercolor sunset over the lake, cinematic, soft light'. "
                "Avoid generic words like 'background' or 'fix'."
            ),
        }

    normalized = prompt.strip().lower()
    tokens = set()
    for kw in WEAK_PROMPT_KEYWORDS_ZH:
        if kw in prompt:
            tokens.add(kw)
    for kw in WEAK_PROMPT_KEYWORDS_EN:
        if kw in normalized:
            tokens.add(kw)

    # 去空格/标点的纯长度判断：<6 字符且只匹配到弱词 → 弱
    if tokens and len(prompt.strip()) < 12:
        return {
            "code": "weak_prompt",
            "reason": (
                f"Prompt is very short and contains 'extend-the-context' keywords "
                f"({sorted(tokens)!r}). Diffusion inpainting will most likely just copy "
                "the surrounding texture into the masked area, producing a result "
                "almost identical to the original."
            ),
            "matched": sorted(tokens),
            "suggested": (
                "Write what you want to *appear* in the masked area, not how to fill it. "
                "Example: 'a clear night sky with stars and a glowing moon, cinematic, "
                "soft volumetric light'."
            ),
        }

    return None


STYLE_PRESETS_FOR_RESTYLE = {
    # 阿里 wanx2.1-imageedit/stylization_local 文档列出的官方风格。
    # 中文与英文名称都接受，统一映射到中文调用。
    "photographic":        "写实主义",
    "realistic":           "写实主义",
    "anime":               "日系动漫",
    "japanese anime":      "日系动漫",
    "oil painting":        "油画",
    "watercolor":          "水彩",
    "sketch":              "素描",
    "3d cartoon":          "3D 卡通",
    "cartoon":             "3D 卡通",
    "chinese painting":    "国画",
    "flat illustration":   "扁平插画",
    "illustration":        "扁平插画",
    "cyberpunk":           "赛博朋克",
    "comic":               "漫画",
}


def resolve_stylization_prompt(prompt: str, style: str | None) -> str:
    """
    为 mode='restyle' 构造 prompt。

    关键点：stylization_local 是"风格迁移"模型，对 prompt 的响应风格与
    description_edit_with_mask 不同——它需要一个明确的目标风格与构图，
    否则很容易在 mask 范围内"原地画一个东西"，看起来像贴上去的。
    这里统一在用户 prompt 外面补一层明确的指令，提升重绘幅度。
    """
    style_token = None
    if style:
        key = style.strip().lower()
        style_token = STYLE_PRESETS_FOR_RESTYLE.get(key, style)

    parts = []
    if style_token:
        parts.append(f"以{style_token}风格")
    parts.append("完全重绘 mask 区域内容")
    parts.append(
        "不要保留原图构图、纹理或物体形状，"
        "不要复刻 mask 周围的内容，"
        "避免与原图相同的色彩与结构。"
    )
    if prompt.strip():
        parts.append(f"主体内容：{prompt.strip()}")

    directive = "，".join(parts) + "。"
    print(f"[inpaint] restyle directive: {directive!r}")
    return directive


def compute_mask_white_ratio(mask_image: Image.Image) -> float:
    """
    统计 mask 中"待编辑区域"占比。
    与 generate_inpaint 内的算法保持一致：RGBA 取 alpha，L 模式直接使用。
    """
    if mask_image.mode == "RGBA":
        alpha = mask_image.split()[3]
    else:
        alpha = mask_image.convert("L")
    arr = np.array(alpha)
    return float((arr > 0).mean())
