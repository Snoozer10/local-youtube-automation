from __future__ import annotations

import subprocess


def _probe_encoder(encoder_name: str) -> bool:
    try:
        test_cmd = [
            "ffmpeg",
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
        result = subprocess.run(test_cmd, capture_output=True, timeout=5)
        return result.returncode == 0
    except Exception:
        return False


def _build_encoder_config(encoder: str, config: dict) -> dict:
    base = {
        "video_codec": encoder,
        "encoder_name": encoder,
        "hwaccel": "qsv" if "qsv" in encoder else ("cuda" if "nvenc" in encoder else "none"),
        "encoder_args": [],
    }

    if encoder == "h264_qsv":
        base["encoder_args"] = [
            "-preset",
            config["QSV_PRESET"],
            "-global_quality",
            str(config["QSV_GLOBAL_QUALITY"]),
            "-look_ahead",
            "0",  # Enforced QSV_LOOKAHEAD=0
            "-look_ahead_depth",
            str(config["QSV_LOOKAHEAD_DEPTH"]),
        ]
        if config["ENABLE_VBV"]:
            base["encoder_args"].extend(
                ["-maxrate", config["VBV_MAXRATE"], "-bufsize", config["VBV_BUFSIZE"]]
            )

    elif encoder == "h264_nvenc":
        base["encoder_args"] = [
            "-preset",
            config["NVENC_PRESET"],
            "-cq",
            str(config["NVENC_CQ"]),
            "-rc",
            config["NVENC_RC"],
            "-multipass",
            config["NVENC_MULTIPASS"],
            "-spatial_aq",
            str(config["NVENC_SPATIAL_AQ"]),
            "-temporal_aq",
            str(config["NVENC_TEMPORAL_AQ"]),
        ]
        if config["ENABLE_VBV"]:
            base["encoder_args"].extend(
                ["-maxrate", config["VBV_MAXRATE"], "-bufsize", config["VBV_BUFSIZE"]]
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
        if config["ENABLE_VBV"]:
            base["encoder_args"].extend(
                ["-maxrate", config["VBV_MAXRATE"], "-bufsize", config["VBV_BUFSIZE"]]
            )

    fps = int(config["OUTPUT_FPS"])
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
            str(config["FFMPEG_THREADS"]),
        ]
    )

    return base


def detect_hardware_encoder(config: dict) -> dict:
    if config.get("ENCODER_FORCE"):
        return _build_encoder_config(config["ENCODER_FORCE"], config)

    if config.get("ENABLE_HARDWARE_ENCODER", True):
        # ADR 0002: Prioritize Intel QuickSync (h264_qsv) including 1440p master via format=nv12
        if _probe_encoder("h264_qsv"):
            return _build_encoder_config("h264_qsv", config)
        if _probe_encoder("h264_nvenc"):
            return _build_encoder_config("h264_nvenc", config)

    return _build_encoder_config("libx264", config)


