from __future__ import annotations

import subprocess
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from .runner import MediaRunner


class EncoderConfig(TypedDict):
    video_codec: str
    encoder_name: str
    hwaccel: str
    encoder_args: list[str]


def _probe_encoder(encoder_name: str, runner: MediaRunner | None = None) -> bool:
    test_args = [
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=s=64x64:d=0.04",
        "-c:v",
        encoder_name,
        "-f",
        "null",
        "-",
    ]
    if runner is not None:
        try:
            runner.run_ffmpeg(test_args, timeout=5.0)
            return True
        except Exception:
            return False

    try:
        test_cmd = ["ffmpeg"] + test_args
        result = subprocess.run(test_cmd, capture_output=True, timeout=5)
        return result.returncode == 0
    except Exception:
        return False


def _build_encoder_config(encoder: str, config: Mapping[str, Any]) -> EncoderConfig:
    base: EncoderConfig = {
        "video_codec": encoder,
        "encoder_name": encoder,
        "hwaccel": "qsv" if "qsv" in encoder else ("cuda" if "nvenc" in encoder else "none"),
        "encoder_args": [],
    }

    if encoder == "h264_qsv":
        base["encoder_args"] = [
            "-preset",
            str(config.get("QSV_PRESET", "fast")),
            "-global_quality",
            str(config.get("QSV_GLOBAL_QUALITY", 22)),
            "-look_ahead",
            "0",  # Enforced QSV_LOOKAHEAD=0
            "-look_ahead_depth",
            str(config.get("QSV_LOOKAHEAD_DEPTH", 20)),
        ]
        if config.get("ENABLE_VBV", True):
            base["encoder_args"].extend(
                [
                    "-maxrate",
                    str(config.get("VBV_MAXRATE", "8000k")),
                    "-bufsize",
                    str(config.get("VBV_BUFSIZE", "16000k")),
                ]
            )

    elif encoder == "h264_nvenc":
        base["encoder_args"] = [
            "-preset",
            str(config.get("NVENC_PRESET", "p4")),
            "-cq",
            str(config.get("NVENC_CQ", 22)),
            "-rc",
            str(config.get("NVENC_RC", "vbr")),
            "-multipass",
            str(config.get("NVENC_MULTIPASS", "fullres")),
            "-spatial_aq",
            str(config.get("NVENC_SPATIAL_AQ", 1)),
            "-temporal_aq",
            str(config.get("NVENC_TEMPORAL_AQ", 1)),
        ]
        if config.get("ENABLE_VBV", True):
            base["encoder_args"].extend(
                [
                    "-maxrate",
                    str(config.get("VBV_MAXRATE", "8000k")),
                    "-bufsize",
                    str(config.get("VBV_BUFSIZE", "16000k")),
                ]
            )

    else:  # libx264 CPU (Master 2D Animation Profile)
        target_level = (
            "5.1"
            if int(config.get("OUTPUT_HEIGHT", 1080)) >= 1440
            else config.get("OUTPUT_LEVEL", "4.1")
        )
        base["encoder_args"] = [
            "-preset",
            config.get("CPU_PRESET", "veryfast"),
            "-crf",
            str(config.get("CPU_CRF", 17)),
            "-tune",
            "animation",  # Crucial: Preserves flat color planes and crisp vector lines
            "-profile:v",
            "high",
            "-level",
            target_level,
            "-x264-params",
            "bframes=4:b-adapt=2:ref=4:aq-mode=3",  # Eliminates flat-color banding
        ]
        if config.get("ENABLE_VBV", True):
            base["encoder_args"].extend(
                [
                    "-maxrate",
                    str(config.get("VBV_MAXRATE", "8000k")),
                    "-bufsize",
                    str(config.get("VBV_BUFSIZE", "16000k")),
                ]
            )

    fps = int(config.get("OUTPUT_FPS", 30))
    target_pix_fmt = "nv12" if "qsv" in encoder else config.get("OUTPUT_PIX_FMT", "yuv420p")
    base["encoder_args"].extend(
        [
            "-pix_fmt",
            target_pix_fmt,
            "-colorspace",
            "bt709",
            "-color_primaries",
            "bt709",
            "-color_trc",
            "bt709",
            "-color_range",
            "tv",
            "-r",
            str(fps),
            "-fps_mode",
            "cfr",
            "-video_track_timescale",
            str(fps * 1000),
            "-g",
            str(fps * 2),
            "-keyint_min",
            str(fps),
            "-flags",
            "+cgop",
            "-avoid_negative_ts",
            "make_zero",
            "-fflags",
            "+genpts",
            "-movflags",
            "+faststart",
            "-threads",
            str(config.get("FFMPEG_THREADS", 4)),
        ]
    )

    return base


def detect_hardware_encoder(
    config: Mapping[str, Any],
    runner: MediaRunner | None = None,
) -> EncoderConfig:
    if runner is None:
        from .runner import SubprocessMediaRunner, get_default_runner
        default_runner = get_default_runner()
        if not isinstance(default_runner, SubprocessMediaRunner):
            runner = default_runner

    if config.get("ENCODER_FORCE"):
        return _build_encoder_config(config["ENCODER_FORCE"], config)

    if config.get("ENABLE_HARDWARE_ENCODER", True):
        # ADR 0002: Prioritize Intel QuickSync (h264_qsv) including 1440p master via format=nv12
        qsv_ok = _probe_encoder("h264_qsv", runner) if runner is not None else _probe_encoder("h264_qsv")
        if qsv_ok:
            return _build_encoder_config("h264_qsv", config)
        nvenc_ok = _probe_encoder("h264_nvenc", runner) if runner is not None else _probe_encoder("h264_nvenc")
        if nvenc_ok:
            return _build_encoder_config("h264_nvenc", config)

    return _build_encoder_config("libx264", config)
