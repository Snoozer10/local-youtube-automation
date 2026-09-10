"""Unit tests for tools/run_canary_benchmark.py.

Validates:
1. Target canary frame selection (Frames 1, 15, 60, 150, 264).
2. Comparison row generation and metric aggregation.
3. Markdown report formatting.
"""

import pytest

from tools.run_canary_benchmark import (
    build_canary_comparison_row,
    format_comparison_markdown_table,
    select_canary_frames,
)


def test_select_canary_frames():
    mock_frames = [{"index": i, "timestamp": f"[{i:02d}:00]"} for i in range(1, 300)]
    selected = select_canary_frames(mock_frames, target_indices=[1, 15, 60, 150, 264])
    assert len(selected) == 5
    assert [f["index"] for f in selected] == [1, 15, 60, 150, 264]


def test_select_canary_frames_missing_index():
    mock_frames = [{"index": 1}, {"index": 15}]
    selected = select_canary_frames(mock_frames, target_indices=[1, 15, 999])
    assert len(selected) == 2
    assert [f["index"] for f in selected] == [1, 15]


def test_build_canary_comparison_row():
    row = build_canary_comparison_row(
        frame_idx=1,
        timestamp="[00:00]",
        archetype="Scientific Rigor",
        baseline_text="Host in studio",
        socratic_text="Host in studio with 1-2-3 shape hierarchy and Sfumato",
        has_text_collision=False,
        ocr_text_found="",
        upper_80_clear=True,
    )
    assert row["frame_index"] == 1
    assert row["archetype"] == "Scientific Rigor"
    assert row["upper_80_clear"] is True
    assert row["has_text_collision"] is False


def test_format_comparison_markdown_table():
    rows = [
        {
            "frame_index": 1,
            "timestamp": "[00:00]",
            "archetype": "Host Hook",
            "has_text_collision": False,
            "upper_80_clear": True,
            "ocr_text_found": "NONE",
            "socratic_features": "1-2-3 shape hierarchy, Sfumato chiaroscuro, 24mm optics",
        },
        {
            "frame_index": 15,
            "timestamp": "[00:45]",
            "archetype": "Debunk Dissection",
            "has_text_collision": False,
            "upper_80_clear": True,
            "ocr_text_found": "NONE",
            "socratic_features": "Bifurcated stage, 1-2-3 shape hierarchy",
        },
    ]
    md = format_comparison_markdown_table(rows)
    assert "| Frame |" in md
    assert "Host Hook" in md
    assert "Debunk Dissection" in md
    assert "PASS" in md
