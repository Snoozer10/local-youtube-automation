"""Unit tests for compile_video.get_audio_duration subprocess hardening (ERR-04)."""

import subprocess

import pytest

import compile_video


class TestGetAudioDuration:
    def test_ffprobe_timeout_raises_runtime_error(self, monkeypatch):
        def raise_timeout(cmd, *args, **kwargs):
            raise subprocess.TimeoutExpired(cmd, timeout=kwargs.get("timeout", 60))

        monkeypatch.setattr(subprocess, "run", raise_timeout)
        with pytest.raises(RuntimeError, match=r"exceeded 60(\.0)?s cap"):
            compile_video.get_audio_duration("audio.wav")

    def test_nonzero_returncode_raises_runtime_error_with_stderr_excerpt(self, monkeypatch):
        class FakeResult:
            returncode = 2
            stdout = ""
            stderr = "Invalid data found"

        monkeypatch.setattr(subprocess, "run", lambda cmd, *a, **k: FakeResult())
        with pytest.raises(RuntimeError, match="rc=2.*Invalid data found"):
            compile_video.get_audio_duration("audio.wav")

    def test_success_parses_stdout_float(self, monkeypatch):
        class FakeResult:
            returncode = 0
            stdout = "12.5\n"
            stderr = ""

        monkeypatch.setattr(subprocess, "run", lambda cmd, *a, **k: FakeResult())
        assert compile_video.get_audio_duration("audio.wav") == 12.5
