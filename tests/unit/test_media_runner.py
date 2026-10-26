from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from youtube_automation.video.runner import (
    FakeMediaRunner,
    MediaExecutionError,
    MediaProbeResult,
    MediaRunner,
    SubprocessMediaRunner,
)


def test_media_runner_protocol_conformance() -> None:
    fake = FakeMediaRunner()
    subprocess_runner = SubprocessMediaRunner()
    assert isinstance(fake, MediaRunner)
    assert isinstance(subprocess_runner, MediaRunner)


def test_fake_media_runner_records_commands() -> None:
    runner = FakeMediaRunner()
    stdout, stderr = runner.run_ffmpeg(["-version"])
    assert "fake ffmpeg" in stdout
    assert runner.commands_run == [["ffmpeg", "-version"]]


def test_fake_media_runner_simulates_failure() -> None:
    runner = FakeMediaRunner()
    runner.set_next_error(
        MediaExecutionError("Simulated GPU crash", ["ffmpeg", "-c:v", "h264_qsv"], 1, "QSV error")
    )

    with pytest.raises(MediaExecutionError) as exc_info:
        runner.run_ffmpeg(["-c:v", "h264_qsv"])
    assert "Simulated GPU crash" in str(exc_info.value)
    assert exc_info.value.returncode == 1
    assert exc_info.value.stderr == "QSV error"


def test_fake_media_runner_creates_output_file(tmp_path: Path) -> None:
    runner = FakeMediaRunner()
    output_mp4 = tmp_path / "output.mp4"
    assert not output_mp4.exists()

    runner.run_ffmpeg(["-i", "input.png", "-y", str(output_mp4)])
    assert output_mp4.exists()
    assert output_mp4.stat().st_size > 0


def test_fake_media_runner_probe_default_and_custom(tmp_path: Path) -> None:
    runner = FakeMediaRunner()
    media_file = tmp_path / "video.mp4"
    media_file.write_bytes(b"dummy video")

    # Default probe
    res = runner.probe(media_file)
    assert res.total_frames == 90
    assert res.duration == 3.0
    assert res.fps == 30.0
    assert res.pix_fmt == "yuv420p"
    assert res.color_range == "tv"

    # Custom registered probe
    custom = MediaProbeResult(
        duration=10.0,
        total_frames=300,
        width=2560,
        height=1440,
        fps=30.0,
        pix_fmt="nv12",
        color_range="tv",
    )
    runner.register_probe(media_file, custom)
    res_custom = runner.probe(media_file)
    assert res_custom.total_frames == 300
    assert res_custom.width == 2560
    assert res_custom.pix_fmt == "nv12"


def test_fake_media_runner_probe_missing_file(tmp_path: Path) -> None:
    runner = FakeMediaRunner()
    missing = tmp_path / "does_not_exist.mp4"
    with pytest.raises(FileNotFoundError):
        runner.probe(missing)


def test_subprocess_media_runner_missing_file_probe(tmp_path: Path) -> None:
    runner = SubprocessMediaRunner()
    missing = tmp_path / "non_existent.mp4"
    with pytest.raises(FileNotFoundError):
        runner.probe(missing)


def test_subprocess_media_runner_execution_failure() -> None:
    runner = SubprocessMediaRunner()
    # Invalid argument to force non-zero return code
    with pytest.raises(MediaExecutionError) as exc_info:
        runner.run_ffmpeg(["-invalid_flag_that_does_not_exist_xyz"])
    assert exc_info.value.returncode != 0
    assert len(exc_info.value.stderr) > 0


def test_subprocess_probe_retains_independent_stream_durations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json
    import subprocess

    media = tmp_path / "candidate.mp4"
    media.write_bytes(b"media fixture")
    payload = {
        "streams": [
            {"codec_type": "video", "width": 128, "height": 72,
             "avg_frame_rate": "30/1", "pix_fmt": "yuv420p",
             "color_range": "tv", "nb_read_frames": "30", "duration": "1.0"},
            {"codec_type": "audio", "duration": "0.5"},
        ],
        "format": {"duration": "1.0"},
    }
    monkeypatch.setattr(
        subprocess, "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, json.dumps(payload), ""),
    )
    result = SubprocessMediaRunner().probe(media, require_audio=True)
    assert result.video_duration == 1.0
    assert result.audio_duration == 0.5


def test_fake_runner_uses_explicit_target_and_exact_pending_alias(tmp_path: Path) -> None:
    runner = FakeMediaRunner(default_width=128, default_height=72, default_fps=24, default_pix_fmt="yuv444p")
    media = tmp_path / "other.mp4"
    media.write_bytes(b"fixture")
    metadata = runner.probe(media)
    assert (metadata.width, metadata.height, metadata.fps, metadata.pix_fmt) == (128, 72, 24, "yuv444p")

    desired = MediaProbeResult(1.0, 30, 640, 480, 30.0, "yuv420p", "tv", True)
    runner.register_probe(tmp_path / "accepted.mp4", desired)
    runner.register_probe(tmp_path / "accepted-extra.mp4", replace(desired, width=1920))
    pending = tmp_path / "accepted.pending_1234abcd.mp4"
    pending.write_bytes(b"candidate")
    assert runner.probe(pending) == desired
