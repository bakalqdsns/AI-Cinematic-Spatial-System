"""
DashScope Wanx2.1-imageedit inpaint utilities.

Uses direct base64 data URLs — no HTTP server or OSS upload needed.
"""
import base64
import io
import httpx
from PIL import Image
from dashscope import ImageSynthesis
from http import HTTPStatus

import dashscope

dashscope.base_http_api_url = "https://dashscope.aliyuncs.com/api/v1"


def pil_to_base64(img: Image.Image) -> str:
    """PIL Image -> data:image/png;base64,... string (RGB, alpha removed)."""
    if img.mode == "RGBA":
        rgb = Image.new("RGB", img.size, (255, 255, 255))
        rgb.paste(img, mask=img.split()[3])
        img = rgb
    elif img.mode != "RGB":
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"


def mask_to_inpaint_format(img: Image.Image) -> str:
    """
    Convert RGBA mask to inpaint format (white=edit area, black=keep area).

    mask: alpha=255 (selected object) -> black (keep, do NOT edit)
          alpha=0   (background / edit area)  -> white (edit)
    """
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    r, g, b, a = img.split()
    # alpha channel: 255 -> white (edit), 0 -> black (keep)
    rgb = Image.merge("RGB", (a, a, a))
    buf = io.BytesIO()
    rgb.save(buf, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"


def generate_inpaint(
    base_image: Image.Image,
    mask_image: Image.Image,
    prompt: str,
    api_key: str,
) -> Image.Image:
    """
    Call wanx2.1-imageedit for inpainting.

    base_image: cropped, fixed-size RGB image
    mask_image: RGBA inverse mask (white=edit, black=keep)
    prompt: inpainting prompt

    Returns PIL Image of the inpainted result.
    """
    base64_img = pil_to_base64(base_image)
    base64_mask = mask_to_inpaint_format(mask_image)

    rsp = ImageSynthesis.call(
        api_key=api_key,
        model="wanx2.1-imageedit",
        function="description_edit_with_mask",
        prompt=prompt,
        base_image_url=base64_img,
        mask_image_url=base64_mask,
        n=1,
    )

    if rsp.status_code != HTTPStatus.OK:
        raise RuntimeError(
            f"DashScope error: code={rsp.code}, message={rsp.message}, status={rsp.status_code}"
        )

    result_url = rsp.output.results[0].url

    resp = httpx.get(result_url, timeout=120)
    resp.raise_for_status()
    return Image.open(io.BytesIO(resp.content))
