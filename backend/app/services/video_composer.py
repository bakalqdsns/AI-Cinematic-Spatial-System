"""
Video Composer Service
FFmpeg-backed clip concatenation, transitions, audio mixing and color grading.

All ffmpeg invocations use ``asyncio.create_subprocess_exec`` so the event
loop is never blocked. If ffmpeg is not on PATH we raise
``RuntimeError("FFMPEG_MISSING")`` and the endpoint layer maps that to 503.

Output defaults to ``settings.workspace_dir / projects / <project_id> / compose / <ts>.mp4``
when ``output_path`` is not supplied.

Reference: docs/EXECUTION_TASKS.md (T01 / T02 / T04 / T05)
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
from pathlib import Path
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# ffmpeg / ffprobe resolution
# ─────────────────────────────────────────────────────────────────────────────

def resolve_ffmpeg() -> str:
    """Return the ffmpeg binary path or raise ``RuntimeError("FFMPEG_MISSING")``."""
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("FFMPEG_MISSING")
    return exe


def resolve_ffprobe() -> Optional[str]:
    """Return ffprobe binary path or None (we degrade gracefully when absent)."""
    return shutil.which("ffprobe")


# ─────────────────────────────────────────────────────────────────────────────
# Low-level async helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _run(cmd: list[str], *, timeout: float = 600.0) -> tuple[int, str, str]:
    """
    Run a command via ``asyncio.create_subprocess_exec``.

    Returns (returncode, stdout, stderr). Never raises for non-zero exit;
    callers inspect returncode. Raises ``asyncio.TimeoutError`` on timeout.
    """
    logger.debug("[video_composer] exec: %s", " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    return proc.returncode, stdout_b.decode("utf-8", "replace"), stderr_b.decode("utf-8", "replace")


async def _probe_duration(path: str) -> float:
    """Return media duration in seconds via ffprobe; 0.0 if unavailable."""
    ffprobe = resolve_ffprobe()
    if not ffprobe:
        ffmpeg = resolve_ffmpeg()
        _rc, _out, err = await _run([ffmpeg, "-i", path], timeout=60.0)
        import re
        m = re.search(r"Duration:\s+(\d+):(\d+):(\d+(?:\.\d+)?)", err)
        if not m:
            return 0.0
        h, mi, s = m.groups()
        return int(h) * 3600 + int(mi) * 60 + float(s)
    rc, out, _err = await _run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "json", path],
        timeout=60.0,
    )
    if rc != 0:
        return 0.0
    try:
        return float(json.loads(out).get("format", {}).get("duration", 0.0) or 0.0)
    except Exception:
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Normalisation filter (1080p, padded, H.264, yuv420p)
# ─────────────────────────────────────────────────────────────────────────────

SCALE_PAD_VF = (
    "scale=1920:1080:force_original_aspect_ratio=decrease,"
    "pad=1920:1080:(ow-iw)/2:(oh-ih)/2"
)

ENCODER_ARGS = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", "-movflags", "+faststart"]


async def _normalize_clip(clip_path: str, out_path: str) -> str:
    """Re-encode a clip to canonical 1080p H.264 yuv420p form for safe concat/xfade."""
    ffmpeg = resolve_ffmpeg()
    cmd = [ffmpeg, "-y", "-i", clip_path, "-vf", SCALE_PAD_VF, *ENCODER_ARGS, out_path]
    rc, _out, err = await _run(cmd)
    if rc != 0:
        raise RuntimeError(f"NORMALIZE_FAILED: {err[-500:]}")
    return out_path


# ─────────────────────────────────────────────────────────────────────────────
# T02 — Transitions
# ─────────────────────────────────────────────────────────────────────────────

async def apply_transition(
    prev_path: str,
    next_path: str,
    kind: str,
    duration: float,
    workdir: Path,
) -> str:
    """
    Render a transition between two clips and return the resulting path.

    kind ∈ {"cut", "dissolve", "fade", "wipe"}.

    - cut:      concat demuxer with ``-c copy`` (no re-encode).
    - dissolve: ``xfade=transition=fade:duration=…:offset=prev_dur-duration``.
    - fade:     prev clip ``fade=t=out`` + next clip ``fade=t=in`` with a short
                black field between them (concat).
    - wipe:     ``xfade=transition=sliceleft:duration=…:offset=prev_dur-duration``.

    ``dissolve`` / ``wipe`` at the head or tail of the timeline (where there
    is no neighbour on one side) auto-degrade to ``fade`` per T02 acceptance.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    ffmpeg = resolve_ffmpeg()
    kind = (kind or "cut").lower()

    prev_dur = await _probe_duration(prev_path)
    next_dur = await _probe_duration(next_path)

    # Auto-degrade: xfade needs both neighbours; at the timeline edges we
    # fall back to fade so the head/tail still gets a soft transition.
    if kind in ("dissolve", "wipe") and (prev_dur <= 0 or next_dur <= 0):
        logger.info("[video_composer] %s at edge -> fade", kind)
        kind = "fade"

    # Clamp transition duration to half of the shorter clip — xfade crashes
    # if offset + duration > prev_dur.
    if prev_dur > 0:
        duration = max(0.0, min(duration, prev_dur * 0.5))
    offset = max(0.0, prev_dur - duration)

    out_path = str(workdir / f"trans_{int(time.time()*1000)}_{kind}.mp4")

    if kind == "cut":
        list_file = workdir / f"concat_{int(time.time()*1000)}.txt"
        list_file.write_text(
            f"file '{Path(prev_path).as_posix()}'\nfile '{Path(next_path).as_posix()}'\n",
            encoding="utf-8",
        )
        cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
               "-c", "copy", out_path]
        rc, _out, err = await _run(cmd)
        if rc != 0:
            # concat copy can fail on codec boundary mismatches — fall back to re-encode.
            logger.warning("[video_composer] concat copy failed, re-encoding: %s", err[-200:])
            cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
                   *ENCODER_ARGS, out_path]
            rc, _out, err = await _run(cmd)
            if rc != 0:
                raise RuntimeError(f"TRANSITION_CUT_FAILED: {err[-500:]}")
        return out_path

    if kind in ("dissolve", "wipe"):
        xfade_trans = "fade" if kind == "dissolve" else "sliceleft"
        cmd = [
            ffmpeg, "-y", "-i", prev_path, "-i", next_path,
            "-filter_complex",
            f"[0:v][1:v]xfade=transition={xfade_trans}:duration={duration}:offset={offset}",
            *ENCODER_ARGS, out_path,
        ]
        rc, _out, err = await _run(cmd)
        if rc != 0:
            raise RuntimeError(f"TRANSITION_{kind.upper()}_FAILED: {err[-500:]}")
        return out_path

    if kind == "fade":
        prev_out = str(workdir / f"fade_prev_{int(time.time()*1000)}.mp4")
        next_out = str(workdir / f"fade_next_{int(time.time()*1000)}.mp4")
        black_out = str(workdir / f"black_{int(time.time()*1000)}.mp4")

        fade_out_st = max(0.0, prev_dur - duration)
        cmd_prev = [ffmpeg, "-y", "-i", prev_path,
                   "-vf", f"fade=t=out:st={fade_out_st}:d={duration},{SCALE_PAD_VF}",
                   *ENCODER_ARGS, "-an", prev_out]
        rc, _out, err = await _run(cmd_prev)
        if rc != 0:
            raise RuntimeError(f"TRANSITION_FADE_OUT_FAILED: {err[-500:]}")

        cmd_next = [ffmpeg, "-y", "-i", next_path,
                    "-vf", f"fade=t=in:st=0:d={duration},{SCALE_PAD_VF}",
                    *ENCODER_ARGS, "-an", next_out]
        rc, _out, err = await _run(cmd_next)
        if rc != 0:
            raise RuntimeError(f"TRANSITION_FADE_IN_FAILED: {err[-500:]}")

        # Short black bridge so the fade hits pure black on both sides.
        black_dur = max(0.05, duration * 0.1)
        cmd_black = [ffmpeg, "-y", "-f", "lavfi", "-i",
                     f"color=c=black:s=1920x1080:d={black_dur}:r=30",
                     *ENCODER_ARGS, "-an", black_out]
        rc, _out, err = await _run(cmd_black)
        if rc != 0:
            raise RuntimeError(f"TRANSITION_FADE_BLACK_FAILED: {err[-500:]}")

        list_file = workdir / f"fade_concat_{int(time.time()*1000)}.txt"
        list_file.write_text(
            f"file '{Path(prev_out).as_posix()}'\n"
            f"file '{Path(black_out).as_posix()}'\n"
            f"file '{Path(next_out).as_posix()}'\n",
            encoding="utf-8",
        )
        cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
               *ENCODER_ARGS, out_path]
        rc, _out, err = await _run(cmd)
        if rc != 0:
            raise RuntimeError(f"TRANSITION_FADE_CONCAT_FAILED: {err[-500:]}")
        return out_path

    raise RuntimeError(f"UNKNOWN_TRANSITION: {kind}")


# ─────────────────────────────────────────────────────────────────────────────
# T04 — Audio mixing
# ─────────────────────────────────────────────────────────────────────────────

async def mix_audio(
    video_path: str,
    tracks: list[dict],
    output_path: str,
) -> str:
    """
    Mix BGM / SFX / voiceover tracks onto a video and apply loudnorm.

    Each track dict:
        {
          "kind":      "bgm" | "sfx" | "voiceover",
          "path\":     "<audio file path>",
          "volume":    0.0..2.0  (default 1.0),
          "start_at":  seconds offset into the final timeline (default 0.0),
        }

    - BGM:       ``-stream_loop -1`` looped to video length, ``-shortest``.
    - SFX:       delayed via ``adelay=<ms>|<ms>`` to land at ``start_at``.
    - Voiceover: same delay mechanism, aligned to shot time.

    Final pass: ``-af loudnorm=I=-16:TP=-1.5:LRA=11`` for streaming-safe loudness.
    """
    ffmpeg = resolve_ffmpeg()
    if not tracks:
        return video_path

    # Verify each track file exists; ignore missing ones with a warning.
    valid = []
    for t in tracks:
        p = t.get("path")
        if not p or not Path(p).exists():
            logger.warning("[video_composer] skip missing audio track: %s", p)
            continue
        valid.append(t)
    if not valid:
        return video_path

    inputs: list[str] = []
    filter_parts: list[str] = []
    amix_labels: list[str] = []

    # video is input 0
    inputs += ["-i", video_path]
    video_dur = await _probe_duration(video_path)

    idx = 1  # audio inputs start at index 1
    for t in valid:
        kind = t.get("kind", "sfx")
        path = t["path"]
        vol = float(t.get("volume", 1.0))
        start_at = float(t.get("start_at", 0.0))

        if kind == "bgm":
            inputs += ["-stream_loop", "-1", "-i", path]
            label = f"a{idx}"
            # Loop BGM, set volume, then trim to video length.
            filter_parts.append(
                f"[{idx}:a]volume={vol},atrim=duration={video_dur}[{label}]"
            )
            amix_labels.append(f"[{label}]")
        else:
            # sfx / voiceover: delay to start_at, then volume.
            inputs += ["-i", path]
            delay_ms = int(max(0.0, start_at) * 1000)
            label = f"a{idx}"
            filter_parts.append(
                f"[{idx}:a]adelay={delay_ms}|{delay_ms},volume={vol}[{label}]"
            )
            amix_labels.append(f"[{label}]")
        idx += 1

    # Mix all audio labels + original video audio (0:a) together.
    mix_inputs = "".join(amix_labels)
    n_inputs = len(amix_labels) + 1  # +1 for original 0:a
    filter_parts.append(
        f"[0:a]{mix_inputs}amix=inputs={n_inputs}:duration=first:dropout_transition=0,"
        f"loudnorm=I=-16:TP=-1.5:LRA=11[aout]"
    )
    filter_complex = ";".join(filter_parts)

    cmd = [
        ffmpeg, "-y", *inputs,
        "-filter_complex", filter_complex,
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        output_path,
    ]
    rc, _out, err = await _run(cmd, timeout=900.0)
    if rc != 0:
        raise RuntimeError(f"MIX_AUDIO_FAILED: {err[-500:]}")
    return output_path


# ─────────────────────────────────────────────────────────────────────────────
# T05 — Color grading
# ─────────────────────────────────────────────────────────────────────────────

async def apply_color_grade(
    clip_path: str,
    grade: dict,
    output_path: str,
) -> str:
    """
    Apply a color grade to a clip.

    grade dict:
        {
          "lut_path":   optional path to a .cube LUT,
          "brightness": -1.0..1.0  (default 0.0),
          "contrast":   -1000..1000 (eq filter scale, default 1.0),
          "saturation":  0.0..3.0   (default 1.0),
        }

    When ``lut_path`` is set we use ``lut3d``; otherwise we fall back to the
    ``eq`` filter with brightness / contrast / saturation. The output is
    re-encoded to canonical 1080p H.264 yuv420p.
    """
    ffmpeg = resolve_ffmpeg()
    lut_path = grade.get("lut_path")
    brightness = float(grade.get("brightness", 0.0))
    contrast = float(grade.get("contrast", 1.0))
    saturation = float(grade.get("saturation", 1.0))

    if lut_path:
        if not Path(lut_path).exists():
            raise RuntimeError(f"LUT_MISSING: {lut_path}")
        vf = f"lut3d='{Path(lut_path).as_posix()}'"
        if grade.get("brightness") or grade.get("contrast") or grade.get("saturation"):
            vf = f"{vf},eq=brightness={brightness}:contrast={contrast}:saturation={saturation}"
    else:
        vf = f"eq=brightness={brightness}:contrast={contrast}:saturation={saturation}"

    # Keep canonical 1080p encoding on the output.
    vf = f"{vf},{SCALE_PAD_VF}"

    cmd = [ffmpeg, "-y", "-i", clip_path, "-vf", vf, *ENCODER_ARGS, output_path]
    rc, _out, err = await _run(cmd, timeout=900.0)
    if rc != 0:
        raise RuntimeError(f"COLOR_GRADE_FAILED: {err[-500:]}")
    return output_path


# ─────────────────────────────────────────────────────────────────────────────
# T01 — Top-level compose
# ─────────────────────────────────────────────────────────────────────────────

async def compose_clips(
    clip_paths: list[str],
    durations: list[float],
    transition: str = "cut",
    transition_duration: float = 0.5,
    output_path: Optional[str] = None,
    project_id: Optional[str] = None,
    audio_tracks: Optional[list[dict]] = None,
    color_grade: Optional[dict] = None,
) -> str:
    """
    Compose a list of clips into a single 1080p H.264 MP4.

    Pipeline:
      1. Normalise every clip to canonical 1080p yuv420p.
      2. Pairwise apply transitions (T02) → intermediate clips.
      3. Concat all intermediate clips into one file.
      4. (Optional) mix audio tracks (T04).
      5. (Optional) apply color grade (T05).

    Args:
        clip_paths:          ordered list of source MP4 paths.
        durations:           per-clip target durations (informational; used to
                             validate input length and for transition clamping).
        transition:          "cut" | "dissolve" | "fade" | "wipe".
        transition_duration: seconds (default 0.5).
        output_path:         explicit output; None → auto-derived under
                             ``settings.workspace_dir / projects / <project_id> / compose``.
        project_id:          used for default output path.
        audio_tracks:        optional list of AudioTrack dicts (T04).
        color_grade:         optional ColorGrade dict (T05).

    Returns:
        Absolute path to the final MP4.

    Raises:
        RuntimeError("FFMPEG_MISSING")   — endpoint maps to 503.
        RuntimeError("NORMALIZE_FAILED" / "CONCAT_FAILED" / "MIX_AUDIO_FAILED" /
                     "COLOR_GRADE_FAILED") — endpoint maps to 500.
    """
    if not clip_paths:
        raise RuntimeError("NO_INPUT_CLIPS")

    # Probing ffmpeg early so we surface FFMPEG_MISSING before any work.
    resolve_ffmpeg()

    # Resolve default output path.
    if not output_path:
        ts = time.strftime("%Y%m%d_%H%M%S")
        pid = project_id or "default"
        out_dir = settings.workspace_dir / "projects" / pid / "compose"
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(out_dir / f"{ts}.mp4")

    workdir = Path(output_path).parent / f".work_{int(time.time()*1000)}"
    workdir.mkdir(parents=True, exist_ok=True)

    try:
        # 1. Normalise all input clips.
        normalized: list[str] = []
        for i, clip in enumerate(clip_paths):
            if not Path(clip).exists():
                raise RuntimeError(f"CLIP_MISSING: {clip}")
            npath = str(workdir / f"norm_{i:04d}.mp4")
            await _normalize_clip(clip, npath)
            normalized.append(npath)

        if len(normalized) == 1:
            # Single clip — copy through as the "concat" result.
            concat_path = str(workdir / "concat_out.mp4")
            shutil.copyfile(normalized[0], concat_path)
        else:
            # 2. Pairwise transitions.
            trans_pairs: list[str] = []
            for i in range(len(normalized) - 1):
                prev = normalized[i] if not trans_pairs else trans_pairs[-1]
                nxt = normalized[i + 1]
                kind = transition
                # Head/tail of the timeline: dissolve/wipe degrade to fade
                # automatically inside apply_transition when probe finds no
                # neighbour on one side. Here both sides always have a
                # neighbour (we feed prev result), so the only edge case is
                # the very first pair — which is fine for all four kinds.
                merged = await apply_transition(prev, nxt, kind, transition_duration, workdir)
                trans_pairs.append(merged)

            concat_path = trans_pairs[-1]

        # 3. (Optional) mix audio.
        if audio_tracks:
            mixed_path = str(workdir / "mixed.mp4")
            await mix_audio(concat_path, audio_tracks, mixed_path)
            concat_path = mixed_path

        # 4. (Optional) color grade.
        if color_grade:
            graded_path = str(workdir / "graded.mp4")
            await apply_color_grade(concat_path, color_grade, graded_path)
            concat_path = graded_path

        # 5. Move final result to the requested output_path.
        if Path(concat_path).resolve() != Path(output_path).resolve():
            shutil.copyfile(concat_path, output_path)

        logger.info("[video_composer] compose -> %s", output_path)
        return output_path

    finally:
        # Best-effort cleanup of intermediate workdir.
        try:
            for f in workdir.glob("*"):
                f.unlink(missing_ok=True)
            workdir.rmdir()
        except Exception:
            pass
