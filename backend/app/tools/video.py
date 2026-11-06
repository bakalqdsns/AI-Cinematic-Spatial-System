"""动作视频与抽帧工具。

包装 ``app.services.motion_extractor`` 的视频生成与 ffmpeg 抽帧。
输入输出都是 str / list，不依赖 FastAPI，不直接读全局 settings。
"""
from __future__ import annotations

from typing import Optional

__all__ = ["action_video", "extract_frames"]


async def action_video(
    prompt: str,
    start_image_b64: Optional[str] = None,
    end_image_b64: Optional[str] = None,
    duration: float = 5.0,
    provider: str = "dashscope",
    greenscreen: bool = False,
) -> Optional[str]:
    """生成一段动作视频（图生视频）。

    输入:
        prompt: 动作描述文本。
        start_image_b64 / end_image_b64: 可选首尾关键帧（base64 PNG）。
        duration: 目标时长（秒）。
        provider: "dashscope"（云端 wan2.5，付费）/ "happyhorse"（云端，
            试用额度）/ "local_wan"（本地 28GB+ VRAM）/ "svd"（本地 8GB）。
        greenscreen: True 时给提示词追加绿幕背景指令，产物可直接交给
            ``key_greenscreen`` 抠像。
    输出:
        本地视频文件路径（str）；失败返回 None。
    副作用:
        调用视频生成后端，在缓存目录写入视频文件。
    模型:
        云端 DashScope VideoSynthesis 或本地 wan2.1 / SVD，取决于 provider。
    """
    from app.services.motion_extractor import generate_action_video

    return await generate_action_video(
        prompt,
        start_image_b64=start_image_b64,
        end_image_b64=end_image_b64,
        duration_seconds=duration,
        provider=provider,
        greenscreen=greenscreen,
    )


def extract_frames(
    video_path: str,
    output_dir: str,
    fps: float = 30.0,
    max_frames: int = 300,
    ffmpeg_path: Optional[str] = None,
) -> list[str]:
    """用 ffmpeg 把视频抽成 PNG 帧序列。

    输入:
        video_path: 源视频文件路径。
        output_dir: 帧输出目录（自动创建；已有 frame_*.png 会先清理）。
        fps: 抽帧采样率。
        max_frames: 帧数上限。
        ffmpeg_path: 显式 ffmpeg 路径；None 时依次找 FFMPEG_PATH 环境变量、
            imageio-ffmpeg 自带二进制、系统 PATH。
    输出:
        排序后的帧文件路径列表（frame_0001.png ...）。
    副作用:
        向 output_dir 写 PNG 帧；ffmpeg 缺失或执行失败抛 RuntimeError。
    模型:
        无（只调 ffmpeg 子进程）。
    """
    from app.services.motion_extractor import extract_frames_from_video

    return extract_frames_from_video(
        video_path,
        output_dir,
        fps=fps,
        max_frames=max_frames,
        ffmpeg_path=ffmpeg_path,
    )
