"""Integration tests for the chunked render pipeline (run_chunked_compile / build_chunk_filter_graph)."""

import os
import subprocess
import tempfile

import pytest
from ffmpeg_stubs import FakePopen

import compile_video


def _assembly_cmd(calls):
    """Return the final assembly command (last Popen call)."""
    return calls[-1]


class TestRunChunkedCompile:
    """Tests for run_chunked_compile(config, encoder_config, sync_timeline, images_dir, audio_path, run_folder[, checkpoint])."""

    def test_happy_path_returns_true(
        self,
        config,
        temp_run_folder,
        sync_timeline,
        test_images_dir,
        dummy_audio_file,
        mock_ffmpeg_popen,
    ):
        """Full chunked render + assembly succeeds with mocked ffmpeg."""
        encoder_config = compile_video.detect_hardware_encoder(config)
        result = compile_video.run_chunked_compile(
            config,
            encoder_config,
            sync_timeline,
            test_images_dir,
            dummy_audio_file,
            temp_run_folder,
        )

        assert result is True
        # chunk render + final assembly
        assert len(mock_ffmpeg_popen) == 2
        # assembly command targets youtube_ready_video.mp4
        assert any("youtube_ready_video.mp4" in part for part in _assembly_cmd(mock_ffmpeg_popen))

    def test_chunk_filter_script_created(
        self,
        config,
        temp_run_folder,
        sync_timeline,
        test_images_dir,
        dummy_audio_file,
        mock_ffmpeg_popen,
    ):
        """Chunk filter graph written to temp_clips/filter_chunk_0000.txt."""
        encoder_config = compile_video.detect_hardware_encoder(config)
        compile_video.run_chunked_compile(
            config,
            encoder_config,
            sync_timeline,
            test_images_dir,
            dummy_audio_file,
            temp_run_folder,
        )

        filter_path = os.path.join(temp_run_folder, "temp_clips", "filter_chunk_0000.txt")
        assert os.path.exists(filter_path), "filter_chunk_0000.txt should be created"
        with open(filter_path, encoding="utf-8") as f:
            content = f.read()
        assert "concat=" in content
        assert "scale=" in content

    def test_final_assembly_script_contains_loudnorm(
        self,
        config,
        temp_run_folder,
        sync_timeline,
        test_images_dir,
        dummy_audio_file,
        mock_ffmpeg_popen,
    ):
        """Final assembly filter script contains the loudnorm audio chain."""
        encoder_config = compile_video.detect_hardware_encoder(config)
        compile_video.run_chunked_compile(
            config,
            encoder_config,
            sync_timeline,
            test_images_dir,
            dummy_audio_file,
            temp_run_folder,
        )

        filter_path = os.path.join(temp_run_folder, "temp_clips", "filter_final_assembly.txt")
        assert os.path.exists(filter_path), "filter_final_assembly.txt should be created"
        with open(filter_path, encoding="utf-8") as f:
            content = f.read()
        assert "loudnorm" in content
        assert "[aout]" in content

    def test_ffmpeg_failure_returns_false(
        self, config, temp_run_folder, sync_timeline, test_images_dir, dummy_audio_file, monkeypatch
    ):
        """Chunk ffmpeg failure with CPU encoder (no fallback) returns False."""
        calls = []

        class FailingPopen(FakePopen):
            def __init__(self, cmd, **kwargs):
                super().__init__(cmd, **kwargs)
                calls.append(list(cmd))
                self.returncode = 1

        monkeypatch.setattr(subprocess, "Popen", FailingPopen)
        encoder_config = compile_video.detect_hardware_encoder(config)
        result = compile_video.run_chunked_compile(
            config,
            encoder_config,
            sync_timeline,
            test_images_dir,
            dummy_audio_file,
            temp_run_folder,
        )

        assert result is False

    def test_hardware_encoder_failure_falls_back_to_cpu(
        self, config, temp_run_folder, sync_timeline, test_images_dir, dummy_audio_file, monkeypatch
    ):
        """QSV failure triggers retry of all chunks with libx264 software fallback."""
        encoder_config = {
            "video_codec": "h264_qsv",
            "hwaccel": "qsv",
            "encoder_args": ["-global_quality", "22"],
        }

        called_cmds = []
        attempt = {"count": 0}

        class FallbackPopen(FakePopen):
            def __init__(self, cmd, **kwargs):
                super().__init__(cmd, **kwargs)
                called_cmds.append(list(cmd))
                # Fail the QSV chunk render once; libx264 retry succeeds
                if "h264_qsv" in cmd:
                    attempt["count"] += 1
                    self.returncode = 1
                else:
                    self.returncode = 0

        monkeypatch.setattr(subprocess, "Popen", FallbackPopen)
        result = compile_video.run_chunked_compile(
            config,
            encoder_config,
            sync_timeline,
            test_images_dir,
            dummy_audio_file,
            temp_run_folder,
        )

        assert result is True
        assert "h264_qsv" in called_cmds[0]
        assert "libx264" in called_cmds[1]

    def test_ffmpeg_timeout_returns_false(
        self, config, temp_run_folder, sync_timeline, test_images_dir, dummy_audio_file, monkeypatch
    ):
        """Chunk ffmpeg timeout kills the process and returns False."""
        config["FFMPEG_CLIP_TIMEOUT"] = 1

        class HangingPopen(FakePopen):
            killed = []

            def poll(self):
                return None  # never finishes

            def kill(self):
                HangingPopen.killed.append(True)

        monkeypatch.setattr(subprocess, "Popen", HangingPopen)
        encoder_config = compile_video.detect_hardware_encoder(config)
        result = compile_video.run_chunked_compile(
            config,
            encoder_config,
            sync_timeline,
            test_images_dir,
            dummy_audio_file,
            temp_run_folder,
        )

        assert result is False
        assert HangingPopen.killed, "hung ffmpeg process should be killed"

    def test_checkpoint_complete_skips_render(
        self,
        config,
        temp_run_folder,
        sync_timeline,
        test_images_dir,
        dummy_audio_file,
        mock_ffmpeg_popen,
    ):
        """Completed checkpoint + existing output skips rendering entirely."""
        config["ENABLE_CHECKPOINT_RESUME"] = True

        output_file = os.path.join(temp_run_folder, "youtube_ready_video.mp4")
        with open(output_file, "w") as f:
            f.write("dummy video data" * 100)

        encoder_config = compile_video.detect_hardware_encoder(config)
        checkpoint = compile_video.CheckpointManager(temp_run_folder, config)
        checkpoint.initialize(len(sync_timeline), encoder_config, dummy_audio_file, 10.0)
        for i in range(len(sync_timeline)):
            checkpoint.mark_clip_done(i, "youtube_ready_video.mp4", sync_timeline[i]["duration"])

        result = compile_video.run_chunked_compile(
            config,
            encoder_config,
            sync_timeline,
            test_images_dir,
            dummy_audio_file,
            temp_run_folder,
            checkpoint,
        )

        assert result is True
        assert len(mock_ffmpeg_popen) == 0, "Should skip rendering and not invoke FFmpeg"

    def test_checkpoint_initialized_for_chunked_render(
        self,
        config,
        temp_run_folder,
        sync_timeline,
        test_images_dir,
        dummy_audio_file,
        mock_ffmpeg_popen,
    ):
        """Chunked render initializes a v3 checkpoint with all clips tracked as pending."""
        config["ENABLE_CHECKPOINT_RESUME"] = True

        encoder_config = compile_video.detect_hardware_encoder(config)
        checkpoint = compile_video.CheckpointManager(temp_run_folder, config)

        result = compile_video.run_chunked_compile(
            config,
            encoder_config,
            sync_timeline,
            test_images_dir,
            dummy_audio_file,
            temp_run_folder,
            checkpoint,
        )

        assert result is True
        checkpoint_path = os.path.join(temp_run_folder, config["CHECKPOINT_FILE"])
        assert os.path.exists(checkpoint_path), "checkpoint file should be created"

        checkpoint_res = compile_video.CheckpointManager(temp_run_folder, config)
        assert checkpoint_res.data["version"] == 3
        assert checkpoint_res.data["total_clips"] == len(sync_timeline)
        assert checkpoint_res.data["completed_clips"] == 0
        assert len(checkpoint_res.data["clip_states"]) == len(sync_timeline)
        assert all(
            state["status"] == "pending" for state in checkpoint_res.data["clip_states"].values()
        )

    def test_subtitle_missing_continues(
        self,
        config,
        temp_run_folder,
        sync_timeline,
        test_images_dir,
        dummy_audio_file,
        mock_ffmpeg_popen,
    ):
        """ENABLE_SUBTITLES=true but SRT missing renders without subtitles."""
        config["ENABLE_SUBTITLES"] = True

        encoder_config = compile_video.detect_hardware_encoder(config)
        result = compile_video.run_chunked_compile(
            config,
            encoder_config,
            sync_timeline,
            test_images_dir,
            dummy_audio_file,
            temp_run_folder,
        )

        assert result is True
        # assembly command has no subtitles filter
        assert "subtitles=" not in " ".join(_assembly_cmd(mock_ffmpeg_popen))

    def test_subtitles_burned_into_final_assembly(
        self,
        config,
        temp_run_folder,
        sync_timeline,
        test_images_dir,
        dummy_audio_file,
        dummy_transcript_file,
        mock_ffmpeg_popen,
    ):
        """Timestamped transcript present -> dynamic ASS built and burned into final assembly."""
        config["ENABLE_SUBTITLES"] = True

        encoder_config = compile_video.detect_hardware_encoder(config)
        result = compile_video.run_chunked_compile(
            config,
            encoder_config,
            sync_timeline,
            test_images_dir,
            dummy_audio_file,
            temp_run_folder,
        )

        assert result is True
        ass_path = os.path.join(temp_run_folder, "dynamic_subtitles.ass")
        assert os.path.exists(ass_path), "dynamic_subtitles.ass should be generated from transcript"
        # subtitles filter lives in the assembly filter script and references the
        # dynamic ASS file; the video stream is re-encoded (not copied) on burn-in
        script_path = os.path.join(temp_run_folder, "temp_clips", "filter_final_assembly.txt")
        with open(script_path, encoding="utf-8") as f:
            content = f.read()
        assert "subtitles=" in content
        assert "dynamic_subtitles.ass" in content
        assert "-c:v" in _assembly_cmd(mock_ffmpeg_popen)
        assert "[vout]" in _assembly_cmd(mock_ffmpeg_popen)

    def test_dry_run_still_builds_dynamic_subtitles(
        self,
        config,
        temp_run_folder,
        sync_timeline,
        test_images_dir,
        dummy_audio_file,
        dummy_transcript_file,
        mock_ffmpeg_popen,
    ):
        """DEBUG_DRY_RUN no longer gates subtitle generation; ASS is produced regardless."""
        config["ENABLE_SUBTITLES"] = True
        config["DEBUG_DRY_RUN"] = True

        encoder_config = compile_video.detect_hardware_encoder(config)
        result = compile_video.run_chunked_compile(
            config,
            encoder_config,
            sync_timeline,
            test_images_dir,
            dummy_audio_file,
            temp_run_folder,
        )

        assert result is True
        ass_path = os.path.join(temp_run_folder, "dynamic_subtitles.ass")
        assert os.path.exists(ass_path), (
            "dynamic_subtitles.ass should be generated regardless of dry run"
        )


class TestBuildChunkFilterGraph:
    """Tests for build_chunk_filter_graph(config, encoder_config, chunk_timeline, images_dir, ai_cameras, manual_cameras, anim_enabled)."""

    def test_filter_graph_includes_ken_burns_for_each_clip(
        self, config, sync_timeline, test_images_dir
    ):
        """Every clip (animated or static) routes through zoompan for exact frame counts."""
        encoder_config = compile_video.detect_hardware_encoder(config)
        ai_cameras = {"00_00": "zoom_in", "00_08": "pan_left", "00_15": "static"}
        manual_cameras = {}

        input_args, filter_complex, video_label = compile_video.build_chunk_filter_graph(
            config, encoder_config, sync_timeline, test_images_dir, ai_cameras, manual_cameras, True
        )

        # zoompan normalizes every clip's frame count; static clips use z='1.0'
        assert filter_complex.count("zoompan") == len(sync_timeline)
        assert f"concat=n={len(sync_timeline)}" in filter_complex
        assert "force_original_aspect_ratio=increase" in filter_complex
        assert "crop=" in filter_complex
        assert video_label == "vout"

    def test_manual_overrides_override_ai_cameras(
        self, config, sync_timeline, test_images_dir, monkeypatch
    ):
        """Manual camera overrides take precedence over AI decisions."""
        encoder_config = compile_video.detect_hardware_encoder(config)
        ai_cameras = {"00_08": "pan_left"}
        manual_cameras = {"00_08": "zoom_out"}

        captured = []

        def spy_ken_burns(config, frame_count, camera_action, pix_fmt="yuv420p"):
            captured.append(camera_action)
            return "spy"

        monkeypatch.setattr(compile_video, "build_ken_burns_filter", spy_ken_burns)
        compile_video.build_chunk_filter_graph(
            config, encoder_config, sync_timeline, test_images_dir, ai_cameras, manual_cameras, True
        )

        assert captured[1] == "zoom_out", "Manual override 'zoom_out' must override AI 'pan_left'"

    def test_animations_disabled_all_static(
        self, config, sync_timeline, test_images_dir, monkeypatch
    ):
        """anim_enabled=False forces the canonical static_hold action for every clip."""
        encoder_config = compile_video.detect_hardware_encoder(config)
        ai_cameras = {"00_00": "zoom_in", "00_08": "zoom_out", "00_15": "pan_left"}

        captured = []

        def spy_ken_burns(config, frame_count, camera_action, pix_fmt="yuv420p"):
            captured.append(camera_action)
            return "spy"

        monkeypatch.setattr(compile_video, "build_ken_burns_filter", spy_ken_burns)
        compile_video.build_chunk_filter_graph(
            config, encoder_config, sync_timeline, test_images_dir, ai_cameras, {}, False
        )

        assert captured == ["static_hold", "static_hold", "static_hold"]

    def test_input_args_count_matches_images(self, config, sync_timeline, test_images_dir):
        """Input args contain one -i per resolved image clip (no audio in chunk)."""
        encoder_config = compile_video.detect_hardware_encoder(config)

        input_args, _, _ = compile_video.build_chunk_filter_graph(
            config, encoder_config, sync_timeline, test_images_dir, {}, {}, True
        )

        assert input_args.count("-i") == len(sync_timeline)

    def test_empty_chunk_raises_valueerror(self, config, test_images_dir):
        """Chunk with no resolvable clips raises ValueError."""
        encoder_config = compile_video.detect_hardware_encoder(config)

        with pytest.raises(ValueError):
            compile_video.build_chunk_filter_graph(
                config, encoder_config, [], test_images_dir, {}, {}, True
            )

    def test_render_chunk_catches_valueerror_returns_none(
        self, config, temp_run_folder, sync_timeline, dummy_audio_file, monkeypatch
    ):
        """render_chunk converts unresolvable-image ValueError into None."""
        empty_images_dir = tempfile.mkdtemp()
        try:
            encoder_config = compile_video.detect_hardware_encoder(config)
            result = compile_video.render_chunk(
                config,
                encoder_config,
                sync_timeline,
                empty_images_dir,
                {},
                {},
                True,
                0,
                temp_run_folder,
                temp_run_folder,
                0,
            )
            assert result is None
        finally:
            os.rmdir(empty_images_dir)
