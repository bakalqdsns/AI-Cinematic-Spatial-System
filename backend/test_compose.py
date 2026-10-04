"""
Pytest tests for the video composition pipeline (T01 / T02 / T04 / T05).

These tests are skipped automatically when ffmpeg is not available on PATH
so CI environments without ffmpeg don't fail. Generate sample clips with:

    py -c "import test_compose; test_compose._ensure_sample_clips()"

or just run pytest — the fixture creates the samples on demand.
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

from app.services.video_composer import (
    apply_color_grade,
    apply_transition,
    compose_clips,
    mix_audio,
    resolve_ffmpeg,
)

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None
FFPROBE_AVAILABLE = shutil.which("ffprobe") is not None

# Tests that actually invoke ffmpeg are marked here. The OpenAPI schema
# test below does NOT need ffmpeg and runs unconditionally.
ffmpeg_required = pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg not on PATH")


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_test_clip(path: Path, duration: float = 5.0, color: str = "red") -> None:
    """Generate a small test MP4 via ffmpeg lavfi (color source + sine tone)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = resolve_ffmpeg()
    cmd = [
        ffmpeg, "-y",
        "-f", "lavfi", "-i", f"color=c={color}:s=1280x720:d={duration}:r=30",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        str(path),
    ]
    rc, _out, err = asyncio.run(_run_for_test(cmd))
    assert rc == 0, f"failed to create test clip {path}: {err[-300:]}"


async def _run_for_test(cmd: list[str], timeout: float = 60.0):
    import asyncio as _aio
    proc = await _aio.create_subprocess_exec(
        *cmd, stdout=_aio.subprocess.PIPE, stderr=_aio.subprocess.PIPE,
    )
    out_b, err_b = await _aio.wait_for(proc.communicate(), timeout=timeout)
    return proc.returncode, out_b.decode("utf-8", "replace"), err_b.decode("utf-8", "replace")


def _make_wav(path: Path, duration: float = 5.0, freq: int = 300) -> None:
    """Generate a short WAV file via ffmpeg lavfi sine source."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = resolve_ffmpeg()
    cmd = [
        ffmpeg, "-y", "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={duration}",
        "-c:a", "pcm_s16le", str(path),
    ]
    rc, _out, err = asyncio.run(_run_for_test(cmd))
    assert rc == 0, f"failed to create wav {path}: {err[-300:]}"


def _make_cube_lut(path: Path) -> None:
    """Write a minimal valid .cube LUT (identity 2x2x2)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ['TITLE "test"', 'LUT_3D_SIZE 2', ""]
    for r in range(2):
        for g in range(2):
            for b in range(2):
                lines.append(f"{r/1.0} {g/1.0} {b/1.0}")
    path.write_text("\n".join(lines), encoding="utf-8")


@pytest.fixture
def sample_clips(tmp_path: Path) -> list[str]:
    """Three 5-second MP4 clips with distinct colors."""
    paths = []
    for i, color in enumerate(["red", "lime", "blue"]):
        p = tmp_path / f"clip_{i}.mp4"
        _make_test_clip(p, duration=5.0, color=color)
        paths.append(str(p))
    return paths


@pytest.fixture
def single_clip(tmp_path: Path) -> str:
    p = tmp_path / "single.mp4"
    _make_test_clip(p, duration=5.0, color="magenta")
    return str(p)


@pytest.fixture
def bgm_track(tmp_path: Path) -> str:
    p = tmp_path / "bgm.wav"
    _make_wav(p, duration=10.0, freq=200)
    return str(p)


@pytest.fixture
def voiceover_track(tmp_path: Path) -> str:
    p = tmp_path / "voice.wav"
    _make_wav(p, duration=3.0, freq=600)
    return str(p)


@pytest.fixture
def cube_lut(tmp_path: Path) -> str:
    p = tmp_path / "grade.cube"
    _make_cube_lut(p)
    return str(p)


# ─────────────────────────────────────────────────────────────────────────────
# T01 — Core composition
# ─────────────────────────────────────────────────────────────────────────────

@ffmpeg_required
def test_compose_three_clips_cut(sample_clips, tmp_path: Path) -> None:
    """3× 5s clips → ~15s single MP4 (cut transition preserves full length)."""
    out = tmp_path / "out_cut.mp4"
    result = asyncio.run(compose_clips(
        clip_paths=sample_clips,
        durations=[5.0, 5.0, 5.0],
        transition="cut",
        transition_duration=0.5,
        output_path=str(out),
        project_id="test_proj",
    ))
    assert result == str(out)
    assert out.exists()
    assert out.stat().st_size > 0
    # ffprobe-based duration check (when available)
    if FFPROBE_AVAILABLE:
        from app.services.video_composer import _probe_duration
        dur = asyncio.run(_probe_duration(str(out)))
        # cut concat should preserve total length within ~0.5s tolerance.
        assert 14.0 <= dur <= 16.0, f"unexpected duration {dur}"


@ffmpeg_required
def test_compose_single_clip(single_clip, tmp_path: Path) -> None:
    """Single clip input still produces a valid output."""
    out = tmp_path / "out_single.mp4"
    result = asyncio.run(compose_clips(
        clip_paths=[single_clip],
        durations=[5.0],
        transition="cut",
        output_path=str(out),
        project_id="test_proj",
    ))
    assert result == str(out)
    assert out.exists()


@ffmpeg_required
def test_compose_default_output_path(sample_clips, tmp_path: Path, monkeypatch) -> None:
    """When output_path is None, the composer derives a path under workspace/projects/<pid>/compose."""
    from app.config import settings
    monkeypatch.setattr(settings, "workspace_dir", tmp_path)
    result = asyncio.run(compose_clips(
        clip_paths=sample_clips,
        durations=[5.0, 5.0, 5.0],
        transition="cut",
        project_id="proj_xyz",
    ))
    assert "projects" in result and "proj_xyz" in result and "compose" in result
    assert Path(result).exists()


@ffmpeg_required
def test_compose_ffmpeg_missing(monkeypatch, sample_clips, tmp_path: Path) -> None:
    """When ffmpeg is not resolvable, the composer raises FFMPEG_MISSING."""
    import app.services.video_composer as vc
    monkeypatch.setattr(vc, "resolve_ffmpeg", lambda: (_ for _ in ()).throw(RuntimeError("FFMPEG_MISSING")))
    with pytest.raises(RuntimeError, match="FFMPEG_MISSING"):
        asyncio.run(compose_clips(
            clip_paths=sample_clips,
            durations=[5.0, 5.0, 5.0],
            output_path=str(tmp_path / "x.mp4"),
        ))


# ─────────────────────────────────────────────────────────────────────────────
# T02 — Transitions
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("kind", ["cut", "dissolve", "fade", "wipe"])
@ffmpeg_required
def test_apply_transition_all_kinds(sample_clips, tmp_path: Path, kind: str) -> None:
    """Each of the four transition kinds produces a playable MP4."""
    workdir = tmp_path / "work"
    workdir.mkdir()
    out = asyncio.run(apply_transition(
        sample_clips[0], sample_clips[1], kind, 0.5, workdir,
    ))
    assert Path(out).exists()
    assert Path(out).stat().st_size > 0


@ffmpeg_required
def test_compose_each_transition_kind(sample_clips, tmp_path: Path) -> None:
    """compose_clips with each transition kind returns a valid file."""
    for kind in ["cut", "dissolve", "fade", "wipe"]:
        out = tmp_path / f"out_{kind}.mp4"
        result = asyncio.run(compose_clips(
            clip_paths=sample_clips,
            durations=[5.0, 5.0, 5.0],
            transition=kind,
            transition_duration=0.5,
            output_path=str(out),
            project_id="test_proj",
        ))
        assert Path(result).exists(), f"{kind} did not produce output"
        assert Path(result).stat().st_size > 0


# ─────────────────────────────────────────────────────────────────────────────
# T04 — Audio mixing
# ─────────────────────────────────────────────────────────────────────────────

@ffmpeg_required
def test_mix_audio_bgm_and_voiceover(sample_clips, bgm_track, voiceover_track, tmp_path: Path) -> None:
    """Given BGM + voiceover, the composed output contains a mixed audio track."""
    out = tmp_path / "out_audio.mp4"
    result = asyncio.run(compose_clips(
        clip_paths=sample_clips,
        durations=[5.0, 5.0, 5.0],
        transition="cut",
        output_path=str(out),
        project_id="test_proj",
        audio_tracks=[
            {"kind": "bgm", "path": bgm_track, "volume": 0.6, "start_at": 0.0},
            {"kind": "voiceover", "path": voiceover_track, "volume": 1.0, "start_at": 2.0},
        ],
    ))
    assert Path(result).exists()
    # Probe audio stream presence via ffprobe when available.
    if FFPROBE_AVAILABLE:
        from app.services.video_composer import _probe_duration, resolve_ffprobe
        ffprobe = resolve_ffprobe()
        rc, out_s, _err = asyncio.run(_run_for_test(
            [ffprobe, "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=codec_type", "-of", "json", result]
        ))
        assert rc == 0
        import json
        info = json.loads(out_s)
        streams = info.get("streams", [])
        assert any(s.get("codec_type") == "audio" for s in streams), "no audio stream in output"


@ffmpeg_required
def test_mix_audio_empty_tracks_passthrough(sample_clips, tmp_path: Path) -> None:
    """Empty audio_tracks list is a no-op (video still composed)."""
    out = tmp_path / "out_noaudio.mp4"
    result = asyncio.run(compose_clips(
        clip_paths=sample_clips,
        durations=[5.0, 5.0, 5.0],
        transition="cut",
        output_path=str(out),
        project_id="test_proj",
        audio_tracks=[],
    ))
    assert Path(result).exists()


# ─────────────────────────────────────────────────────────────────────────────
# T05 — Color grading
# ─────────────────────────────────────────────────────────────────────────────

@ffmpeg_required
def test_apply_color_grade_with_lut(single_clip, cube_lut, tmp_path: Path) -> None:
    """A .cube LUT is applied and the output is a playable MP4."""
    out = tmp_path / "graded_lut.mp4"
    result = asyncio.run(apply_color_grade(
        single_clip,
        {"lut_path": cube_lut, "brightness": 0.0, "contrast": 1.0, "saturation": 1.0},
        str(out),
    ))
    assert Path(result).exists()
    assert Path(result).stat().st_size > 0


@ffmpeg_required
def test_apply_color_grade_eq_only(single_clip, tmp_path: Path) -> None:
    """Brightness / contrast / saturation via eq filter produces a valid MP4."""
    out = tmp_path / "graded_eq.mp4"
    result = asyncio.run(apply_color_grade(
        single_clip,
        {"brightness": 0.05, "contrast": 1.1, "saturation": 1.2},
        str(out),
    ))
    assert Path(result).exists()
    assert Path(result).stat().st_size > 0


@ffmpeg_required
def test_compose_with_color_grade(sample_clips, cube_lut, tmp_path: Path) -> None:
    """End-to-end: compose with colorGrade produces a graded MP4."""
    out = tmp_path / "out_graded.mp4"
    result = asyncio.run(compose_clips(
        clip_paths=sample_clips,
        durations=[5.0, 5.0, 5.0],
        transition="cut",
        output_path=str(out),
        project_id="test_proj",
        color_grade={"lut_path": cube_lut, "brightness": 0.0, "contrast": 1.0, "saturation": 1.1},
    ))
    assert Path(result).exists()


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint / OpenAPI smoke test
# ─────────────────────────────────────────────────────────────────────────────

def test_endpoint_response_model_in_openapi() -> None:
    """The /compose endpoint declares ComposeResponse in OpenAPI schema."""
    from fastapi import FastAPI
    from app.endpoints_compose import router, ComposeResponse

    app = FastAPI()
    app.include_router(router)
    schema = app.openapi()
    paths = schema.get("paths", {})
    path_key = "/api/aicss/v2/projects/{project_id}/compose"
    assert path_key in paths, "compose path not registered"
    post_op = paths[path_key]["post"]
    # The response should reference ComposeResponse schema.
    ref = post_op["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert "ComposeResponse" in ref
    assert "ComposeResponse" in schema.get("components", {}).get("schemas", {})
