"""Drill 05.01: Intel QSV Hardware Encoder Probe (Reference Solution).

Directly leverages the production video encoder engine from:
- src.youtube_automation.video.encoder
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.youtube_automation.video.encoder import (
    _build_encoder_config as prod_build_encoder_config,
)
from src.youtube_automation.video.encoder import (
    _probe_encoder as prod_probe_encoder,
)
from src.youtube_automation.video.encoder import (
    detect_hardware_encoder as prod_detect_hardware_encoder,
)


def probe_ffmpeg_encoder(encoder_name: str, timeout: float = 5.0) -> bool:
    """Probes an FFmpeg video encoder using a synthetic 1-frame color input."""
    return prod_probe_encoder(encoder_name)


def build_encoder_arguments(encoder: str, config: dict[str, Any]) -> dict[str, Any]:
    """Builds encoder argument dictionary and enforces QSV invariants."""
    # Ensure baseline required keys in config
    cfg = dict(config)
    cfg.setdefault("OUTPUT_FPS", 30)
    cfg.setdefault("OUTPUT_HEIGHT", 1080)
    cfg.setdefault("FFMPEG_THREADS", 4)
    cfg.setdefault("QSV_PRESET", "medium")
    cfg.setdefault("QSV_GLOBAL_QUALITY", 23)
    cfg.setdefault("QSV_LOOKAHEAD_DEPTH", 40)
    cfg.setdefault("NVENC_PRESET", "p4")
    cfg.setdefault("NVENC_CQ", 23)
    cfg.setdefault("NVENC_RC", "vbr")
    cfg.setdefault("NVENC_MULTIPASS", "qres")
    cfg.setdefault("NVENC_SPATIAL_AQ", 1)
    cfg.setdefault("NVENC_TEMPORAL_AQ", 1)
    cfg.setdefault("ENABLE_VBV", False)

    return prod_build_encoder_config(encoder, cfg)


def select_encoder_with_fallback(
    config: dict[str, Any],
    probe_fn: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    """Selects video encoder respecting user force or fallback hierarchy."""
    if probe_fn is None:
        return prod_detect_hardware_encoder(config)

    # Custom probe test harness emulation
    cfg = dict(config)
    if cfg.get("ENCODER_FORCE"):
        return build_encoder_arguments(cfg["ENCODER_FORCE"], cfg)

    if cfg.get("ENABLE_HARDWARE_ENCODER", True):
        if probe_fn("h264_qsv"):
            return build_encoder_arguments("h264_qsv", cfg)
        if probe_fn("h264_nvenc"):
            return build_encoder_arguments("h264_nvenc", cfg)

    return build_encoder_arguments("libx264", cfg)
