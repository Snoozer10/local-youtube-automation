from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import compile_video
import youtube_automation.video.engine as engine_mod
from youtube_automation.video.compiler import (
    build_compilation_request_from_run,
    parse_compile_args,
)
from youtube_automation.video.runner import FakeMediaRunner
from youtube_automation.video.schema import (
    CompilationProfile,
    CompilationRequest,
    DialogueCue,
)


def _setup_synthetic_run_dir(
    tmp_path: Path,
    *,
    has_audio: bool = True,
    has_timeline: bool = True,
    has_images: bool = True,
    has_brief: bool = False,
    subtitles_enabled: bool = False,
) -> Path:
    """Helper to create a well-formed synthetic run folder for CLI testing."""
    run_dir = tmp_path / "test_run"
    run_dir.mkdir(parents=True, exist_ok=True)

    if has_audio:
        audio_dir = run_dir / "audacity_voice"
        audio_dir.mkdir(parents=True, exist_ok=True)
        (audio_dir / "full_episode_voice.wav").write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00")

    if has_timeline:
        timeline_data = {
            "version": "1.0.0",
            "fps": 30,
            "total_frames": 60,
            "audio_duration": 2.0,
            "spans": [
                {
                    "index": 0,
                    "name": "00_00",
                    "start": 0.0,
                    "end": 1.0,
                    "start_frame": 0,
                    "end_frame": 30,
                    "frame_count": 30,
                    "text": "First test span sentence.",
                    "occurrence": 1,
                },
                {
                    "index": 1,
                    "name": "00_01",
                    "start": 1.0,
                    "end": 2.0,
                    "start_frame": 30,
                    "end_frame": 60,
                    "frame_count": 30,
                    "text": "Second test span sentence.",
                    "occurrence": 1,
                },
            ],
        }
        (run_dir / "timeline.json").write_text(
            json.dumps(timeline_data, indent=2), encoding="utf-8"
        )

    if has_images:
        img_dir = run_dir / "generated_images"
        img_dir.mkdir(parents=True, exist_ok=True)
        (img_dir / "00_00.png").write_bytes(b"\x89PNG\r\n\x1a\nfakeimage0")
        (img_dir / "00_01.png").write_bytes(b"\x89PNG\r\n\x1a\nfakeimage1")

    if has_brief:
        (run_dir / "episode_brief.json").write_text(
            json.dumps({"channel_name": "test_channel"}), encoding="utf-8"
        )

    cfg_lines = [
        "OUTPUT_WIDTH=2560",
        "OUTPUT_HEIGHT=1440",
        "OUTPUT_FPS=30",
        f"ENABLE_SUBTITLES={'True' if subtitles_enabled else 'False'}",
        "ENABLE_ANIMATIONS=True",
    ]
    (run_dir / "video_config.txt").write_text("\n".join(cfg_lines), encoding="utf-8")

    return run_dir


class TestParseCompileArgs:
    """Test CLI argument parsing capabilities."""

    def test_positional_run_folder(self) -> None:
        args = parse_compile_args("youtube_runs/demo_run")
        assert args.run_folder == "youtube_runs/demo_run"
        assert args.run_folder_flag is None

    def test_flag_run_folder(self) -> None:
        args = parse_compile_args(["--run-folder", "youtube_runs/flag_run"])
        assert args.run_folder_flag == "youtube_runs/flag_run"
        assert args.run_folder is None

    def test_flags_preview_encoder_output_fps(self) -> None:
        args = parse_compile_args(
            [
                "--preview",
                "--encoder",
                "libx264",
                "-o",
                "custom_output.mp4",
                "--fps",
                "24",
                "--width",
                "1920",
                "--height",
                "1080",
            ]
        )
        assert args.preview is True
        assert args.encoder == "libx264"
        assert args.output == "custom_output.mp4"
        assert args.fps == 24
        assert args.width == 1920
        assert args.height == 1080

    def test_empty_args_defaults(self) -> None:
        args = parse_compile_args([])
        assert args.run_folder is None
        assert args.run_folder_flag is None
        assert args.preview is False
        assert args.profile is None
        assert args.encoder is None
        assert args.output is None


class TestBuildCompilationRequest:
    """Test translating run directory manifests into structured CompilationRequest."""

    def test_missing_run_folder_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="Run folder not found"):
            build_compilation_request_from_run(tmp_path / "non_existent_folder")

    def test_missing_voice_track_raises(self, tmp_path: Path) -> None:
        run_dir = _setup_synthetic_run_dir(tmp_path, has_audio=False)
        with pytest.raises(FileNotFoundError, match="No voice track found"):
            build_compilation_request_from_run(run_dir)

    def test_valid_run_manifest_builds_broadcast_master_request(
        self, tmp_path: Path
    ) -> None:
        run_dir = _setup_synthetic_run_dir(tmp_path)
        fake_runner = FakeMediaRunner()

        req = build_compilation_request_from_run(
            run_dir,
            config={"OUTPUT_WIDTH": 2560, "OUTPUT_HEIGHT": 1440, "OUTPUT_FPS": 30},
            runner=fake_runner,
        )

        assert isinstance(req, CompilationRequest)
        assert req.profile == CompilationProfile.BROADCAST_MASTER
        assert req.target is not None
        assert req.target.width == 2560
        assert req.target.height == 1440
        assert req.target.fps == 30
        assert req.target.pixel_format == "nv12"
        assert req.output_path == run_dir / "youtube_ready_video.mp4"
        assert len(req.spans) == 2
        assert req.spans[0].shot_id == "shot_00000"
        assert req.spans[0].start_frame == 0
        assert req.spans[0].end_frame == 30
        assert req.spans[1].shot_id == "shot_00001"
        assert req.spans[1].start_frame == 30
        assert req.spans[1].end_frame == 90
        assert len(req.asset_paths) == 2
        assert req.spans[0].asset_id in req.asset_paths
        assert req.asset_paths[req.spans[0].asset_id].exists()

    def test_fps_flag_preserved_without_explicit_dimensions(
        self, tmp_path: Path
    ) -> None:
        run_dir = _setup_synthetic_run_dir(tmp_path)
        fake_runner = FakeMediaRunner()

        req = build_compilation_request_from_run(
            run_dir,
            fps=24,
            runner=fake_runner,
        )
        assert req.target is not None
        assert req.target.fps == 24
        assert req.target.width == 2560
        assert req.target.height == 1440
        assert req.target.pixel_format == "nv12"

    def test_custom_dimensions_preserve_nv12_for_broadcast_master(
        self, tmp_path: Path
    ) -> None:
        run_dir = _setup_synthetic_run_dir(tmp_path)
        fake_runner = FakeMediaRunner()

        req = build_compilation_request_from_run(
            run_dir,
            width=1280,
            height=720,
            runner=fake_runner,
        )
        assert req.target is not None
        assert req.target.width == 1280
        assert req.target.height == 720
        assert req.target.pixel_format == "nv12"

    def test_preview_profile_and_target_resolution(self, tmp_path: Path) -> None:
        run_dir = _setup_synthetic_run_dir(tmp_path)
        fake_runner = FakeMediaRunner()

        req = build_compilation_request_from_run(
            run_dir,
            profile=CompilationProfile.PREVIEW,
            width=1280,
            height=720,
            runner=fake_runner,
        )

        assert req.profile == CompilationProfile.PREVIEW
        assert req.target is not None
        assert req.target.width == 1280
        assert req.target.height == 720
        assert req.target.pixel_format == "yuv420p"

    def test_external_ass_takes_precedence_over_derived_dialogue(self, tmp_path: Path) -> None:
        run_dir = _setup_synthetic_run_dir(tmp_path, subtitles_enabled=True)
        (run_dir / "dynamic_subtitles.ass").write_text(
            "[Script Info]\n[Events]\nDialogue: 0,0:00:00.000,0:00:01.000,Default,Test\n",
            encoding="utf-8",
        )
        fake_runner = FakeMediaRunner()

        req = build_compilation_request_from_run(
            run_dir,
            config={"ENABLE_SUBTITLES": True},
            runner=fake_runner,
        )

        assert req.subtitles_path is not None
        assert req.subtitles_path.is_file()
        assert req.subtitles_path.suffix.lower() == ".ass"
        assert req.dialogue_events == ()

    def test_dialogue_extraction_is_fallback_without_external_ass(
        self, tmp_path: Path
    ) -> None:
        run_dir = _setup_synthetic_run_dir(tmp_path, subtitles_enabled=True)
        req = build_compilation_request_from_run(
            run_dir,
            config={"ENABLE_SUBTITLES": True},
            runner=FakeMediaRunner(),
        )

        assert req.subtitles_path is None
        assert len(req.dialogue_events) == 2
        assert isinstance(req.dialogue_events[0], DialogueCue)
        assert req.dialogue_events[0].text == "First test span sentence."
        assert req.dialogue_events[1].text == "Second test span sentence."


class TestMainExecutionAndDelegation:
    """Test facade entrypoint execution and delegation to VideoCompiler."""

    def test_main_compiles_successfully_with_fake_runner(
        self, tmp_path: Path
    ) -> None:
        run_dir = _setup_synthetic_run_dir(tmp_path)
        fake_runner = FakeMediaRunner(
            default_total_frames=60,
            default_duration=2.0,
            default_width=1920,
            default_height=1080,
            default_fps=30.0,
            default_pix_fmt="yuv420p",
        )

        res = compile_video.main([str(run_dir)], runner=fake_runner)

        assert res == 0
        output_file = run_dir / "youtube_ready_video.mp4"
        assert output_file.exists()
        assert len(fake_runner.commands_run) >= 3
        # Verify clip rendering and final assembly commands were executed
        assert any("-vf" in cmd for cmd in fake_runner.commands_run)
        assert any("-f" in cmd and "concat" in cmd for cmd in fake_runner.commands_run)

    def test_main_missing_run_folder_exits_1(self) -> None:
        with pytest.raises(SystemExit) as exc:
            compile_video.main(["non_existent_folder_xyz_98765"])
        assert exc.value.code == 1

    def test_main_routes_episode_brief_to_render_plan(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        run_dir = _setup_synthetic_run_dir(tmp_path, has_brief=True)
        mock_render_plan = MagicMock(return_value="mock_plan_rendered")
        monkeypatch.setattr(
            "youtube_automation.production.render.render_plan", mock_render_plan
        )

        res = compile_video.main([str(run_dir)])
        assert res == 0
        mock_render_plan.assert_called_once()


class TestFacadeArchitectureIntegrity:
    """Test that compile_video.py facade shim contains zero duplicate compilation logic."""

    def test_root_compile_video_contains_zero_ffmpeg_execution(self) -> None:
        root_facade = Path("compile_video.py").read_text(encoding="utf-8")
        assert "subprocess.run" not in root_facade
        assert "subprocess.Popen" not in root_facade
        assert "run_chunked_compile" not in root_facade
        assert "_FacadeProxy" in root_facade
        assert "compiler_mod.main" in root_facade

    def test_facade_re_exports_unified_engine_symbols(self) -> None:
        assert hasattr(compile_video, "main")
        assert hasattr(compile_video, "build_compilation_request_from_run")
        assert hasattr(compile_video, "parse_compile_args")
        assert hasattr(compile_video, "VideoCompiler")
        assert hasattr(compile_video, "compile_video")

    def test_facade_bidirectional_monkeypatch_sync_engine(self) -> None:
        test_val = "unit_test_sync_value_42"
        compile_video._test_sentinel_attr = test_val  # type: ignore[attr-defined]
        try:
            assert getattr(engine_mod, "_test_sentinel_attr", None) == test_val
        finally:
            if hasattr(engine_mod, "_test_sentinel_attr"):
                delattr(engine_mod, "_test_sentinel_attr")
            if hasattr(compile_video, "_test_sentinel_attr"):
                delattr(compile_video, "_test_sentinel_attr")
