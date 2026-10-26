"""Unit tests for consolidated filtergraph generation and visual overlays behind VideoCompiler.

Conforms to ADR 0002, ADR 0006, and Ticket 3 (Issue #26).
Exercises procedural Ken Burns smoothstep kinematics, dynamic duration scaling,
clamped zero-safe evaluation clip(on, 0, N), ASS overlay pass composition,
TV color range normalization, and file-backed -/filter_complex scripts.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from youtube_automation.video.engine import VideoCompiler
from youtube_automation.video.filter_graph import (
    build_camera_filter,
    build_span_filter_graph,
    normalize_color_range_filter,
    pixel_format_for_encoder,
)
from youtube_automation.video.runner import FakeMediaRunner, MediaProbeResult
from youtube_automation.video.schema import (
    CompilationProfile,
    CompilationRequest,
    CompilationSpan,
    CompilationTarget,
)
from youtube_automation.video.subtitles import (
    _ass_time,
    _safe_ass_text,
    _scaled_timer_ass_time,
    _timer_ass_time,
    format_dialogue_ass,
    overlay_ass,
    pictogram_ass,
    timer_segments,
)

# ---------------------------------------------------------------------------
# 1. Camera Kinematics & Clamped Smoothstep Tests
# ---------------------------------------------------------------------------

class TestCameraKinematics:
    """Verifies procedural Ken Burns pan-and-zoom expressions and zero-safe clamps."""

    def test_hold_motion_has_no_temporal_expressions(self) -> None:
        span = CompilationSpan(
            index=0,
            shot_id="shot_001",
            start_frame=0,
            end_frame=90,
            asset_id="asset_1",
            camera_motion="hold",
            zoom=1.0,
        )
        filt = build_camera_filter(span, 1920, 1080, 30)
        assert "z='1.0'" in filt
        assert "clip(on," not in filt
        assert "zoompan=z='1.0'" in filt
        assert "s=1920x1080:fps=30" in filt

    def test_push_motion_applies_zero_safe_smoothstep_clamp(self) -> None:
        span = CompilationSpan(
            index=0,
            shot_id="shot_002",
            start_frame=0,
            end_frame=180,
            asset_id="asset_1",
            camera_motion="push",
            zoom=1.08,
            metadata={"focal_x": 0.35, "focal_y": 0.65},
        )
        filt = build_camera_filter(span, 1920, 1080, 30)
        # Denominator is frames - 1 = 179
        assert "clip(on,0,179)" in filt
        # Smoothstep ease curve: t*t*(3-2*t)
        assert "(3-2*(" in filt
        # Focal center tracking
        assert "iw*0.35" in filt
        assert "ih*0.65" in filt

    def test_single_frame_span_avoids_division_by_zero(self) -> None:
        span = CompilationSpan(
            index=0,
            shot_id="shot_single",
            start_frame=0,
            end_frame=1,
            asset_id="asset_1",
            camera_motion="push",
            zoom=1.05,
        )
        filt = build_camera_filter(span, 640, 360, 30)
        # For frames=1, den = max(1, 0) = 1
        assert "clip(on,0,1)/1" in filt

    def test_dynamic_duration_scaling_applies_within_bounds(self) -> None:
        # At 30fps: 75 frames = 2.5s -> scale = 1.06
        span_short = CompilationSpan(
            index=0,
            shot_id="shot_short",
            start_frame=0,
            end_frame=75,
            asset_id="asset_1",
            camera_motion="push",
            zoom=1.0,
        )
        filt_short = build_camera_filter(span_short, 1920, 1080, 30, dynamic_scale=True)
        assert "1+(1.06-1)" in filt_short

        # At 30fps: 135 frames = 4.5s -> scale = 1.10
        span_long = CompilationSpan(
            index=1,
            shot_id="shot_long",
            start_frame=0,
            end_frame=135,
            asset_id="asset_1",
            camera_motion="push",
            zoom=1.0,
        )
        filt_long = build_camera_filter(span_long, 1920, 1080, 30, dynamic_scale=True)
        assert "1+(1.1-1)" in filt_long

    def test_pan_motion_preserves_focal_bounds(self) -> None:
        span_pan = CompilationSpan(
            index=0,
            shot_id="shot_pan",
            start_frame=0,
            end_frame=90,
            asset_id="asset_1",
            camera_motion="pan_left",
            zoom=1.10,
        )
        filt = build_camera_filter(span_pan, 1920, 1080, 30)
        assert "0.75*iw/zoom" in filt
        assert "0.25*iw/zoom" in filt

    def test_pan_motion_without_safe_travel_raises_error(self) -> None:
        span_unsafe = CompilationSpan(
            index=0,
            shot_id="shot_unsafe",
            start_frame=0,
            end_frame=90,
            asset_id="asset_1",
            camera_motion="pan_right",
            zoom=1.02,
            metadata={"focal_x": 0.01},
        )
        with pytest.raises(ValueError, match="No safe pan travel"):
            build_camera_filter(span_unsafe, 1920, 1080, 30)


# ---------------------------------------------------------------------------
# 2. ASS Subtitles & Visual Overlays Tests
# ---------------------------------------------------------------------------

class TestSubtitlesAndOverlays:
    """Verifies single-pass compositing of ASS subtitles and graphic copy cues."""

    def test_safe_ass_text_escapes_formatting_controls(self) -> None:
        raw = "Line 1 {\\b1}Bold{\\b0}\nLine 2\\With\\Slashes\r"
        escaped = _safe_ass_text(raw)
        assert "{\\b1}" not in escaped
        assert "(" in escaped and ")" in escaped
        assert "\\N" in escaped
        assert "＼" in escaped
        assert "\r" not in escaped

    def test_time_formatting_functions(self) -> None:
        assert _ass_time(0, 30) == "0:00:00.00"
        assert _ass_time(45, 30) == "0:00:01.50"
        assert _timer_ass_time(60, 30) == "0:00:02.00"
        assert _scaled_timer_ass_time(30, 30) == "0:00:02.00"

    def test_schulte_matrix_generates_all_36_numbers_and_grid(self) -> None:
        overlays = [
            {
                "kind": "data_grid",
                "preset": "schulte_6x6",
                "start_frame": 0,
                "end_frame": 180,
                "x": 0.15,
                "y": 0.15,
                "width": 0.7,
                "height": 0.7,
                "highlight_cells": [0, 5],
            }
        ]
        span = CompilationSpan(
            index=0,
            shot_id="schulte_span",
            start_frame=0,
            end_frame=180,
            asset_id="asset_1",
            overlays=tuple(overlays),
        )
        ass_text = overlay_ass(span, 1920, 1080, 30)
        assert "PlayResX: 1920" in ass_text
        assert "PlayResY: 1080" in ass_text
        # Verify grid lines rendered
        assert "m 0 0 l 1344 0 1344 756" in ass_text
        # Verify numbers 1-36 are all present in dialogue events
        for num in map(str, range(1, 37)):
            assert f"}}{num}\n" in ass_text or f"}}{num}\r\n" in ass_text

    def test_timer_countdown_segments(self) -> None:
        segs = timer_segments(
            start_frame=0,
            end_frame=90,
            shot_start_frame=0,
            clock_start_frame=0,
            seconds=30,
            fps=30,
        )
        assert len(segs) == 3
        assert segs[0] == (0, 30, "00:30")
        assert segs[1] == (30, 60, "00:29")
        assert segs[2] == (60, 90, "00:28")

    def test_pictogram_generation_and_movement(self) -> None:
        lines_static = pictogram_ass("phone", 100, 200, 80, 80)
        assert len(lines_static) == 4
        assert "\\pos(100,200)" in lines_static[0]

        lines_moving = pictogram_ass(
            "eye", 50, 50, 100, 100, move_to=(200, 300), move_ms=500
        )
        assert len(lines_moving) == 4
        assert "\\move(50,50,200,300,0,500)" in lines_moving[0]

    def test_dialogue_subtitles_formatting(self) -> None:
        dialogue = [
            {"start_frame": 0, "end_frame": 30, "text": "مرحباً بكم"},
            {"start_frame": 30, "end_frame": 60, "text": "في هذه الحلقة"},
        ]
        ass = format_dialogue_ass(dialogue, 1920, 1080, 30)
        assert "مرحباً بكم" in ass
        assert "في هذه الحلقة" in ass
        assert "0:00:00.00,0:00:01.00" in ass
        assert "0:00:01.00,0:00:02.00" in ass


# ---------------------------------------------------------------------------
# 3. TV Color Range & Hardware Pixel Format Normalization Tests
# ---------------------------------------------------------------------------

class TestColorRangeAndPixelFormats:
    """Verifies output stream normalization conforming to broadcast master specs."""

    def test_pixel_format_selection(self) -> None:
        assert pixel_format_for_encoder({"video_codec": "h264_qsv"}) == "nv12"
        assert pixel_format_for_encoder({"video_codec": "libx264"}) == "yuv420p"
        assert pixel_format_for_encoder({"video_codec": "h264_nvenc"}) == "yuv420p"

    def test_normalize_color_range_filter(self) -> None:
        filt_nv12 = normalize_color_range_filter("nv12")
        assert "in_range=auto:out_range=tv" in filt_nv12
        assert "format=nv12" in filt_nv12
        assert "setparams=range=tv" in filt_nv12

        filt_yuv = normalize_color_range_filter("yuv420p")
        assert "in_range=auto:out_range=tv" in filt_yuv
        assert "format=yuv420p" in filt_yuv
        assert "setparams=range=tv" in filt_yuv

        with pytest.raises(ValueError, match="must be nv12 or yuv420p"):
            normalize_color_range_filter("rgb24")


# ---------------------------------------------------------------------------
# 4. File-Backed -/filter_complex Script Contract Tests
# ---------------------------------------------------------------------------

class TestFileBackedFiltergraphContract:
    """Verifies file-backed filter script generation conforming to modern FFmpeg contract."""

    def test_simple_span_uses_inline_vf(self, tmp_path: Path) -> None:
        span = CompilationSpan(
            index=0,
            shot_id="shot_simple",
            start_frame=0,
            end_frame=30,
            asset_id="asset_1",
            camera_motion="hold",
        )
        target = CompilationTarget(width=1920, height=1080, fps=30)
        encoder = {"video_codec": "libx264"}

        result = build_span_filter_graph(
            span=span,
            target=target,
            encoder_config=encoder,
            work_dir=tmp_path,
            force_file_backed=False,
            cmd_length_threshold=2000,
        )

        assert result.is_file_backed is False
        assert result.args[0] == "-vf"
        assert result.script_path is None
        assert "format=yuv420p,setparams=range=tv" in result.filter_string

    def test_force_file_backed_produces_script(self, tmp_path: Path) -> None:
        span = CompilationSpan(
            index=3,
            shot_id="shot_file_backed",
            start_frame=0,
            end_frame=60,
            asset_id="asset_1",
            camera_motion="hold",
        )
        target = CompilationTarget(width=1920, height=1080, fps=30)
        encoder = {"video_codec": "libx264"}

        result = build_span_filter_graph(
            span=span,
            target=target,
            encoder_config=encoder,
            work_dir=tmp_path,
            force_file_backed=True,
        )

        assert result.is_file_backed is True
        assert result.args[0] == "-/filter_complex"
        assert result.args[1] == "graph_00003.txt"
        assert result.args[2] == "-map"
        assert result.args[3] == "[vout]"

        # Script must be written to disk with [0:v]...[vout]
        assert result.script_path is not None
        assert result.script_path.exists()
        content = result.script_path.read_text(encoding="utf-8")
        assert content.startswith("[0:v]")
        assert content.endswith("[vout]")
        assert "setparams=range=tv" in content

    def test_overlays_trigger_file_backed_script_and_ass_files(self, tmp_path: Path) -> None:
        overlays = [
            {"kind": "label", "text": "Test Headline", "start_frame": 0, "end_frame": 60, "x": 0.2, "y": 0.2},
            {"kind": "timer", "text": "00:15", "start_frame": 0, "end_frame": 60, "x": 0.8, "y": 0.05},
        ]
        span = CompilationSpan(
            index=1,
            shot_id="shot_with_overlays",
            start_frame=0,
            end_frame=60,
            asset_id="asset_1",
            overlays=tuple(overlays),
        )
        target = CompilationTarget(width=2560, height=1440, fps=30)
        encoder = {"video_codec": "h264_qsv"}

        result = build_span_filter_graph(
            span=span,
            target=target,
            encoder_config=encoder,
            work_dir=tmp_path,
        )

        assert result.is_file_backed is True
        assert result.args == ["-/filter_complex", "graph_00001.txt", "-map", "[vout]"]
        assert len(result.ass_files) >= 1
        for ass_file in result.ass_files:
            assert ass_file.exists()
            assert "Test Headline" in ass_file.read_text(encoding="utf-8")

        # QSV requires nv12
        assert "format=nv12,setparams=range=tv" in result.filter_string

    def test_length_threshold_triggers_file_backed_script(self, tmp_path: Path) -> None:
        span = CompilationSpan(
            index=0,
            shot_id="shot_threshold",
            start_frame=0,
            end_frame=90,
            asset_id="asset_1",
            camera_motion="push",
            zoom=1.05,
        )
        target = CompilationTarget(width=1920, height=1080, fps=30)
        encoder = {"video_codec": "libx264"}

        # Setting threshold low (e.g. 50 characters) forces file-backed mode
        result = build_span_filter_graph(
            span=span,
            target=target,
            encoder_config=encoder,
            work_dir=tmp_path,
            cmd_length_threshold=50,
        )
        assert result.is_file_backed is True
        assert result.args[0] == "-/filter_complex"


# ---------------------------------------------------------------------------
# 5. End-to-End Single-Pass Compilation with FakeMediaRunner
# ---------------------------------------------------------------------------

class TestVideoCompilerSinglePassComposition:
    """Verifies end-to-end clip rendering with overlays and camera motions via FakeMediaRunner."""

    def _setup_request(self, tmp_path: Path) -> tuple[CompilationRequest, Path, Path]:
        img1 = tmp_path / "img1.png"
        img1.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
        img2 = tmp_path / "img2.png"
        img2.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
        audio = tmp_path / "audio.wav"
        audio.write_bytes(b"RIFF" + b"\x00" * 36)
        out = tmp_path / "master.mp4"

        spans = [
            CompilationSpan(
                index=0,
                shot_id="shot_000",
                start_frame=0,
                end_frame=60,
                asset_id="img1",
                camera_motion="push",
                zoom=1.06,
                overlays=(
                    {
                        "kind": "data_grid",
                        "preset": "schulte_6x6",
                        "start_frame": 0,
                        "end_frame": 60,
                        "x": 0.2,
                        "y": 0.2,
                        "width": 0.6,
                        "height": 0.6,
                    },
                ),
            ),
            CompilationSpan(
                index=1,
                shot_id="shot_001",
                start_frame=60,
                end_frame=120,
                asset_id="img2",
                camera_motion="pan_left",
                zoom=1.08,
                overlays=(
                    {
                        "kind": "timer",
                        "text": "00:30",
                        "start_frame": 0,
                        "end_frame": 60,
                        "x": 0.8,
                        "y": 0.05,
                        "width": 0.15,
                        "height": 0.1,
                    },
                ),
            ),
        ]

        work = tmp_path / "work"
        work.mkdir(parents=True, exist_ok=True)
        req = CompilationRequest(
            spans=tuple(spans),
            audio_path=audio,
            asset_paths={"img1": img1, "img2": img2},
            output_path=out,
            profile=CompilationProfile.BROADCAST_MASTER,
            work_dir=work,
        )
        return req, img1, out

    def test_end_to_end_single_pass_burn_in(self, tmp_path: Path) -> None:
        req, _, out = self._setup_request(tmp_path)
        fake_runner = FakeMediaRunner(
            available_encoders={"h264_qsv", "libx264"},
            default_total_frames=120,
            default_duration=4.0,
            default_width=2560,
            default_height=1440,
            default_fps=30.0,
            default_pix_fmt="yuv420p",
        )
        fake_runner.register_probe(
            out,
            MediaProbeResult(
                duration=4.0,
                total_frames=120,
                width=2560,
                height=1440,
                fps=30.0,
                pix_fmt="yuv420p",
                color_range="tv",
                has_audio=True,
            ),
        )

        compiler = VideoCompiler(runner=fake_runner)
        result = compiler.compile(req)

        assert result.verified is True
        assert result.width == 2560
        assert result.height == 1440
        assert result.total_frames == 120

        # Inspect FFmpeg commands executed
        clip_cmds = [cmd for cmd in fake_runner.commands_run if "clip_" in " ".join(cmd)]
        assert len(clip_cmds) == 2

        for cmd in clip_cmds:
            cmd_str = " ".join(cmd)
            # Must use file-backed -/filter_complex contract due to overlays
            assert "-/filter_complex" in cmd
            assert "-map" in cmd
            assert "[vout]" in cmd
            assert "-bsf:v" in cmd
            assert "h264_metadata=video_full_range_flag=0" in cmd_str

    def test_midstream_hardware_fallback_regenerates_compliant_filtergraph(
        self, tmp_path: Path
    ) -> None:
        req, _, out = self._setup_request(tmp_path)
        # Simulate QSV crashing during clip encode, forcing failover to libx264
        fake_runner = FakeMediaRunner(
            available_encoders={"h264_qsv", "libx264"},
            error_on_encoder={"h264_qsv"},
            default_total_frames=120,
            default_duration=4.0,
            default_width=2560,
            default_height=1440,
            default_fps=30.0,
            default_pix_fmt="yuv420p",
        )
        fake_runner.register_probe(
            out,
            MediaProbeResult(
                duration=4.0,
                total_frames=120,
                width=2560,
                height=1440,
                fps=30.0,
                pix_fmt="yuv420p",
                color_range="tv",
                has_audio=True,
            ),
        )

        compiler = VideoCompiler(runner=fake_runner)
        result = compiler.compile(req)

        assert result.verified is True
        assert result.fallback_occurred is True
        assert result.fallback_from == "h264_qsv"
        assert result.encoder_used == "libx264"

        # Verify that fallback retry switched from nv12 to yuv420p
        qsv_cmds = [cmd for cmd in fake_runner.commands_run if "h264_qsv" in cmd]
        assert qsv_cmds
        for cmd in qsv_cmds:
            if "clip_" in " ".join(cmd):
                graph_arg_idx = cmd.index("-/filter_complex") + 1
                graph_file = Path(cmd[-1]).parent / Path(cmd[graph_arg_idx])
                assert graph_file.is_file()
                content = graph_file.read_text(encoding="utf-8")
                assert "format=nv12" in content

        libx264_cmds = [cmd for cmd in fake_runner.commands_run if "libx264" in cmd]
        assert len(libx264_cmds) >= 2
        for cmd in libx264_cmds:
            if "clip_" in " ".join(cmd):
                # Verify that the backing graph text was regenerated with format=yuv420p
                graph_arg_idx = cmd.index("-/filter_complex") + 1
                graph_file = Path(cmd[-1]).parent / Path(cmd[graph_arg_idx])
                assert graph_file.is_file()
                content = graph_file.read_text(encoding="utf-8")
                assert "format=yuv420p" in content
                assert "format=nv12" not in content

    def test_external_ass_uses_episode_timestamps_and_short_scratch(
        self, tmp_path: Path
    ) -> None:
        span = CompilationSpan(
            index=1,
            shot_id="shot_second",
            start_frame=30,
            end_frame=60,
            asset_id="asset_1",
            camera_motion="hold",
        )
        target = CompilationTarget(width=320, height=180, fps=30)
        source_ass = tmp_path / "source.ass"
        ass_bytes = (
            b"[Script Info]\nPlayResX: 320\nPlayResY: 180\n"
            b"[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour\n"
            b"Style: Default,Arial,20,&H00FFFFFF\n"
            b"[Events]\nFormat: Layer, Start, End, Style, Text\n"
            b"Dialogue: 0,0:00:00.600,0:00:01.400,Default,Across cut\n"
        )
        source_ass.write_bytes(ass_bytes)
        scratch_dir = tmp_path / "scratch"
        scratch_dir.mkdir()

        result = build_span_filter_graph(
            span=span,
            target=target,
            encoder_config={"video_codec": "libx264"},
            work_dir=scratch_dir,
            external_subtitles_path=source_ass,
        )

        copied_ass = scratch_dir / "external_subtitles_00001.ass"
        assert copied_ass.read_bytes() == ass_bytes
        assert result.is_file_backed
        assert result.filter_string.index("setpts=PTS+1.000000000/TB") < result.filter_string.index(
            "ass=external_subtitles_00001.ass"
        )
        assert result.filter_string.index("ass=external_subtitles_00001.ass") < result.filter_string.index(
            "setpts=PTS-1.000000000/TB"
        )
        assert copied_ass in result.ass_files
