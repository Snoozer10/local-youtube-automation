from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from youtube_automation.video.engine import VideoCompiler, compile_video
from youtube_automation.video.runner import (
    FakeMediaRunner,
    MediaExecutionError,
    MediaProbeResult,
)
from youtube_automation.video.schema import (
    CompilationError,
    CompilationProfile,
    CompilationRequest,
    CompilationSpan,
    CompilationTarget,
    DialogueCue,
)


def _make_dummy_request(
    tmp_path: Path,
    *,
    profile: CompilationProfile = CompilationProfile.PREVIEW,
    target: CompilationTarget | None = None,
    encoder_override: str | None = None,
    total_frames: int = 90,
    dialogue_events: tuple[Any, ...] = ()
) -> CompilationRequest:
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"RIFF dummy audio data")

    img1 = tmp_path / "shot_01.png"
    img2 = tmp_path / "shot_02.png"
    img1.write_bytes(b"\x89PNG dummy image 1")
    img2.write_bytes(b"\x89PNG dummy image 2")

    mid = total_frames // 2
    span1 = CompilationSpan(
        index=0,
        shot_id="shot_01",
        start_frame=0,
        end_frame=mid,
        asset_id="asset_01",
    )
    span2 = CompilationSpan(
        index=1,
        shot_id="shot_02",
        start_frame=mid,
        end_frame=total_frames,
        asset_id="asset_02",
    )

    output_path = tmp_path / "final_output.mp4"

    return CompilationRequest(
        spans=(span1, span2),
        audio_path=audio_path,
        asset_paths={"asset_01": img1, "asset_02": img2},
        output_path=output_path,
        profile=profile,
        target=target,
        encoder_override=encoder_override,
        dialogue_events=dialogue_events,
    )


class TestCompilationSchemaValidation:
    """Test request and span validation contracts."""

    def test_span_duration_helpers(self) -> None:
        span = CompilationSpan(
            index=0,
            shot_id="s1",
            start_frame=30,
            end_frame=90,
            asset_id="a1",
        )
        assert span.duration_frames == 60
        assert span.duration_sec(30) == 2.0

        with pytest.raises(ValueError, match="positive"):
            span.duration_sec(0)

    def test_request_empty_spans_rejected(self, tmp_path: Path) -> None:
        req = CompilationRequest(
            spans=(),
            audio_path=tmp_path / "audio.wav",
            asset_paths={},
            output_path=tmp_path / "out.mp4",
        )
        with pytest.raises(ValueError, match="at least one span"):
            req.validate()

    def test_request_negative_start_frame_rejected(self, tmp_path: Path) -> None:
        span = CompilationSpan(
            index=0,
            shot_id="s1",
            start_frame=-5,
            end_frame=30,
            asset_id="a1",
        )
        req = CompilationRequest(
            spans=(span,),
            audio_path=tmp_path / "audio.wav",
            asset_paths={"a1": tmp_path / "img.png"},
            output_path=tmp_path / "out.mp4",
        )
        with pytest.raises(ValueError, match="negative start_frame"):
            req.validate()

    def test_request_inverted_frame_range_rejected(self, tmp_path: Path) -> None:
        span = CompilationSpan(
            index=0,
            shot_id="s1",
            start_frame=30,
            end_frame=20,
            asset_id="a1",
        )
        req = CompilationRequest(
            spans=(span,),
            audio_path=tmp_path / "audio.wav",
            asset_paths={"a1": tmp_path / "img.png"},
            output_path=tmp_path / "out.mp4",
        )
        with pytest.raises(ValueError, match="strictly greater than"):
            req.validate()

    def test_request_missing_asset_path_rejected(self, tmp_path: Path) -> None:
        span = CompilationSpan(
            index=0,
            shot_id="s1",
            start_frame=0,
            end_frame=30,
            asset_id="unregistered_asset",
        )
        req = CompilationRequest(
            spans=(span,),
            audio_path=tmp_path / "audio.wav",
            asset_paths={"other_asset": tmp_path / "img.png"},
            output_path=tmp_path / "out.mp4",
        )
        with pytest.raises(ValueError, match="missing from asset_paths"):
            req.validate()

    def test_request_overlapping_spans_rejected(self, tmp_path: Path) -> None:
        span1 = CompilationSpan(
            index=0, shot_id="s1", start_frame=0, end_frame=30, asset_id="a1"
        )
        span2 = CompilationSpan(
            index=1, shot_id="s2", start_frame=25, end_frame=60, asset_id="a2"
        )
        req = CompilationRequest(
            spans=(span1, span2),
            audio_path=tmp_path / "audio.wav",
            asset_paths={"a1": tmp_path / "1.png", "a2": tmp_path / "2.png"},
            output_path=tmp_path / "out.mp4",
        )
        with pytest.raises(ValueError, match="overlaps with"):
            req.validate()


class TestCompilationTargetValidation:
    """Test CompilationTarget constraints."""

    def test_valid_target(self) -> None:
        target = CompilationTarget(width=1920, height=1080, fps=30)
        assert target.width == 1920
        assert target.height == 1080
        assert target.fps == 30
        assert target.color_range == "tv"

    def test_odd_dimensions_rejected(self) -> None:
        with pytest.raises(ValueError, match="even"):
            CompilationTarget(width=1921, height=1080)

        with pytest.raises(ValueError, match="even"):
            CompilationTarget(width=1920, height=1081)

    def test_non_positive_fps_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            CompilationTarget(width=1920, height=1080, fps=0)

    def test_invalid_color_range_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid color range"):
            CompilationTarget(width=1920, height=1080, color_range="invalid")


class TestResolutionAndNegotiation:
    """Test target resolution and encoder priority negotiation."""

    def test_preview_profile_resolution(self, tmp_path: Path) -> None:
        compiler = VideoCompiler()
        req = _make_dummy_request(tmp_path, profile=CompilationProfile.PREVIEW)
        target = compiler.resolve_target(req)

        assert target.width == 1920
        assert target.height == 1080
        assert target.fps == 30
        assert target.pixel_format == "yuv420p"
        assert target.color_range == "tv"

    def test_broadcast_master_resolution_adr0002(self, tmp_path: Path) -> None:
        compiler = VideoCompiler()
        req = _make_dummy_request(tmp_path, profile=CompilationProfile.BROADCAST_MASTER)
        target = compiler.resolve_target(req)

        # ADR 0002: 1440p master at CFR 30fps with nv12 QSV format
        assert target.width == 2560
        assert target.height == 1440
        assert target.fps == 30
        assert target.pixel_format == "nv12"
        assert target.color_range == "tv"

    def test_explicit_target_overrides_profile(self, tmp_path: Path) -> None:
        compiler = VideoCompiler()
        custom = CompilationTarget(width=1280, height=720, fps=60)
        req = _make_dummy_request(
            tmp_path, profile=CompilationProfile.BROADCAST_MASTER, target=custom
        )
        target = compiler.resolve_target(req)

        assert target.width == 1280
        assert target.height == 720
        assert target.fps == 60

    def test_encoder_negotiation_priority_qsv_selected(self) -> None:
        fake_runner = FakeMediaRunner(available_encoders={"h264_qsv", "h264_nvenc", "libx264"})
        compiler = VideoCompiler(runner=fake_runner)
        cfg = compiler.detect_encoder({"OUTPUT_FPS": 30})

        assert cfg["video_codec"] == "h264_qsv"
        assert cfg["hwaccel"] == "qsv"
        assert "-look_ahead" in cfg["encoder_args"]
        assert cfg["encoder_args"][cfg["encoder_args"].index("-look_ahead") + 1] == "0"
        assert "-pix_fmt" in cfg["encoder_args"]
        assert cfg["encoder_args"][cfg["encoder_args"].index("-pix_fmt") + 1] == "nv12"

    def test_encoder_negotiation_priority_nvenc_selected_when_no_qsv(self) -> None:
        fake_runner = FakeMediaRunner(available_encoders={"h264_nvenc", "libx264"})
        compiler = VideoCompiler(runner=fake_runner)
        cfg = compiler.detect_encoder({"OUTPUT_FPS": 30})

        assert cfg["video_codec"] == "h264_nvenc"
        assert cfg["hwaccel"] == "cuda"

    def test_encoder_negotiation_cpu_fallback_when_no_hardware(self) -> None:
        fake_runner = FakeMediaRunner(available_encoders={"libx264"})
        compiler = VideoCompiler(runner=fake_runner)
        cfg = compiler.detect_encoder({"OUTPUT_FPS": 30})

        assert cfg["video_codec"] == "libx264"
        assert cfg["hwaccel"] == "none"
        assert "-preset" in cfg["encoder_args"]
        assert "-crf" in cfg["encoder_args"]
        assert "-tune" in cfg["encoder_args"]

    def test_encoder_override_forces_selected_codec(self) -> None:
        fake_runner = FakeMediaRunner(available_encoders={"h264_qsv", "libx264"})
        compiler = VideoCompiler(runner=fake_runner)
        cfg = compiler.detect_encoder({"OUTPUT_FPS": 30}, override="libx264")

        assert cfg["video_codec"] == "libx264"


class TestVideoCompilerExecution:
    """Test end-to-end compilation through FakeMediaRunner."""

    def test_preview_compile_success(self, tmp_path: Path) -> None:
        fake_runner = FakeMediaRunner(available_encoders={"libx264"})
        compiler = VideoCompiler(runner=fake_runner)
        req = _make_dummy_request(tmp_path, profile=CompilationProfile.PREVIEW)

        result = compiler.compile(req)

        assert result.verified is True
        assert result.total_frames == 90
        assert result.fps == 30
        assert result.width == 1920
        assert result.height == 1080
        assert result.encoder_used == "libx264"
        assert result.fallback_occurred is False
        assert result.clip_count == 2
        assert req.output_path.exists()

        # Check recorded commands
        cmd_types = [cmd[0] for cmd in fake_runner.commands_run]
        assert all(c == "ffmpeg" for c in cmd_types)
        assert len(fake_runner.commands_run) >= 3  # clip 0, clip 1, and concat

    def test_broadcast_master_compile_success(self, tmp_path: Path) -> None:
        fake_runner = FakeMediaRunner(available_encoders={"h264_qsv", "libx264"})
        # Custom probe for 1440p
        fake_runner.register_probe(
            tmp_path / "final_output.mp4",
            MediaProbeResult(
                duration=3.0,
                total_frames=90,
                width=2560,
                height=1440,
                fps=30.0,
                pix_fmt="yuv420p",
                color_range="tv",
                has_audio=True,
            ),
        )

        compiler = VideoCompiler(runner=fake_runner)
        req = _make_dummy_request(tmp_path, profile=CompilationProfile.BROADCAST_MASTER)

        result = compiler.compile(req)

        assert result.verified is True
        assert result.width == 2560
        assert result.height == 1440
        assert result.encoder_used == "h264_qsv"
        assert result.fallback_occurred is False

    def test_midstream_hardware_failure_falls_back_to_libx264(self, tmp_path: Path) -> None:
        # Simulate qsv available during probe, but crashing during clip encode
        fake_runner = FakeMediaRunner(
            available_encoders={"h264_qsv", "libx264"},
            error_on_encoder={"h264_qsv"},
        )
        compiler = VideoCompiler(runner=fake_runner)
        req = _make_dummy_request(tmp_path)

        result = compiler.compile(req)

        assert result.verified is True
        assert result.fallback_occurred is True
        assert result.fallback_from == "h264_qsv"
        assert result.encoder_used == "libx264"

    def test_software_failure_raises_typed_compilation_error(self, tmp_path: Path) -> None:
        fake_runner = FakeMediaRunner(
            available_encoders={"libx264"},
            error_on_encoder={"libx264"},
        )
        compiler = VideoCompiler(runner=fake_runner)
        req = _make_dummy_request(tmp_path)

        with pytest.raises(CompilationError) as exc_info:
            compiler.compile(req)

        err = exc_info.value
        assert err.stage == "clip_encode"
        assert err.clip_index == 0
        assert err.returncode == 1
        assert "Hardware failure with libx264" in err.stderr

    def test_concat_failure_raises_typed_compilation_error(self, tmp_path: Path) -> None:
        fake_runner = FakeMediaRunner(available_encoders={"libx264"})

        # Let clips succeed, but fail concat assembly
        orig_run = fake_runner.run_ffmpeg

        def run_with_concat_failure(args: list[str], **kwargs: Any) -> tuple[str, str]:
            if "-f" in args and "concat" in args:
                raise MediaExecutionError("Concat broken", cmd=["ffmpeg"] + list(args), returncode=2, stderr="Corrupt concat")
            return orig_run(args, **kwargs)

        fake_runner.run_ffmpeg = run_with_concat_failure  # type: ignore

        compiler = VideoCompiler(runner=fake_runner)
        req = _make_dummy_request(tmp_path)

        with pytest.raises(CompilationError) as exc_info:
            compiler.compile(req)

        err = exc_info.value
        assert err.stage == "assembly"
        assert err.returncode == 2
        assert "Corrupt concat" in err.stderr

    def test_verification_frame_mismatch_raises_compilation_error(self, tmp_path: Path) -> None:
        fake_runner = FakeMediaRunner(available_encoders={"libx264"})
        # Register probe with 80 frames instead of expected 90
        fake_runner.register_probe(
            tmp_path / "final_output.mp4",
            MediaProbeResult(
                duration=2.67,
                total_frames=80,
                width=1920,
                height=1080,
                fps=30.0,
                pix_fmt="yuv420p",
                color_range="tv",
                has_audio=True,
            ),
        )
        compiler = VideoCompiler(runner=fake_runner)
        req = _make_dummy_request(tmp_path)

        with pytest.raises(CompilationError, match="Frame count mismatch"):
            compiler.compile(req)

    def test_convenience_compile_video(self, tmp_path: Path) -> None:
        fake_runner = FakeMediaRunner(available_encoders={"libx264"})
        req = _make_dummy_request(tmp_path)

        result = compile_video(req, runner=fake_runner)
        assert result.verified is True
        assert result.total_frames == 90

    def test_midstream_hardware_failure_on_second_clip_re_encodes_all_with_libx264(
        self, tmp_path: Path
    ) -> None:
        class MidstreamFailingRunner(FakeMediaRunner):
            def run_ffmpeg(self, args: list[str], **kwargs: Any) -> tuple[str, str]:
                # Let clip 0 succeed with h264_qsv, but fail when clip 1 attempts h264_qsv
                if "h264_qsv" in args and "clip_00001.pending.mp4" in " ".join(args):
                    raise MediaExecutionError(
                        "QSV device crash on clip 1",
                        cmd=["ffmpeg"] + list(args),
                        returncode=1,
                        stderr="QSV device lost",
                    )
                return super().run_ffmpeg(args, **kwargs)

        fake_runner = MidstreamFailingRunner(available_encoders={"h264_qsv", "libx264"})
        compiler = VideoCompiler(runner=fake_runner)
        req = _make_dummy_request(tmp_path)

        result = compiler.compile(req)

        assert result.verified is True
        assert result.fallback_occurred is True
        assert result.fallback_from == "h264_qsv"
        assert result.encoder_used == "libx264"

        # Concat must have been fed libx264 clips from the fallback work_dir
        concat_cmds = [cmd for cmd in fake_runner.commands_run if "concat" in cmd]
        assert len(concat_cmds) == 1
        concat_idx = concat_cmds[0].index("-i") + 1
        concat_txt = Path(concat_cmds[0][concat_idx]).read_text(encoding="utf-8")
        assert result.generation_hash in concat_txt

    def test_dialogue_subtitles_sliced_and_composed_in_filtergraph(
        self, tmp_path: Path
    ) -> None:
        fake_runner = FakeMediaRunner(available_encoders={"libx264"})
        compiler = VideoCompiler(runner=fake_runner)

        # 2 spans: 0..45 and 45..90 frames
        dialogue = (
            DialogueCue(start_frame=5, end_frame=35, text="First dialogue cue"),
            DialogueCue(start_frame=40, end_frame=60, text="Bridging dialogue cue"),
        )
        req = _make_dummy_request(tmp_path, dialogue_events=dialogue)
        result = compiler.compile(req)

        assert result.verified is True

        # Find graph scripts in the compiler scratch dir
        scratch_dir = req.work_dir or (tmp_path / ".compiler_scratch")
        dialogue_ass_files = list(scratch_dir.rglob("dialogue_*.ass"))
        assert len(dialogue_ass_files) >= 1

        contents = [f.read_text(encoding="utf-8") for f in dialogue_ass_files]
        combined = "\n".join(contents)
        assert "First dialogue cue" in combined
        assert "Bridging dialogue cue" in combined
