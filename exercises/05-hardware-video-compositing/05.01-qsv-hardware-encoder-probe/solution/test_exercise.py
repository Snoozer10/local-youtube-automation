"""Unit & Diagnostic Drill Tests for 05.01 Intel QSV Hardware Encoder Probe."""

from typing import Any

import pytest

from .exercise import (
    build_encoder_arguments,
    probe_ffmpeg_encoder,
    select_encoder_with_fallback,
)


@pytest.mark.drill
def test_qsv_encoder_invariants_lookahead_zero_and_nv12() -> None:
    config: dict[str, Any] = {
        "OUTPUT_FPS": 30,
        "OUTPUT_HEIGHT": 1080,
        "FFMPEG_THREADS": 4,
        "QSV_PRESET": "medium",
        "QSV_GLOBAL_QUALITY": 23,
        "QSV_LOOKAHEAD_DEPTH": 40,
        "ENABLE_VBV": False,
    }

    result = build_encoder_arguments("h264_qsv", config)
    assert result["video_codec"] == "h264_qsv"
    assert result["hwaccel"] == "qsv"

    args = result["encoder_args"]

    # Invariant 1: QSV_LOOKAHEAD must be pinned to 0
    assert "-look_ahead" in args
    idx_lookahead = args.index("-look_ahead")
    assert args[idx_lookahead + 1] == "0"

    # Invariant 2: format=nv12 must be enforced
    assert "-pix_fmt" in args
    idx_pixfmt = args.index("-pix_fmt")
    assert args[idx_pixfmt + 1] == "nv12"


@pytest.mark.drill
def test_cpu_libx264_animation_tuning() -> None:
    config: dict[str, Any] = {
        "OUTPUT_FPS": 30,
        "OUTPUT_HEIGHT": 1080,
        "FFMPEG_THREADS": 4,
        "ENABLE_VBV": False,
    }

    result = build_encoder_arguments("libx264", config)
    assert result["hwaccel"] == "none"

    args = result["encoder_args"]
    assert "-tune" in args
    idx_tune = args.index("-tune")
    assert args[idx_tune + 1] == "animation"


@pytest.mark.drill
def test_fallback_hierarchy_resolution() -> None:
    config: dict[str, Any] = {
        "OUTPUT_FPS": 30,
        "OUTPUT_HEIGHT": 1080,
        "FFMPEG_THREADS": 4,
        "QSV_PRESET": "medium",
        "QSV_GLOBAL_QUALITY": 23,
        "QSV_LOOKAHEAD_DEPTH": 40,
        "ENABLE_VBV": False,
        "ENABLE_HARDWARE_ENCODER": True,
    }

    # Case A: QSV is available
    res_qsv = select_encoder_with_fallback(config, probe_fn=lambda enc: enc == "h264_qsv")
    assert res_qsv["video_codec"] == "h264_qsv"

    # Case B: QSV unavailable, NVENC available
    res_nvenc = select_encoder_with_fallback(config, probe_fn=lambda enc: enc == "h264_nvenc")
    assert res_nvenc["video_codec"] == "h264_nvenc"

    # Case C: Hardware encoders unavailable -> fallback to libx264
    res_cpu = select_encoder_with_fallback(config, probe_fn=lambda enc: False)
    assert res_cpu["video_codec"] == "libx264"

    # Case D: Forced encoder takes priority
    cfg_forced = dict(config, ENCODER_FORCE="libx264")
    res_forced = select_encoder_with_fallback(cfg_forced, probe_fn=lambda enc: True)
    assert res_forced["video_codec"] == "libx264"


@pytest.mark.drill
def test_synthetic_ffmpeg_probe_execution() -> None:
    """Diagnostic check executing the actual FFmpeg synthetic color pipeline."""
    # libx264 is guaranteed to exist on standard FFmpeg installations
    libx264_ok = probe_ffmpeg_encoder("libx264")
    assert isinstance(libx264_ok, bool)

    # h264_qsv probe returns bool indicating whether Intel silicon is present
    qsv_ok = probe_ffmpeg_encoder("h264_qsv")
    assert isinstance(qsv_ok, bool)
