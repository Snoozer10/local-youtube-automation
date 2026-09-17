"""Unit tests for Cumulative Integer Quantization Invariants and Canonical Timeline Ingestion (Audit §6.3, Task 3.1)."""

from __future__ import annotations

import io
import json
import os
import struct
import wave
import pytest

from src.youtube_automation.timeline.engine import get_wav_duration
from src.youtube_automation.video.compiler import (
    get_audio_duration,
    parse_image_timeline,
    prepare_synchronized_timeline,
)


def _create_dummy_wav(num_samples: int, sample_rate: int = 48000) -> bytes:
    """Generates an in-memory 16-bit mono PCM WAV payload with exact sample count."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        raw_data = struct.pack(f"<{num_samples}h", *(0 for _ in range(num_samples)))
        wf.writeframes(raw_data)
    return buf.getvalue()


def test_wav_header_duration_precision(tmp_path):
    """Verifies that get_wav_duration and get_audio_duration extract exact float duration from WAV headers."""
    # 48,000 samples at 48kHz = 1.0s exact
    wav_1s = tmp_path / "test_1s.wav"
    wav_1s.write_bytes(_create_dummy_wav(48000, 48000))

    assert get_wav_duration(str(wav_1s)) == pytest.approx(1.0, abs=1e-6)
    assert get_audio_duration(str(wav_1s)) == pytest.approx(1.0, abs=1e-6)

    # 72,000 samples at 48kHz = 1.5s exact
    wav_1_5s = tmp_path / "test_1_5s.wav"
    wav_1_5s.write_bytes(_create_dummy_wav(72000, 48000))

    assert get_wav_duration(str(wav_1_5s)) == pytest.approx(1.5, abs=1e-6)
    assert get_audio_duration(str(wav_1_5s)) == pytest.approx(1.5, abs=1e-6)


def test_canonical_timeline_ingestion_bypasses_resnapping():
    """Verifies that canonical timeline.json ingestion preserves pre-quantized bounds without re-snapping or comedic grouping."""
    run_folder = os.path.join(
        "youtube_runs", "Terrence Howard This is The Best Kept SECRET in The ENTIRE WORLD!"
    )
    timeline_json_path = os.path.join(run_folder, "timeline.json")
    if not os.path.exists(timeline_json_path):
        pytest.skip(f"Production timeline not found at {timeline_json_path}")

    with open(timeline_json_path, encoding="utf-8") as f:
        timeline_data = json.load(f)

    expected_spans = timeline_data["spans"]
    audio_duration = float(timeline_data["audio_duration"])
    fps = int(timeline_data["fps"])

    blocks = parse_image_timeline(run_folder)
    assert len(blocks) == len(expected_spans) == 293
    assert all("span" in b for b in blocks)

    sync_timeline = prepare_synchronized_timeline(blocks, audio_duration=audio_duration, fps=fps)
    assert len(sync_timeline) == 293

    # Assert 1:1 match of frame bounds against pre-quantized timeline.json
    for idx, (sync_clip, exp_span) in enumerate(zip(sync_timeline, expected_spans)):
        assert sync_clip["start_frame"] == exp_span["start_frame"], f"Span {idx} start_frame mismatch"
        assert sync_clip["end_frame"] == exp_span["end_frame"], f"Span {idx} end_frame mismatch"
        assert sync_clip["frame_count"] == exp_span["frame_count"], f"Span {idx} frame_count mismatch"


def test_cumulative_integer_quantization_zero_drift():
    """Asserts mathematical zero-drift over 40,030 frames with strict contiguous chaining."""
    run_folder = os.path.join(
        "youtube_runs", "Terrence Howard This is The Best Kept SECRET in The ENTIRE WORLD!"
    )
    timeline_json_path = os.path.join(run_folder, "timeline.json")
    if not os.path.exists(timeline_json_path):
        pytest.skip(f"Production timeline not found at {timeline_json_path}")

    blocks = parse_image_timeline(run_folder)
    sync_timeline = prepare_synchronized_timeline(blocks, audio_duration=1334.34, fps=30)

    # 1. Total frame budget exact match
    total_frames = sum(clip["frame_count"] for clip in sync_timeline)
    assert total_frames == 40030
    assert sync_timeline[-1]["end_frame"] == 40030
    assert sync_timeline[0]["start_frame"] == 0

    # 2. Strict monotonic contiguity: zero voids, zero overlaps
    for prev, cur in zip(sync_timeline, sync_timeline[1:]):
        assert cur["start_frame"] == prev["end_frame"]
        assert cur["frame_count"] == cur["end_frame"] - cur["start_frame"]
        assert cur["frame_count"] >= 1


def test_legacy_blocks_fallback_unaffected():
    """Verifies that ad-hoc image lists without 'span' continue through the acoustic snapping code path."""
    ad_hoc_blocks = [
        {"name": "00_00", "sec": 0.0, "raw_sec": 0.0},
        {"name": "00_04", "sec": 4.0, "raw_sec": 4.0},
        {"name": "00_08", "sec": 8.0, "raw_sec": 8.0},
    ]
    # No 'span' key in blocks -> routes to acoustic snapping
    sync_timeline = prepare_synchronized_timeline(ad_hoc_blocks, audio_duration=10.0, fps=30)

    assert len(sync_timeline) >= 1
    assert sum(clip["frame_count"] for clip in sync_timeline) == round(10.0 * 30)
    assert sync_timeline[0]["start_frame"] == 0
    assert sync_timeline[-1]["end_frame"] == 300


def test_multi_shot_timestamp_occurrence_isolation():
    """Verifies that multiple blocks sharing the same timestamp name receive unique occurrence indices."""
    canonical_blocks = [
        {
            "name": "01_15",
            "sec": 75.0,
            "raw_sec": 75.0,
            "span": {"start_frame": 0, "end_frame": 60, "frame_count": 60},
        },
        {
            "name": "01_15",
            "sec": 77.0,
            "raw_sec": 77.0,
            "span": {"start_frame": 60, "end_frame": 120, "frame_count": 60},
        },
        {
            "name": "01_20",
            "sec": 80.0,
            "raw_sec": 80.0,
            "span": {"start_frame": 120, "end_frame": 180, "frame_count": 60},
        },
    ]

    sync_timeline = prepare_synchronized_timeline(canonical_blocks, audio_duration=6.0, fps=30)
    assert len(sync_timeline) == 3
    assert sync_timeline[0]["name"] == "01_15"
    assert sync_timeline[0]["occurrence"] == 1
    assert sync_timeline[1]["name"] == "01_15"
    assert sync_timeline[1]["occurrence"] == 2
    assert sync_timeline[2]["name"] == "01_20"
    assert sync_timeline[2]["occurrence"] == 1


def test_canonical_timeline_degenerate_surplus_fold():
    """Verifies that when blocks exceed total audio frames, surplus blocks are folded without span inversion."""
    surplus_blocks = [
        {"name": f"clip_{i}", "sec": float(i), "span": {"start_frame": i, "end_frame": i + 1}}
        for i in range(5)
    ]
    # Audio duration 2 frames (fps=30, dur=2/30) with 5 blocks
    sync_timeline = prepare_synchronized_timeline(surplus_blocks, audio_duration=2 / 30.0, fps=30)

    assert len(sync_timeline) == 2
    assert sync_timeline[0]["start_frame"] == 0
    assert sync_timeline[0]["end_frame"] == 1
    assert sync_timeline[1]["start_frame"] == 1
    assert sync_timeline[1]["end_frame"] == 2
    assert sum(c["frame_count"] for c in sync_timeline) == 2
