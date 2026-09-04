"""Unit tests for compile_video.validate_post_encode and dynamic Ken Burns scale (Spec line 85)."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import compile_video


class TestValidatePostEncode:
    def test_missing_video_file_raises_runtime_error(self, tmp_path: Path) -> None:
        missing_file = str(tmp_path / "nonexistent.mp4")
        with pytest.raises(RuntimeError, match="does not exist"):
            compile_video.validate_post_encode(missing_file, 10.0, 30)

    def test_ffprobe_failure_raises_runtime_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dummy_file = tmp_path / "dummy.mp4"
        dummy_file.write_text("fake video content", encoding="utf-8")

        fake_res = MagicMock(returncode=1, stderr="Invalid media format", stdout="")
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: fake_res)

        with pytest.raises(RuntimeError, match="ffprobe failed during post-encode validation"):
            compile_video.validate_post_encode(str(dummy_file), 10.0, 30)

    def test_no_video_streams_raises_runtime_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dummy_file = tmp_path / "dummy.mp4"
        dummy_file.write_text("fake video content", encoding="utf-8")

        fake_res = MagicMock(
            returncode=0,
            stdout=json.dumps({"streams": [], "format": {"duration": "10.0"}}),
        )
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: fake_res)

        with pytest.raises(RuntimeError, match="no video streams found"):
            compile_video.validate_post_encode(str(dummy_file), 10.0, 30)

    def test_frame_count_mismatch_raises_runtime_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dummy_file = tmp_path / "dummy.mp4"
        dummy_file.write_text("fake video content", encoding="utf-8")

        # audio_duration = 10.0s, fps = 30 -> expected 300 frames. Reported: 290 frames.
        fake_res = MagicMock(
            returncode=0,
            stdout=json.dumps(
                {
                    "streams": [{"nb_read_packets": "290", "duration": "10.000"}],
                    "format": {"duration": "10.000"},
                }
            ),
        )
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: fake_res)

        with pytest.raises(RuntimeError, match="frame count mismatch"):
            compile_video.validate_post_encode(str(dummy_file), 10.0, 30)

    def test_duration_drift_exceeds_002s_raises_runtime_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dummy_file = tmp_path / "dummy.mp4"
        dummy_file.write_text("fake video content", encoding="utf-8")

        # audio_duration = 10.000s, video duration = 10.035s -> diff 0.035s > 0.02s
        fake_res = MagicMock(
            returncode=0,
            stdout=json.dumps(
                {
                    "streams": [{"nb_read_packets": "300", "duration": "10.035"}],
                    "format": {"duration": "10.035"},
                }
            ),
        )
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: fake_res)

        with pytest.raises(RuntimeError, match="audio/video duration drift.*threshold"):
            compile_video.validate_post_encode(str(dummy_file), 10.0, 30)

    def test_post_encode_within_tolerance_passes_cleanly(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dummy_file = tmp_path / "dummy.mp4"
        dummy_file.write_text("fake video content", encoding="utf-8")

        # audio_duration = 10.000s, video duration = 10.008s -> diff 0.008s <= 0.02s
        fake_res = MagicMock(
            returncode=0,
            stdout=json.dumps(
                {
                    "streams": [{"nb_read_packets": "300", "duration": "10.008"}],
                    "format": {"duration": "10.008"},
                }
            ),
        )
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: fake_res)

        # Should return without exception
        compile_video.validate_post_encode(str(dummy_file), 10.0, 30)


class TestKenBurnsDynamicScale:
    def test_dynamic_scale_enabled_by_default(self) -> None:
        config = {
            "OUTPUT_FPS": 30,
            "OUTPUT_WIDTH": 1920,
            "OUTPUT_HEIGHT": 1080,
            "KEN_BURNS_ZOOM_MIN": 1.0,
        }
        # 30 frames at 30 fps = 1.0s duration -> scale = clamp(1.06 + (1.0 - 2.5)/2.0 * 0.04) = clamp(1.03) = 1.06
        flt_short = compile_video.build_ken_burns_filter(config, frame_count=30, camera_action="zoom_in")
        assert "min(1.06" in flt_short

        # 150 frames at 30 fps = 5.0s duration -> scale = clamp(1.06 + (5.0 - 2.5)/2.0 * 0.04) = clamp(1.11) = 1.10
        flt_long = compile_video.build_ken_burns_filter(config, frame_count=150, camera_action="zoom_in")
        assert "min(1.1" in flt_long

    def test_dynamic_scale_clamped_by_zoom_max_if_lower(self) -> None:
        config = {
            "OUTPUT_FPS": 30,
            "OUTPUT_WIDTH": 1920,
            "OUTPUT_HEIGHT": 1080,
            "KEN_BURNS_ZOOM_MIN": 1.0,
            "KEN_BURNS_ZOOM_MAX": 1.08,
        }
        # 150 frames at 30 fps -> dynamic scale is 1.10, but capped by 1.08
        flt = compile_video.build_ken_burns_filter(config, frame_count=150, camera_action="zoom_in")
        assert "min(1.08" in flt
