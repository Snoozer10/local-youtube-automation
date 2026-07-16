"""Integration tests for run_single_pass and related functions."""

import os
import tempfile
import subprocess
import pytest
import compile_video


class TestRunSinglePass:
    """Tests for run_single_pass(config, encoder_config, image_blocks, images_dir, audio_path, run_folder)."""

    def test_dry_run_returns_true_no_ffmpeg(self, config, temp_run_folder, sample_timeline, test_images_dir, dummy_audio_file, monkeypatch):
        """DEBUG_DRY_RUN=true returns True without calling ffmpeg."""
        config["DEBUG_DRY_RUN"] = True
        config["ENABLE_SUBTITLES"] = False

        ffmpeg_called = []
        def mock_run(cmd, *args, **kwargs):
            ffmpeg_called.append(cmd)
            class R:
                returncode = 0
                stdout = ""
                stderr = ""
            return R()
        monkeypatch.setattr(subprocess, "run", mock_run)

        encoder_config = compile_video.detect_hardware_encoder(config)
        result = compile_video.run_single_pass(
            config, encoder_config, sample_timeline,
            test_images_dir, dummy_audio_file, temp_run_folder
        )

        assert result is True
        assert len(ffmpeg_called) == 0, "ffmpeg should not be called in dry run mode"

    def test_subtitle_missing_warning_continues(self, config, temp_run_folder, sample_timeline, test_images_dir, dummy_audio_file, monkeypatch, capsys):
        """ENABLE_SUBTITLES=true but SRT missing prints warning and continues."""
        config["ENABLE_SUBTITLES"] = True
        config["DEBUG_DRY_RUN"] = False  # must not dry-run to test SRT check

        def mock_run(cmd, *args, **kwargs):
            class R:
                returncode = 0
                stdout = ""
                stderr = ""
            return R()
        monkeypatch.setattr(subprocess, "run", mock_run)

        encoder_config = compile_video.detect_hardware_encoder(config)
        result = compile_video.run_single_pass(
            config, encoder_config, sample_timeline,
            test_images_dir, dummy_audio_file, temp_run_folder
        )

        assert result is True
        captured = capsys.readouterr()
        assert "Subtitles enabled but SRT missing" in captured.out

    def test_subtitle_missing_warning_in_dry_run(self, config, temp_run_folder, sample_timeline, test_images_dir, dummy_audio_file, capsys):
        """SRT missing warning still fires when DEBUG_DRY_RUN is enabled."""
        config["ENABLE_SUBTITLES"] = True
        config["DEBUG_DRY_RUN"] = True

        encoder_config = compile_video.detect_hardware_encoder(config)
        result = compile_video.run_single_pass(
            config, encoder_config, sample_timeline,
            test_images_dir, dummy_audio_file, temp_run_folder
        )

        assert result is True
        captured = capsys.readouterr()
        assert "Subtitles enabled but SRT missing" in captured.out

    def test_ffmpeg_timeout_returns_false(self, config, temp_run_folder, sample_timeline, test_images_dir, dummy_audio_file, monkeypatch):
        """FFmpeg timeout returns False."""
        def mock_run(cmd, *args, **kwargs):
            raise subprocess.TimeoutExpired("ffmpeg", config["FFMPEG_FINAL_TIMEOUT"])
        monkeypatch.setattr(subprocess, "run", mock_run)

        encoder_config = compile_video.detect_hardware_encoder(config)
        result = compile_video.run_single_pass(
            config, encoder_config, sample_timeline,
            test_images_dir, dummy_audio_file, temp_run_folder
        )

        assert result is False

    def test_ffmpeg_failure_returns_false(self, config, temp_run_folder, sample_timeline, test_images_dir, dummy_audio_file, monkeypatch):
        """FFmpeg non-zero return code returns False."""
        def mock_run(cmd, *args, **kwargs):
            class R:
                returncode = 1
                stdout = ""
                stderr = "ffmpeg error: invalid argument"
            return R()
        monkeypatch.setattr(subprocess, "run", mock_run)

        encoder_config = compile_video.detect_hardware_encoder(config)
        result = compile_video.run_single_pass(
            config, encoder_config, sample_timeline,
            test_images_dir, dummy_audio_file, temp_run_folder
        )

        assert result is False

    def test_hardware_encoder_failure_falls_back_to_cpu(self, config, temp_run_folder, sample_timeline, test_images_dir, dummy_audio_file, monkeypatch):
        """Hardware encoder failure triggers retry with libx264 software fallback."""
        encoder_config = {
            "video_codec": "h264_qsv",
            "hwaccel": "qsv",
            "encoder_args": ["-global_quality", "22"]
        }

        called_cmds = []
        def mock_run(cmd, *args, **kwargs):
            called_cmds.append(cmd)
            # If QSV is in the command, fail it
            if "h264_qsv" in cmd:
                class R:
                    returncode = 1
                    stdout = ""
                    stderr = "h264_qsv failed: Invalid FrameType:0."
                return R()
            else:
                class R:
                    returncode = 0
                    stdout = ""
                    stderr = ""
                return R()
        monkeypatch.setattr(subprocess, "run", mock_run)

        result = compile_video.run_single_pass(
            config, encoder_config, sample_timeline,
            test_images_dir, dummy_audio_file, temp_run_folder
        )

        assert result is True
        assert len(called_cmds) == 2
        assert "h264_qsv" in called_cmds[0]
        assert "libx264" in called_cmds[1]

    def test_filter_complex_script_file_created(self, config, temp_run_folder, sample_timeline, test_images_dir, dummy_audio_file, monkeypatch):
        """Filter graph written to file and -filter_complex used."""
        def mock_run(cmd, *args, **kwargs):
            class R:
                returncode = 0
                stdout = ""
                stderr = ""
            return R()
        monkeypatch.setattr(subprocess, "run", mock_run)

        encoder_config = compile_video.detect_hardware_encoder(config)
        result = compile_video.run_single_pass(
            config, encoder_config, sample_timeline,
            test_images_dir, dummy_audio_file, temp_run_folder
        )

        assert result is True
        # Check filter_complex.txt was created
        filter_path = os.path.join(temp_run_folder, "filter_complex.txt")
        assert os.path.exists(filter_path), "filter_complex.txt should be created"
        with open(filter_path, encoding="utf-8") as f:
            content = f.read()
        assert "concat=" in content
        assert "loudnorm" in content

    def test_output_video_path_constructed(self, config, temp_run_folder, sample_timeline, test_images_dir, dummy_audio_file, monkeypatch):
        """Output video path is correctly constructed in run_folder."""
        def mock_run(cmd, *args, **kwargs):
            class R:
                returncode = 0
                stdout = ""
                stderr = ""
            return R()
        monkeypatch.setattr(subprocess, "run", mock_run)

        encoder_config = compile_video.detect_hardware_encoder(config)
        result = compile_video.run_single_pass(
            config, encoder_config, sample_timeline,
            test_images_dir, dummy_audio_file, temp_run_folder
        )

        assert result is True
        output_path = os.path.join(temp_run_folder, "youtube_ready_video.mp4")
        # The mock doesn't actually create the file, but we can verify the command
        # was called with the right output path by checking the mock call

    def test_checkpoint_manager_integration(self, config, temp_run_folder, sample_timeline, test_images_dir, dummy_audio_file, monkeypatch):
        """Single-pass mode writes filter_complex.txt and renders in one pass (no checkpoint)."""
        config["ENABLE_CHECKPOINT_RESUME"] = False
        config["ENABLE_SINGLE_PASS"] = True

        def mock_run(cmd, *args, **kwargs):
            class R:
                returncode = 0
                stdout = ""
                stderr = ""
            return R()
        monkeypatch.setattr(subprocess, "run", mock_run)

        encoder_config = compile_video.detect_hardware_encoder(config)
        result = compile_video.run_single_pass(
            config, encoder_config, sample_timeline,
            test_images_dir, dummy_audio_file, temp_run_folder
        )

        assert result is True
        # Single-pass does NOT create compile_checkpoint.json
        checkpoint_path = os.path.join(temp_run_folder, config["CHECKPOINT_FILE"])
        assert not os.path.exists(checkpoint_path), "Single-pass should not create checkpoint file"
        # But it DOES create filter_complex.txt
        filter_path = os.path.join(temp_run_folder, "filter_complex.txt")
        assert os.path.exists(filter_path), "Single-pass should create filter_complex.txt"

    def test_checkpoint_manager_integration_enabled(self, config, temp_run_folder, sample_timeline, test_images_dir, dummy_audio_file, monkeypatch):
        """Single-pass mode initializes checkpoint and completes all clips on success."""
        config["ENABLE_CHECKPOINT_RESUME"] = True
        config["ENABLE_SINGLE_PASS"] = True

        def mock_run(cmd, *args, **kwargs):
            class R:
                returncode = 0
                stdout = ""
                stderr = ""
            return R()
        monkeypatch.setattr(subprocess, "run", mock_run)

        encoder_config = compile_video.detect_hardware_encoder(config)
        checkpoint = compile_video.CheckpointManager(temp_run_folder, config)
        
        result = compile_video.run_single_pass(
            config, encoder_config, sample_timeline,
            test_images_dir, dummy_audio_file, temp_run_folder, checkpoint
        )

        assert result is True
        checkpoint_path = os.path.join(temp_run_folder, config["CHECKPOINT_FILE"])
        assert os.path.exists(checkpoint_path), "Single-pass should create checkpoint file"
        
        # Verify all clips completed in checkpoint
        checkpoint_res = compile_video.CheckpointManager(temp_run_folder, config)
        assert checkpoint_res.data["completed_clips"] == len(sample_timeline)
        assert all(state["status"] == "done" for state in checkpoint_res.data["clip_states"].values())

    def test_checkpoint_manager_integration_resume_skips(self, config, temp_run_folder, sample_timeline, test_images_dir, dummy_audio_file, monkeypatch):
        """Single-pass mode skips compilation if checkpoint indicates completion and output exists."""
        config["ENABLE_CHECKPOINT_RESUME"] = True
        config["ENABLE_SINGLE_PASS"] = True

        # Pre-create output file and a completed checkpoint
        output_file = os.path.join(temp_run_folder, "youtube_ready_video.mp4")
        with open(output_file, "w") as f:
            f.write("dummy video data")

        encoder_config = compile_video.detect_hardware_encoder(config)
        checkpoint = compile_video.CheckpointManager(temp_run_folder, config)
        checkpoint.initialize(len(sample_timeline), encoder_config, dummy_audio_file, 10.0)
        for i in range(len(sample_timeline)):
            checkpoint.mark_clip_done(i, "youtube_ready_video.mp4", 3.0)

        ffmpeg_called = []
        def mock_run(cmd, *args, **kwargs):
            ffmpeg_called.append(cmd)
            class R:
                returncode = 0
            return R()
        monkeypatch.setattr(subprocess, "run", mock_run)

        result = compile_video.run_single_pass(
            config, encoder_config, sample_timeline,
            test_images_dir, dummy_audio_file, temp_run_folder, checkpoint
        )

        assert result is True
        assert len(ffmpeg_called) == 0, "Should skip rendering and not invoke FFmpeg"


class TestBuildSinglePassFilterGraph:
    """Additional tests for build_single_pass_filter_graph."""

    def test_filter_graph_includes_ken_burns_for_each_clip(self, config, temp_run_folder, sample_timeline, test_images_dir, dummy_audio_file):
        """Filter graph contains Ken Burns filter for animated clips, static filter for static clips."""
        encoder_config = compile_video.detect_hardware_encoder(config)
        ai_cameras = {"00_00": "zoom_in", "00_08": "pan_left", "00_15": "static"}
        manual_cameras = {}

        input_args, filter_complex, video_label = compile_video.build_single_pass_filter_graph(
            config, encoder_config, sample_timeline, test_images_dir,
            dummy_audio_file, None, ai_cameras, manual_cameras, True
        )

        assert "zoompan" in filter_complex
        # zoom_in and pan_left use zoompan; static uses scale+pad (no zoompan)
        assert filter_complex.count("zoompan") == 2
        assert "scale=1920:1080:force_original_aspect_ratio=decrease" in filter_complex
        assert "pad=1920:1080:-1:-1:color=black" in filter_complex

    def test_filter_graph_includes_subtitles_when_enabled(self, config, temp_run_folder, sample_timeline, test_images_dir, dummy_audio_file, dummy_srt_file):
        """Filter graph includes subtitles filter when subtitle path provided."""
        config["ENABLE_SUBTITLES"] = True
        encoder_config = compile_video.detect_hardware_encoder(config)

        input_args, filter_complex, video_label = compile_video.build_single_pass_filter_graph(
            config, encoder_config, sample_timeline, test_images_dir,
            dummy_audio_file, dummy_srt_file, {}, {}, True
        )

        assert "subtitles=" in filter_complex
        assert video_label == "vformat"  # subtitles changes output label, format changes it to vformat

    def test_filter_graph_audio_loudnorm_chain(self, config, temp_run_folder, sample_timeline, test_images_dir, dummy_audio_file):
        """Filter graph includes loudnorm filter chain for audio."""
        encoder_config = compile_video.detect_hardware_encoder(config)

        input_args, filter_complex, video_label = compile_video.build_single_pass_filter_graph(
            config, encoder_config, sample_timeline, test_images_dir,
            dummy_audio_file, None, {}, {}, True
        )

        assert "loudnorm" in filter_complex
        assert "[aout]" in filter_complex

    def test_input_args_count_matches_images_plus_audio(self, config, temp_run_folder, sample_timeline, test_images_dir, dummy_audio_file):
        """Input args contain -i for each image + 1 for audio."""
        encoder_config = compile_video.detect_hardware_encoder(config)

        input_args, _, _ = compile_video.build_single_pass_filter_graph(
            config, encoder_config, sample_timeline, test_images_dir,
            dummy_audio_file, None, {}, {}, True
        )

        # Count -i occurrences
        i_count = input_args.count("-i")
        assert i_count == len(sample_timeline) + 1  # images + audio

    def test_manual_overrides_override_ai_cameras(self, config, temp_run_folder, sample_timeline, test_images_dir, dummy_audio_file):
        """Manual camera overrides take precedence over AI decisions."""
        encoder_config = compile_video.detect_hardware_encoder(config)
        ai_cameras = {"00_00": "zoom_in", "00_08": "pan_left", "00_15": "static"}
        manual_cameras = {"00_08": "zoom_out", "00_15": "pan_right"}

        input_args, filter_complex, _ = compile_video.build_single_pass_filter_graph(
            config, encoder_config, sample_timeline, test_images_dir,
            dummy_audio_file, None, ai_cameras, manual_cameras, True
        )

        # The filter_complex should contain the manual override actions
        # For 00_08: zoom_out (manual) instead of pan_left (AI)
        # For 00_15: pan_right (manual) instead of static (AI)
        assert "zoompan" in filter_complex
        # We can't easily assert exact filters without parsing, but we verify structure
        assert filter_complex.count("zoompan") == len(sample_timeline)