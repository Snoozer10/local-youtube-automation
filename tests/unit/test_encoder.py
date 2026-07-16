"""Integration tests for hardware encoder detection and configuration."""

import pytest
import compile_video


class TestProbeEncoder:
    """Tests for _probe_encoder (internal function via detect_hardware_encoder)."""

    def test_probe_encoder_found(self, monkeypatch):
        """Encoder present in ffmpeg -encoders output returns True."""
        def mock_run(cmd, *args, **kwargs):
            class R:
                stdout = "h264_qsv\nh264_nvenc\nlibx264\n"
                returncode = 0
            return R()
        monkeypatch.setattr("compile_video.subprocess.run", mock_run)

        assert compile_video._probe_encoder("h264_qsv") is True
        assert compile_video._probe_encoder("libx264") is True

    def test_probe_encoder_not_found(self, monkeypatch):
        """Encoder absent from ffmpeg -encoders output returns False."""
        def mock_run(cmd, *args, **kwargs):
            class R:
                stdout = "h264_nvenc\nlibx264\n"
                returncode = 0
            return R()
        monkeypatch.setattr("compile_video.subprocess.run", mock_run)

        assert compile_video._probe_encoder("h264_qsv") is False

    def test_probe_encoder_exception_returns_false(self, monkeypatch):
        """Subprocess exception returns False (safe fallback)."""
        def mock_run(cmd, *args, **kwargs):
            raise subprocess.TimeoutExpired("ffmpeg", 10)
        import subprocess
        monkeypatch.setattr("compile_video.subprocess.run", mock_run)

        assert compile_video._probe_encoder("h264_qsv") is False


class TestBuildEncoderConfig:
    """Tests for _build_encoder_config (internal function via detect_hardware_encoder)."""

    def test_qsv_config_includes_vbv_when_enabled(self, encoder_config):
        """QSV config includes VBV args when ENABLE_VBV=true."""
        encoder_config["ENABLE_VBV"] = True
        encoder_config["VBV_MAXRATE"] = "10000k"
        encoder_config["VBV_BUFSIZE"] = "20000k"
        result = compile_video._build_encoder_config("h264_qsv", encoder_config)

        assert result["video_codec"] == "h264_qsv"
        assert result["hwaccel"] == "qsv"
        assert "-preset" in result["encoder_args"]
        assert "-global_quality" in result["encoder_args"]
        assert "-look_ahead" in result["encoder_args"]
        assert "-maxrate" in result["encoder_args"]
        assert "-bufsize" in result["encoder_args"]
        assert result["encoder_args"][result["encoder_args"].index("-maxrate") + 1] == "10000k"

    def test_qsv_config_omits_vbv_when_disabled(self, encoder_config):
        """QSV config omits VBV args when ENABLE_VBV=false."""
        encoder_config["ENABLE_VBV"] = False
        result = compile_video._build_encoder_config("h264_qsv", encoder_config)

        assert "-maxrate" not in result["encoder_args"]
        assert "-bufsize" not in result["encoder_args"]

    def test_nvenc_config_includes_vbv_when_enabled(self, encoder_config):
        """NVENC config includes VBV args when ENABLE_VBV=true."""
        encoder_config["ENABLE_VBV"] = True
        result = compile_video._build_encoder_config("h264_nvenc", encoder_config)

        assert result["video_codec"] == "h264_nvenc"
        assert result["hwaccel"] == "cuda"
        assert "-preset" in result["encoder_args"]
        assert "-cq" in result["encoder_args"]
        assert "-rc" in result["encoder_args"]
        assert "-maxrate" in result["encoder_args"]

    def test_cpu_fallback_config(self, encoder_config):
        """CPU libx264 config uses CRF/preset/tune."""
        result = compile_video._build_encoder_config("libx264", encoder_config)

        assert result["video_codec"] == "libx264"
        assert result["hwaccel"] == "none"
        assert "-crf" in result["encoder_args"]
        assert "-preset" in result["encoder_args"]
        assert "-tune" in result["encoder_args"]
        assert "-profile:v" in result["encoder_args"]
        assert "-level" in result["encoder_args"]

    def test_all_encoders_include_common_args(self, encoder_config):
        """All encoder configs include common args: pix_fmt, movflags, threads."""
        for encoder in ["h264_qsv", "h264_nvenc", "libx264"]:
            result = compile_video._build_encoder_config(encoder, encoder_config)
            assert "-pix_fmt" in result["encoder_args"]
            assert "-movflags" in result["encoder_args"]
            assert "+faststart" in result["encoder_args"]
            assert "-threads" in result["encoder_args"]


class TestDetectHardwareEncoder:
    """Tests for detect_hardware_encoder(config)."""

    def test_qsv_priority_when_available(self, encoder_config, monkeypatch):
        """QSV selected first when available."""
        def mock_probe(encoder):
            return encoder in ["h264_qsv", "h264_nvenc", "libx264"]
        monkeypatch.setattr(compile_video, "_probe_encoder", mock_probe)

        result = compile_video.detect_hardware_encoder(encoder_config)

        assert result["video_codec"] == "h264_qsv"
        assert result["hwaccel"] == "qsv"

    def test_nvenc_fallback_when_no_qsv(self, encoder_config, monkeypatch):
        """NVENC selected when QSV unavailable."""
        def mock_probe(encoder):
            return encoder in ["h264_nvenc", "libx264"]
        monkeypatch.setattr(compile_video, "_probe_encoder", mock_probe)

        result = compile_video.detect_hardware_encoder(encoder_config)

        assert result["video_codec"] == "h264_nvenc"
        assert result["hwaccel"] == "cuda"

    def test_cpu_fallback_when_no_hw(self, encoder_config, monkeypatch):
        """CPU libx264 selected when no hardware encoders."""
        def mock_probe(encoder):
            return encoder == "libx264"
        monkeypatch.setattr(compile_video, "_probe_encoder", mock_probe)

        result = compile_video.detect_hardware_encoder(encoder_config)

        assert result["video_codec"] == "libx264"
        assert result["hwaccel"] == "none"

    def test_encoder_force_overrides_probe(self, encoder_config, monkeypatch):
        """ENCODER_FORCE bypasses probe and selects specified encoder."""
        encoder_config["ENCODER_FORCE"] = "h264_nvenc"

        # Even if probe would fail, force should work
        def mock_probe(encoder):
            return False
        monkeypatch.setattr(compile_video, "_probe_encoder", mock_probe)

        result = compile_video.detect_hardware_encoder(encoder_config)

        assert result["video_codec"] == "h264_nvenc"

    def test_encoder_force_qsv(self, encoder_config, monkeypatch):
        """ENCODER_FORCE=h264_qsv selects QSV config."""
        encoder_config["ENCODER_FORCE"] = "h264_qsv"
        monkeypatch.setattr(compile_video, "_probe_encoder", lambda e: False)

        result = compile_video.detect_hardware_encoder(encoder_config)

        assert result["video_codec"] == "h264_qsv"

    def test_encoder_force_cpu(self, encoder_config, monkeypatch):
        """ENCODER_FORCE=libx264 selects CPU config."""
        encoder_config["ENCODER_FORCE"] = "libx264"
        monkeypatch.setattr(compile_video, "_probe_encoder", lambda e: False)

        result = compile_video.detect_hardware_encoder(encoder_config)

        assert result["video_codec"] == "libx264"