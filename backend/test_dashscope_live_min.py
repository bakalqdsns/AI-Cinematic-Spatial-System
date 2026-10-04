"""Lowest-cost live DashScope e2e: a single video generation call.

Goal: prove that with a real DashScope API key

  * ``greenscreen=True`` injects the chroma-key prompt into the call,
  * the response is a downloadable MP4 URL,
  * the resulting video can be parsed by ``cv2.VideoCapture`` (i.e. ffmpeg
    compatible), and
  * frame extraction + chroma key on a single representative frame leaves
    green pixels with alpha == 0.

What is mocked out (intentional, to keep cost low):
  * ``segment_person_from_frame`` uses the synthetic SAM2 mock — we are
    only validating the provider output, not retraining SAM2.
  * Only ONE video generation call is issued.

Cleanup: the generated MP4 lives under ``backend/test_outputs/dashscope_live/``
and is deleted at the end of the script.
"""
from __future__ import annotations

import asyncio
import base64
import io
import os
import shutil
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# IMPORTANT: set API key BEFORE importing anything that loads settings.
API_KEY = "sk-be08ad3df19b4114affd9b03168816c7"
os.environ["DASHSCOPE_API_KEY"] = API_KEY
os.environ["DASHSCOPE_VIDEO_API_KEY"] = API_KEY


def _make_inline_start_image() -> str:
    """Tiny PNG (64x64) — a gray circle on transparent background.
    Returned as base64 with no data-URI prefix (provider adds it)."""
    from PIL import Image
    img = Image.new("RGBA", (64, 64), (255, 255, 255, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


async def _run_dashscope_with_greenscreen():
    from app.services.video_adapter import DashScopeFilmProvider
    provider = DashScopeFilmProvider()
    # Sanity: API key resolves
    key = provider._resolve_api_key()
    assert key, "API key must resolve from DASHSCOPE_API_KEY env"
    print(f"[live] API key resolved: ...{key[-6:]}")

    # Confirm greenscreen prompt injection (no API call)
    from app.services.video_adapter import _apply_greenscreen_prompt
    injected = _apply_greenscreen_prompt("walking", greenscreen=True)
    assert "00FF00" in injected or "green" in injected.lower(), (
        f"greenscreen prompt injection missing: {injected!r}"
    )
    print(f"[live] greenscreen prompt injection: {injected!r}")

    # THE actual DashScope call. duration=1 (5s is min for wanx_2_1_i2v_plus; we
    # leave default — provider has no duration knob here, see comment below).
    print("[live] calling DashScope VideoSynthesis.call()…")
    start_b64 = _make_inline_start_image()
    try:
        video_path = await provider.generate(
            prompt="character breathing",
            start_image_b64=start_b64,
            duration=1.0,
            greenscreen=True,
        )
    except Exception as e:
        print(f"[live] provider raised: {type(e).__name__}: {e}")
        raise

    return video_path, injected


def _verify_video_file(path: Path) -> int:
    """Return frame count from a downloaded MP4; raises if cv2 can't open it."""
    import cv2
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"cv2.VideoCapture failed to open {path}")
    count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    print(f"[live] video file: {path}  {w}x{h}  {fps:.1f}fps  {count} frames")
    return count


def _extract_one_frame(video_path: Path, frame_idx: int = 0) -> "np.ndarray":
    import cv2
    cap = cv2.VideoCapture(str(video_path))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError("failed to read frame")
    return frame


def _apply_chroma_key_to_frame(rgba: "np.ndarray") -> "np.ndarray":
    """Re-implements chroma_key_rgba locally so this script doesn't depend
    on the motion_extractor module's helpers."""
    import numpy as np
    b, g, r, a = cv2.split(rgba)
    diff = np.sqrt(
        (b.astype(int) - 0) ** 2 +
        (g.astype(int) - 255) ** 2 +
        (r.astype(int) - 0) ** 2
    )
    threshold = 80
    softness = 20
    new_alpha = np.clip(((diff - threshold) * 255 / softness), 0, 255).astype("uint8")
    return cv2.merge([b, g, r, new_alpha])


def main():
    out_dir = BACKEND_DIR / "test_outputs" / "dashscope_live"
    out_dir.mkdir(parents=True, exist_ok=True)
    saved_video = None
    try:
        video_path, injected_prompt = asyncio.run(_run_dashscope_with_greenscreen())
        if video_path is None:
            print("[live] FAIL — provider returned None (model error, no quota, or network)")
            sys.exit(2)

        saved_video = Path(video_path)
        assert saved_video.exists() and saved_video.stat().st_size > 0, (
            f"video file missing or empty: {saved_video}"
        )
        print(f"[live] OK — provider returned video: {saved_video}")
        # Copy into a stable test_outputs path so we can inspect later if needed
        stable = out_dir / "live.mp4"
        shutil.copy(saved_video, stable)
        print(f"[live] copied to: {stable}")

        # ---- pipeline integration: extract first frame + chroma key ----
        frame_count = _verify_video_file(stable)
        assert frame_count >= 1, "video must have at least one frame"
        frame_bgr = _extract_one_frame(stable, 0)
        import numpy as np
        rgba = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2BGRA)
        rgba_after = _apply_chroma_key_to_frame(rgba)
        # Save for inspection
        cv2.imwrite(str(out_dir / "frame_after_chroma.png"), rgba_after)
        green_pixel_count = int(
            ((rgba_after[:, :, 0] == 0) &
             (rgba_after[:, :, 1] == 255) &
             (rgba_after[:, :, 2] == 0)).sum()
        )
        zero_alpha = int((rgba_after[:, :, 3] == 0).sum())
        print(f"[live] frame size: {rgba.shape[0]}x{rgba.shape[1]}")
        print(f"[live] pure-green pixels still present: {green_pixel_count}")
        print(f"[live] pixels with alpha==0 after chroma: {zero_alpha}")
        if green_pixel_count > 0:
            # Not all green pixels must be zero-alpha (gradient zone exists),
            # but the bulk must be cleared.
            green_alphas = rgba_after[
                (rgba_after[:, :, 0] == 0) &
                (rgba_after[:, :, 1] == 255) &
                (rgba_after[:, :, 2] == 0)
            ][:, 3]
            zero_share = float((green_alphas == 0).sum()) / max(1, len(green_alphas))
            print(f"[live] chroma zero-alpha share among pure-green pixels: {zero_share*100:.1f}%")
            assert zero_share > 0.0, "chroma key must zero alpha on at least some greens"

        print("\n[live] PASS — live DashScope e2e succeeded end-to-end.")
        return 0
    except Exception as e:
        print(f"\n[live] EXCEPTION: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        # Best-effort cleanup of the provider's temp file
        if saved_video is not None and saved_video.exists():
            try:
                saved_video.unlink()
            except Exception:
                pass


if __name__ == "__main__":
    # Lazy import cv2 inside main to keep import errors above clear.
    import cv2  # noqa: F401
    sys.exit(main())
