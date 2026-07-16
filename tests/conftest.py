"""Shared pytest fixtures for compile_video tests."""

import os
import tempfile
import shutil
import json
import subprocess
import pytest

import compile_video


@pytest.fixture
def config():
    """Default video config with test overrides."""
    c = compile_video.load_video_config()
    c["ENCODER_FORCE"] = "libx264"
    c["ENABLE_LOUDNORM_TWOPASS"] = False
    c["ENABLE_SUBTITLES"] = False
    c["ENABLE_ANIMATIONS"] = True
    c["ENABLE_CHECKPOINT_RESUME"] = False
    c["ENABLE_SINGLE_PASS"] = True
    c["_audio_duration"] = 10.0
    c["FFMPEG_CLIP_TIMEOUT"] = 60
    c["FFMPEG_FINAL_TIMEOUT"] = 120
    return c


@pytest.fixture
def encoder_config(config):
    """Video config for encoder detection tests (no ENCODER_FORCE override)."""
    c = config.copy()
    c["ENCODER_FORCE"] = ""
    return c


@pytest.fixture
def temp_run_folder():
    """Temp dir with run folder structure (generated_images, temp_clips)."""
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "generated_images"), exist_ok=True)
    os.makedirs(os.path.join(d, "temp_clips"), exist_ok=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def sample_timeline():
    """Standard 3-block timeline."""
    return [
        {"name": "00_00", "sec": 0.0},
        {"name": "00_08", "sec": 8.0},
        {"name": "00_15", "sec": 15.0},
    ]


@pytest.fixture
def sample_flow_prompts(temp_run_folder):
    """Write flow_prompts.json with camera decisions."""
    path = os.path.join(temp_run_folder, "flow_prompts.json")
    data = [
        {"timestamp": "[00:00]", "visual_prompt": {"camera_specifications": "zoom in slowly"}},
        {"timestamp": "[00:08]", "visual_prompt": {"camera_specifications": "pan left across scene"}},
        {"timestamp": "[00:15]", "visual_prompt": {"camera_specifications": "static shot"}},
    ]
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    return path


@pytest.fixture
def sample_manual_animations(temp_run_folder):
    """Write manual_animations.txt with overrides."""
    path = os.path.join(temp_run_folder, "manual_animations.txt")
    with open(path, 'w', encoding='utf-8') as f:
        f.write("00_00=zoom_out\n")
        f.write("00_15=pan_right\n")
    return path


@pytest.fixture
def mock_ffmpeg(monkeypatch):
    """Patch subprocess.run for ffmpeg/ffprobe calls."""
    def mock_run(cmd, *args, **kwargs):
        # Mock ffprobe duration
        if "ffprobe" in cmd[0]:
            class R:
                stdout = "10.0\n"
                returncode = 0
            return R()

        # Mock ffmpeg -encoders
        if "-encoders" in cmd:
            class R:
                stdout = "h264_qsv\nh264_nvenc\nlibx264\n"
                returncode = 0
            return R()

        # Mock loudnorm measure pass
        if "loudnorm" in " ".join(cmd) and "print_format=json" in " ".join(cmd):
            class R:
                stderr = '{"input_i":"-14.5","input_tp":"-1.2","input_lra":"7.8","input_thresh":"-25.3","target_offset":"0.5"}'
                returncode = 0
            return R()

        # Default: success
        class R:
            stdout = ""
            stderr = ""
            returncode = 0
        return R()

    monkeypatch.setattr(subprocess, "run", mock_run)
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **k: b"10.0\n")
    return mock_run


@pytest.fixture
def test_images_dir():
    """Create temp dir with test PNG images."""
    d = tempfile.mkdtemp()
    # Generate simple test images using ffmpeg
    for name in ["00_00.png", "00_08.png", "00_15.png"]:
        img_path = os.path.join(d, name)
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=blue:s=200x200", "-frames:v", "1",
            "-update", "1", img_path
        ]
        subprocess.run(cmd, capture_output=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def dummy_audio_file():
    """Create a dummy audio file for testing."""
    d = tempfile.mkdtemp()
    audio_path = os.path.join(d, "audio.wav")
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=10",
        "-ar", "48000", audio_path
    ]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        pytest.skip("ffmpeg unavailable for audio generation")
    yield audio_path
    if os.path.exists(audio_path):
        os.remove(audio_path)
    os.rmdir(d)


@pytest.fixture
def dummy_srt_file(temp_run_folder):
    """Create a dummy SRT file for subtitle testing."""
    srt_path = os.path.join(temp_run_folder, "timestamped_transcript.srt")
    with open(srt_path, "w", encoding="utf-8-sig") as f:
        f.write("1\n00:00:00,000 --> 00:00:05,000\nTest subtitle\n\n")
        f.write("2\n00:00:05,000 --> 00:00:10,000\nAnother subtitle\n")
    return srt_path