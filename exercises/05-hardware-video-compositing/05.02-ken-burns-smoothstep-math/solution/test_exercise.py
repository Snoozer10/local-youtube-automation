"""Unit & Diagnostic Drill Tests for 05.02 Ken Burns Smoothstep Math."""

import math
from typing import Any

import pytest

from .exercise import (
    build_filter_expression,
    calculate_pace_modulated_zoom,
    cubic_hermite_smoothstep,
)


@pytest.mark.drill
def test_smoothstep_boundary_and_inflection_values() -> None:
    # S(0) = 0, S(1) = 1, S(0.5) = 0.5
    assert math.isclose(cubic_hermite_smoothstep(0.0), 0.0, abs_tol=1e-6)
    assert math.isclose(cubic_hermite_smoothstep(1.0), 1.0, abs_tol=1e-6)
    assert math.isclose(cubic_hermite_smoothstep(0.5), 0.5, abs_tol=1e-6)

    # Clamping behavior for out-of-bounds t
    assert cubic_hermite_smoothstep(-1.0) == 0.0
    assert cubic_hermite_smoothstep(2.0) == 1.0


@pytest.mark.drill
def test_smoothstep_zero_first_derivatives_at_boundaries() -> None:
    # First derivative S'(t) = 6t - 6t^2. At t=0 and t=1, S'(t) == 0.
    eps = 1e-4
    deriv_start = (cubic_hermite_smoothstep(eps) - cubic_hermite_smoothstep(0.0)) / eps
    deriv_end = (cubic_hermite_smoothstep(1.0) - cubic_hermite_smoothstep(1.0 - eps)) / eps

    assert math.isclose(deriv_start, 0.0, abs_tol=1e-3)
    assert math.isclose(deriv_end, 0.0, abs_tol=1e-3)


@pytest.mark.drill
def test_smoothstep_strict_monotonic_growth() -> None:
    steps = 100
    values = [cubic_hermite_smoothstep(i / steps) for i in range(steps + 1)]

    for idx in range(len(values) - 1):
        assert values[idx] <= values[idx + 1]


@pytest.mark.drill
def test_speech_paced_zoom_modulation_limits() -> None:
    duration = 4.0  # seconds

    # Baseline pace (3.0 WPS) -> pace_ratio = 1.0
    zoom_baseline = calculate_pace_modulated_zoom(
        duration=duration,
        words_per_second=3.0,
        zoom_min=1.0,
        zoom_max=1.10,
    )
    assert math.isclose(zoom_baseline, 1.09, abs_tol=1e-2)

    # Fast speech (4.5 WPS) -> increases zoom punch, clamped within [1.0, 1.15]
    zoom_fast = calculate_pace_modulated_zoom(
        duration=duration,
        words_per_second=4.5,
        zoom_min=1.0,
        zoom_max=1.10,
    )
    assert zoom_fast > zoom_baseline
    assert zoom_fast <= 1.15

    # Slow speech (1.5 WPS) -> gentle drift
    zoom_slow = calculate_pace_modulated_zoom(
        duration=duration,
        words_per_second=1.5,
        zoom_min=1.0,
        zoom_max=1.10,
    )
    assert zoom_slow < zoom_baseline
    assert zoom_slow >= 1.0


@pytest.mark.drill
def test_production_ken_burns_filter_string_synthesis() -> None:
    config: dict[str, Any] = {
        "OUTPUT_FPS": 30,
        "OUTPUT_WIDTH": 1920,
        "OUTPUT_HEIGHT": 1080,
        "KEN_BURNS_ZOOM_MIN": 1.0,
        "KEN_BURNS_ZOOM_MAX": 1.10,
        "KEN_BURNS_DYNAMIC_SCALE": True,
        "KEN_BURNS_UPSCALE_FACTOR": 1.12,
    }

    # Zoom in action
    filter_in = build_filter_expression(config, frame_count=90, camera_action="zoom_in", words_per_second=3.0)
    assert "zoompan=z='min(" in filter_in
    assert "d=90:s=1920x1080:fps=30" in filter_in
    assert "scale=out_color_matrix=bt709" in filter_in

    # Static action
    filter_static = build_filter_expression(config, frame_count=90, camera_action="static")
    assert "zoompan=z='1.0'" in filter_static
