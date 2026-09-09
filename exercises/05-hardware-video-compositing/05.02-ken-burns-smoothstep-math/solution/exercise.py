"""Drill 05.02: Ken Burns Smoothstep Math & Speech Pacing (Reference Solution).

Directly leverages the production Ken Burns camera motion engine from:
- src.youtube_automation.video.ken_burns
"""

from __future__ import annotations

from typing import Any

from src.youtube_automation.video.ken_burns import (
    build_ken_burns_filter as prod_build_ken_burns_filter,
)


def cubic_hermite_smoothstep(t: float) -> float:
    """Evaluates the Cubic Hermite Smoothstep function: S(t) = 3*t^2 - 2*t^3."""
    clamped_t = max(0.0, min(1.0, float(t)))
    return clamped_t * clamped_t * (3.0 - 2.0 * clamped_t)


def calculate_pace_modulated_zoom(
    duration: float,
    words_per_second: float = 3.0,
    zoom_min: float = 1.0,
    zoom_max: float = 1.10,
    dynamic_enabled: bool = True,
) -> float:
    """Calculates speech-paced maximum zoom limit matching the production engine."""
    if not dynamic_enabled:
        effective_max = zoom_max
    else:
        # Dynamic duration-based scale: clamp(1.06 + (duration - 2.5)/2.0 * 0.04, 1.06, 1.10)
        dynamic_scale = round(max(1.06, min(1.10, 1.06 + (duration - 2.5) / 2.0 * 0.04)), 3)
        effective_max = min(dynamic_scale, zoom_max)

    wps = 3.0 if words_per_second is None else float(words_per_second)
    pace_ratio = max(0.75, min(1.35, wps / 3.0))

    if dynamic_enabled:
        if pace_ratio == 1.0:
            return float(effective_max)
        else:
            return float(
                round(min(1.15, zoom_min + (effective_max - zoom_min) * pace_ratio), 4)
            )
    return float(effective_max)


def generate_smoothstep_ffmpeg_expression(den: int) -> str:
    """Constructs the symbolic FFmpeg zoompan easing expression."""
    t = f"((on-1)/{den})"
    return f"({t}*{t}*(3-2*{t}))"


def build_filter_expression(
    config: dict[str, Any],
    frame_count: int,
    camera_action: str,
    words_per_second: float = 3.0,
) -> str:
    """Invokes production build_ken_burns_filter."""
    cfg = dict(config)
    cfg.setdefault("OUTPUT_FPS", 30)
    cfg.setdefault("OUTPUT_WIDTH", 1920)
    cfg.setdefault("OUTPUT_HEIGHT", 1080)
    cfg.setdefault("KEN_BURNS_ZOOM_MIN", 1.0)
    cfg.setdefault("KEN_BURNS_ZOOM_MAX", 1.10)
    cfg.setdefault("KEN_BURNS_DYNAMIC_SCALE", True)
    cfg.setdefault("KEN_BURNS_UPSCALE_FACTOR", 1.12)

    return prod_build_ken_burns_filter(
        cfg,
        frame_count=frame_count,
        camera_action=camera_action,
        words_per_second=words_per_second,
    )
