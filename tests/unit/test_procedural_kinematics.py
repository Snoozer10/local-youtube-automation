from __future__ import annotations

import math
import struct
import tempfile
import wave

import pytest

from youtube_automation.video.compiler import prepare_synchronized_timeline
from youtube_automation.video.ken_burns import (
    build_ken_burns_filter,
    derive_multishot_crop,
)


@pytest.fixture
def base_video_config():
    return {
        "OUTPUT_FPS": 30,
        "OUTPUT_WIDTH": 1920,
        "OUTPUT_HEIGHT": 1080,
        "OUTPUT_PIX_FMT": "yuv420p",
        "KEN_BURNS_DYNAMIC_SCALE": False,
        "KEN_BURNS_ZOOM_MAX": 1.10,
    }


@pytest.mark.parametrize("frames", [1, 120, 900])
def test_explicit_hold_never_invents_movement(base_video_config, frames):
    flt = build_ken_burns_filter(base_video_config, frame_count=frames, camera_action="static_hold")
    assert "z='1.0'" in flt
    assert "clip(on" not in flt


def test_static_hold_under_threshold(base_video_config):
    """Verifies that clips shorter than 3.5s receive static 1.0 zoom."""
    frames = 60  # 2.0s at 30 fps
    flt = build_ken_burns_filter(base_video_config, frame_count=frames, camera_action="static")
    assert "z='1.0'" in flt


def test_scale_punch_ken_burns_filter(base_video_config):
    """Verifies scale_punch filter sets zoom to 1.25 and locks eye-line elevation to upper-third."""
    frames = 60
    flt = build_ken_burns_filter(base_video_config, frame_count=frames, camera_action="scale_punch")

    assert "z='1.25'" in flt
    # Ocular Saccade Prevention: Y-expr must anchor to upper-third (ih-ih/zoom)/3.0
    assert "(ih-ih/zoom)/3.0" in flt


def test_derive_multishot_crop_nv12_and_bt709():
    """Verifies derive_multishot_crop computes even-integer bounds, eye-line lock, and BT.709 matrix."""
    crop_info = derive_multishot_crop(
        orig_w=1920,
        orig_h=1080,
        scale_factor=1.25,
        focus_x=0.5,
        eyeline_y=360.0,
        out_w=1920,
        out_h=1080,
    )

    # 1. Even integer clamping for NV12 chroma subsampling
    assert crop_info["crop_w"] % 2 == 0
    assert crop_info["crop_h"] % 2 == 0
    assert crop_info["crop_x"] % 2 == 0
    assert crop_info["crop_y"] % 2 == 0

    # 2. Dimensions for 1.25x scale: 1920 / 1.25 = 1536, 1080 / 1.25 = 864
    assert crop_info["crop_w"] == 1536
    assert crop_info["crop_h"] == 864

    # 3. Horizontal centering: (1920 - 1536) / 2 = 192
    assert crop_info["crop_x"] == 192

    # 4. Vertical positioning locked to eye-line (360 - 864/3 = 72)
    assert crop_info["crop_y"] == 72

    # 5. BT.709 color matrix preservation
    assert "crop=1536:864:192:72" in crop_info["filter_str"]
    assert "scale=1920:1080:out_color_matrix=bt709:flags=lanczos+accurate_rnd" in crop_info["filter_str"]


def test_timeline_subdivision_preserves_budget():
    """Verifies that prepare_synchronized_timeline subdivides long holds at acoustic transients
    into static_hold setup and scale_punch reaction without any frame budget drift.
    """
    sr = 16000
    fps = 30
    duration_sec = 5.0
    total_samples = int(round(duration_sec * sr))

    # Generate synthetic WAV: silence, then strong speech-energy surge at 2.5s
    samples = [0] * total_samples
    transient_sample = int(2.5 * sr)
    surge_len = int(0.3 * sr)

    for i in range(transient_sample, min(total_samples, transient_sample + surge_len)):
        # High amplitude 440 Hz tone (energy floor >> 40 dB, RMS >> 100)
        samples[i] = int(12000 * math.sin(2 * math.pi * 440 * (i / sr)))

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        wav_path = tf.name

    with wave.open(wav_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        raw_bytes = struct.pack(f"<{len(samples)}h", *samples)
        wf.writeframes(raw_bytes)

    # 1 canonical block of 4.5s (135 frames at 30 fps)
    image_blocks = [
        {
            "name": "00_01_00",
            "sec": 0.0,
            "span": {
                "start": 0.0,
                "end": 4.5,
                "start_frame": 0,
                "end_frame": 135,
                "frame_count": 135,
                "duration": 4.5,
                "text": "Terrence Howard explains the secret.",
            },
        }
    ]

    timeline = prepare_synchronized_timeline(
        image_blocks=image_blocks,
        audio_duration=4.5,
        fps=fps,
        audio_path=wav_path,
    )

    # Should be subdivided into 2 sub-shots
    assert len(timeline) == 2

    sub1, sub2 = timeline[0], timeline[1]
    assert sub1["camera_action"] == "static_hold"
    assert sub2["camera_action"] == "scale_punch"

    # Strict zero-drift invariants
    assert sub1["start_frame"] == 0
    assert sub1["end_frame"] == sub2["start_frame"]
    assert sub2["end_frame"] == 135
    assert sub1["frame_count"] + sub2["frame_count"] == 135

    # Occurrence isolation preserved
    assert sub1["occurrence"] == sub2["occurrence"] == 1
    assert sub1["name"] == sub2["name"] == "00_01_00"
