from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from youtube_automation.production import ledger
from youtube_automation.video.engine import VideoCompiler
from youtube_automation.video.runner import FakeMediaRunner, MediaExecutionError, MediaProbeResult
from youtube_automation.video.schema import (
    CompilationError,
    CompilationProfile,
    CompilationRequest,
    CompilationSpan,
    CompilationTarget,
)


def request(tmp_path: Path) -> CompilationRequest:
    audio = tmp_path / "audio.wav"
    image = tmp_path / "image.png"
    audio.write_bytes(b"canonical audio")
    image.write_bytes(b"source image")
    return CompilationRequest(
        spans=(CompilationSpan(0, "shot", 0, 30, "image"),),
        audio_path=audio,
        asset_paths={"image": image},
        output_path=tmp_path / "accepted.mp4",
        work_dir=tmp_path / "work",
        target=CompilationTarget(128, 72),
        encoder_override="libx264",
    )


class ProbeRunner(FakeMediaRunner):
    def __init__(self) -> None:
        super().__init__(available_encoders={"libx264"}, default_total_frames=30, default_duration=1.0)
        self.audio_duration = 1.0
        self.result_probe = MediaProbeResult(
            duration=1.0, total_frames=30, width=128, height=72, fps=30,
            pix_fmt="yuv420p", color_range="tv", has_audio=True,
        )

    def probe(self, path: Path | str, *, require_audio: bool = False, timeout: float = 60.0) -> MediaProbeResult:
        if Path(path).suffix == ".wav":
            return MediaProbeResult(
                duration=self.audio_duration, total_frames=0, width=0, height=0,
                fps=0, pix_fmt="", color_range="", has_audio=True,
            )
        return self.result_probe


def test_rejected_candidate_preserves_existing_output(tmp_path: Path) -> None:
    req = request(tmp_path)
    req.output_path.write_bytes(b"previous accepted output")
    runner = ProbeRunner()
    runner.result_probe = replace(runner.result_probe, total_frames=999)
    with pytest.raises(CompilationError, match="Frame count mismatch"):
        VideoCompiler(runner).compile(req)
    assert req.output_path.read_bytes() == b"previous accepted output"
    assert list(tmp_path.glob("accepted.pending_*.mp4"))


def test_audio_mismatch_rejects_before_encoding(tmp_path: Path) -> None:
    req = request(tmp_path)
    req.output_path.write_bytes(b"previous accepted output")
    runner = ProbeRunner()
    runner.audio_duration = 2.0
    with pytest.raises(CompilationError, match="Audio duration mismatch"):
        VideoCompiler(runner).compile(req)
    assert req.output_path.read_bytes() == b"previous accepted output"
    assert runner.commands_run == []


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"width": 640}, "dimensions"),
        ({"pix_fmt": "yuv444p"}, "Pixel format"),
        ({"duration": float("nan")}, "duration"),
        ({"has_audio": False}, "audio"),
        ({"fps": float("nan")}, "Frame rate"),
        ({"audio_duration": 0.5}, "Audio duration"),
        ({"video_duration": 0.5}, "Video duration"),
    ],
)
def test_candidate_metadata_must_match_requested_target(
    tmp_path: Path, changes: dict[str, Any], message: str,
) -> None:
    req = request(tmp_path)
    req.output_path.write_bytes(b"previous accepted output")
    runner = ProbeRunner()
    runner.result_probe = replace(runner.result_probe, **changes)
    with pytest.raises(CompilationError, match=message):
        VideoCompiler(runner).compile(req)
    assert req.output_path.read_bytes() == b"previous accepted output"


class LeaseObservingRunner(ProbeRunner):
    def observe_lease(self) -> None:
        row = ledger.Ledger(ledger.resource_database()).get("encoder")
        assert row is not None and row["state"] == "RUNNING", "encoder lease must cover media access"

    def probe(self, path: Path | str, *, require_audio: bool = False, timeout: float = 60.0) -> MediaProbeResult:
        self.observe_lease()
        return super().probe(path, require_audio=require_audio, timeout=timeout)

    def run_ffmpeg(self, args: list[str], **kwargs: Any) -> tuple[str, str]:
        self.observe_lease()
        return super().run_ffmpeg(args, **kwargs)


def test_public_compiler_owns_one_lease_through_verification(tmp_path: Path) -> None:
    req = request(tmp_path)
    VideoCompiler(LeaseObservingRunner()).compile(req)
    row = ledger.Ledger(ledger.resource_database()).get("encoder")
    assert row is not None and row["state"] == "SUCCEEDED"
    assert row["attempts"] == 1


def test_public_compiler_reuses_existing_owned_encoder_lease(tmp_path: Path) -> None:
    req = request(tmp_path)
    db = ledger.resource_database()
    with ledger.leased_resource(db, "encoder"):
        before = ledger.Ledger(db).get("encoder")
        VideoCompiler(LeaseObservingRunner()).compile(req)
        after = ledger.Ledger(db).get("encoder")
        assert before is not None and after is not None
        assert (after["owner"], after["fence"], after["attempts"]) == (before["owner"], before["fence"], 1)
    assert ledger.Ledger(db).get("encoder")["state"] == "SUCCEEDED"


@pytest.mark.parametrize("exact_work_dir", [False, True])
def test_hardware_fallback_preserves_complete_generation_and_uses_only_cpu_clips(
    tmp_path: Path, exact_work_dir: bool,
) -> None:
    class SecondClipFailure(ProbeRunner):
        def __init__(self) -> None:
            super().__init__()
            self.available_encoders = {"h264_qsv", "libx264"}
            self.audio_duration = 2.0
            self.result_probe = replace(self.result_probe, duration=2.0, total_frames=60)
            self.hardware_dir: Path | None = None
            self.hardware_snapshot: dict[str, bytes] = {}
            self.cpu_clips = 0

        def run_ffmpeg(self, args: list[str], *, cwd: Path | str | None = None, timeout: float | None = None) -> tuple[str, str]:
            if "h264_qsv" in args and Path(args[-1]).name == "clip_00001.pending.mp4":
                assert cwd is not None
                self.hardware_dir = Path(cwd)
                self.hardware_snapshot = {p.name: p.read_bytes() for p in self.hardware_dir.iterdir()}
                raise MediaExecutionError("injected device loss", ["ffmpeg", *args], 1, "device lost")
            if "libx264" in args and Path(args[-1]).name.startswith("clip_"):
                self.cpu_clips += 1
            return super().run_ffmpeg(args, cwd=cwd, timeout=timeout)

    req = request(tmp_path)
    req = replace(
        req,
        spans=(CompilationSpan(0, "first", 0, 30, "image"), CompilationSpan(1, "second", 30, 60, "image")),
        encoder_override="h264_qsv",
        extra_config={"EXACT_WORK_DIR": exact_work_dir, "GENERATION_OVERRIDE": "production-generation"},
    )
    runner = SecondClipFailure()
    result = VideoCompiler(runner).compile(req)
    assert result.verified and result.fallback_occurred
    assert runner.hardware_dir is not None
    for name, content in runner.hardware_snapshot.items():
        assert (runner.hardware_dir / name).read_bytes() == content
    assert runner.cpu_clips == 2
    assert all(
        clip["execution"]["encoder_recipe"]["video_codec"] == "libx264"
        for clip in result.clip_executions
    )


def test_qsv_surface_format_does_not_waive_decoded_format_check(tmp_path: Path) -> None:
    req = replace(request(tmp_path), target=CompilationTarget(128, 72, pixel_format="nv12"))
    runner = ProbeRunner()
    assert VideoCompiler(runner).compile(req).verified
    runner.result_probe = replace(runner.result_probe, pix_fmt="nv12")
    with pytest.raises(CompilationError, match="Pixel format"):
        VideoCompiler(runner).compile(req)


@pytest.mark.parametrize(
    "field, value",
    [("owner", "another-worker"), ("fence", 999), ("expires", 0), ("state", "CANCELLED")],
)
def test_compiler_rejects_stale_enclosing_claim_before_media_work(
    tmp_path: Path, field: str, value: Any,
) -> None:
    req = request(tmp_path)
    req.output_path.write_bytes(b"previous accepted output")
    runner = ProbeRunner()
    db = ledger.resource_database()
    with pytest.raises(RuntimeError, match="Lost production lease"):
        with ledger.leased_resource(db, "stage"):
            with ledger.leased_resource(db, "encoder"):
                with ledger.Ledger(db).connection() as connection:
                    connection.execute(f"UPDATE jobs SET {field}=? WHERE key='stage'", (value,))
                VideoCompiler(runner).compile(req)
    assert req.output_path.read_bytes() == b"previous accepted output"
    assert runner.commands_run == []


def test_owned_resource_rejects_a_different_ledger_domain(tmp_path: Path) -> None:
    db = ledger.resource_database()
    other = tmp_path / "other-ledger.sqlite3"
    with ledger.leased_resource(db, "encoder"):
        with pytest.raises(RuntimeError, match="share one ledger"):
            with ledger.owned_resource(other, "encoder"):
                pytest.fail("another ledger cannot establish nested ownership")
        assert not other.exists()


@pytest.mark.parametrize("settings", [{"color_range": "pc"}, {"pixel_format": "yuv444p"}])
def test_unsupported_target_is_rejected_before_encoding(
    tmp_path: Path, settings: dict[str, Any],
) -> None:
    req = replace(request(tmp_path), target=CompilationTarget(128, 72, **settings))
    runner = ProbeRunner()
    runner.result_probe = replace(runner.result_probe, **({"pix_fmt": "yuv444p"} if "pixel_format" in settings else {}))
    with pytest.raises(CompilationError, match="Unsupported target"):
        VideoCompiler(runner).compile(req)
    assert runner.commands_run == []


@pytest.mark.parametrize("bounds", [[(0, 30), (60, 90)], [(30, 60)]])
def test_timeline_gaps_are_rejected_before_media_work(
    tmp_path: Path, bounds: list[tuple[int, int]],
) -> None:
    req = request(tmp_path)
    req = replace(req, spans=tuple(CompilationSpan(i, str(i), start, end, "image") for i, (start, end) in enumerate(bounds)))
    runner = ProbeRunner()
    duration = sum(end - start for start, end in bounds) / 30
    runner.audio_duration = duration
    runner.result_probe = replace(runner.result_probe, total_frames=round(duration * 30), duration=duration)
    with pytest.raises(ValueError, match="contiguous"):
        VideoCompiler(runner).compile(req)
    assert runner.commands_run == []


@pytest.mark.parametrize("entrypoint", ["method", "function"])
def test_standalone_encoder_detection_is_lease_protected(tmp_path: Path, entrypoint: str) -> None:
    from youtube_automation.video.engine import detect_encoder

    runner = LeaseObservingRunner()
    if entrypoint == "method":
        selected = VideoCompiler(runner).detect_encoder({"OUTPUT_FPS": 30})
    else:
        selected = detect_encoder({"OUTPUT_FPS": 30}, runner=runner)
    assert selected["video_codec"] == "libx264"
    row = ledger.Ledger(ledger.resource_database()).get("encoder")
    assert row is not None and row["state"] == "SUCCEEDED" and row["attempts"] == 1


@pytest.mark.parametrize("input_kind", ["audio", "asset", "subtitles", "hardlink"])
def test_output_must_not_alias_any_compilation_input(tmp_path: Path, input_kind: str) -> None:
    req = request(tmp_path)
    if input_kind == "audio":
        req = replace(req, output_path=req.audio_path)
        protected = req.audio_path
    elif input_kind == "asset":
        protected = req.asset_paths["image"]
        req = replace(req, output_path=protected)
    elif input_kind == "subtitles":
        protected = tmp_path / "captions.ass"
        protected.write_bytes(b"accepted subtitle data")
        req = replace(req, subtitles_path=protected, output_path=protected)
    else:
        protected = req.audio_path
        req.output_path.hardlink_to(protected)
    before = protected.read_bytes()
    runner = ProbeRunner()
    with pytest.raises(ValueError, match="aliases"):
        VideoCompiler(runner).compile(req)
    assert protected.read_bytes() == before
    assert runner.commands_run == []


def test_2997_fps_does_not_satisfy_an_explicit_30fps_target(tmp_path: Path) -> None:
    req = request(tmp_path)
    req.output_path.write_bytes(b"previous accepted output")
    runner = ProbeRunner()
    runner.result_probe = replace(
        runner.result_probe,
        fps=29.97,
        duration=30 / 29.97,
        video_duration=30 / 29.97,
        audio_duration=1.0,
    )
    with pytest.raises(CompilationError, match="Frame rate mismatch"):
        VideoCompiler(runner).compile(req)
    assert req.output_path.read_bytes() == b"previous accepted output"


def production_fallback_fixture(tmp_path: Path) -> tuple[CompilationRequest, ProbeRunner]:
    hardware = {
        "video_codec": "h264_qsv", "encoder_name": "QSV",
        "hwaccel": "qsv", "encoder_args": ["-global_quality", "20"],
    }
    cpu = {
        "video_codec": "libx264", "encoder_name": "CPU",
        "hwaccel": "none", "encoder_args": ["-preset", "veryfast", "-crf", "17"],
    }

    def valid_execution(value: Any) -> bool:
        return isinstance(value, dict) and (
            (value.get("encoder_recipe") == hardware and value.get("fallback_from") is None)
            or (value.get("encoder_recipe") == cpu and value.get("fallback_from") == hardware)
        )

    req = replace(
        request(tmp_path), encoder_override="h264_qsv",
        extra_config={
            "EXACT_WORK_DIR": True, "GENERATION_OVERRIDE": "production-generation",
            "ENCODER_CONFIG": hardware, "CPU_FALLBACK_CONFIG": cpu,
            "FALLBACK_FROM_VALUE": hardware, "EXECUTION_VALIDATOR": valid_execution,
            "ASSEMBLY_CODEC": "libx264",
        },
    )
    runner = ProbeRunner()
    runner.available_encoders = {"h264_qsv", "libx264"}
    runner.error_on_encoder = {"h264_qsv"}
    return req, runner


def test_master_reuses_verified_preview_cpu_fallback_without_hardware_retry(tmp_path: Path) -> None:
    req, runner = production_fallback_fixture(tmp_path)
    preview = VideoCompiler(runner).compile(req)
    assert preview.fallback_occurred
    runner.commands_run.clear()
    master = VideoCompiler(runner).compile(
        replace(req, profile=CompilationProfile.BROADCAST_MASTER, output_path=tmp_path / "master.mp4")
    )
    assert master.verified and master.reused_clip_count == 1
    assert master.generation_hash == preview.generation_hash
    assert len(runner.commands_run) == 1
    assert "concat" in runner.commands_run[0]


@pytest.mark.parametrize("change", ["target", "cpu_encoder", "asset"])
def test_cpu_cache_never_reuses_a_different_physical_recipe(tmp_path: Path, change: str) -> None:
    req, runner = production_fallback_fixture(tmp_path)
    preview = VideoCompiler(runner).compile(req)
    next_request = replace(req, profile=CompilationProfile.BROADCAST_MASTER, output_path=tmp_path / "master.mp4")
    if change == "target":
        next_request = replace(next_request, target=CompilationTarget(256, 144))
        runner.result_probe = replace(runner.result_probe, width=256, height=144)
    elif change == "asset":
        req.asset_paths["image"].write_bytes(b"changed source pixels")
    else:
        config = dict(req.extra_config)
        hardware = config["ENCODER_CONFIG"]
        cpu = dict(config["CPU_FALLBACK_CONFIG"], encoder_args=["-preset", "veryfast", "-crf", "18"])
        config["CPU_FALLBACK_CONFIG"] = cpu
        config["EXECUTION_VALIDATOR"] = lambda value: isinstance(value, dict) and (
            (value.get("encoder_recipe") == hardware and value.get("fallback_from") is None)
            or (value.get("encoder_recipe") == cpu and value.get("fallback_from") == hardware)
        )
        next_request = replace(next_request, extra_config=config)
    runner.commands_run.clear()
    master = VideoCompiler(runner).compile(next_request)
    assert master.verified and master.reused_clip_count == 0
    assert master.generation_hash != preview.generation_hash
    assert any("-frames:v" in command for command in runner.commands_run)


def test_partial_preview_cpu_fallback_resumes_master_without_retrying_hardware(tmp_path: Path) -> None:
    class PartialCpuRunner(ProbeRunner):
        def __init__(self) -> None:
            super().__init__()
            self.available_encoders = {"h264_qsv", "libx264"}
            self.error_on_encoder = {"h264_qsv"}
            self.audio_duration = 2.0
            self.result_probe = replace(self.result_probe, total_frames=60, duration=2.0)
            self.interrupt_once = True

        def run_ffmpeg(self, args: list[str], **kwargs: Any) -> tuple[str, str]:
            if self.interrupt_once and "libx264" in args and Path(args[-1]).name == "clip_00001.pending.mp4":
                self.interrupt_once = False
                raise MediaExecutionError("interrupted CPU clip", ["ffmpeg", *args], 1, "interrupted CPU clip")
            return super().run_ffmpeg(args, **kwargs)

    req, _ = production_fallback_fixture(tmp_path)
    req = replace(req, spans=(CompilationSpan(0, "first", 0, 30, "image"), CompilationSpan(1, "second", 30, 60, "image")))
    runner = PartialCpuRunner()
    with pytest.raises(CompilationError, match="interrupted CPU clip"):
        VideoCompiler(runner).compile(req)
    runner.commands_run.clear()
    master = VideoCompiler(runner).compile(
        replace(req, profile=CompilationProfile.BROADCAST_MASTER, output_path=tmp_path / "master.mp4")
    )
    assert master.verified and master.reused_clip_count == 1
    assert len(runner.commands_run) == 2
    assert all("h264_qsv" not in command for command in runner.commands_run)
