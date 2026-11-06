"""工具层内部共享的小工具（私有，不属于对外 API）。

只放两件到处都要用的东西：图像输入归一化、语言参数归一化。
"""
from __future__ import annotations

from pathlib import Path
from typing import Union

import numpy as np
from PIL import Image

ImageLike = Union[Image.Image, np.ndarray, str, Path]


def to_pil(image: ImageLike, *, mode: str = "RGB") -> Image.Image:
    """把 PIL 图像 / numpy 数组 / 文件路径统一成 PIL 图像。

    - ``PIL.Image.Image``：按需 convert(mode)
    - ``numpy.ndarray``：HxWx3 uint8 视为 RGB，HxWx4 视为 RGBA
    - ``str`` / ``Path``：当作图像文件路径打开
    """
    if isinstance(image, Image.Image):
        return image.convert(mode) if image.mode != mode else image
    if isinstance(image, np.ndarray):
        arr = image
        if arr.ndim == 2:
            return Image.fromarray(arr.astype(np.uint8), mode="L").convert(mode)
        if arr.ndim == 3 and arr.shape[2] == 4:
            return Image.fromarray(arr.astype(np.uint8), mode="RGBA").convert(mode)
        return Image.fromarray(arr.astype(np.uint8), mode="RGB").convert(mode)
    if isinstance(image, (str, Path)):
        return Image.open(image).convert(mode)
    raise TypeError(f"不支持的图像输入类型: {type(image)!r}")


def to_language(value, default=None):
    """把 "chinese" / "english" / "japanese" 字符串或枚举统一成 ScriptLanguage。

    无法识别时返回 ``default``（默认中文）。
    """
    from app.services.script_parser import ScriptLanguage

    if default is None:
        default = ScriptLanguage.CHINESE
    if isinstance(value, ScriptLanguage):
        return value
    if value is None:
        return default
    try:
        return ScriptLanguage(str(value).strip().lower())
    except ValueError:
        return default
