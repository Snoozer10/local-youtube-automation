"""Unit tests for content-addressed clip journal and restart-resumption.

Conforms to ADR 0002 and ADR 0006.
Verifies deterministic generation fingerprinting, atomic persistence,
corruption detection, and zero-redundant-re-encode resumption.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from youtube_automation.video.encoder import EncoderConfig
from youtube_automation.video.engine import VideoCompiler
from youtube_automation.video.journal import (
    ClipJournalEntry,
    RenderJournal,
    compute_generation_fingerprint,
    get_file_sha256,
)
from youtube_automation.video.runner import FakeMediaRunner, MediaExecutionError, MediaProbeResult
from youtube_automation.video.schema import (
    CompilationError,
    CompilationProfile,
    CompilationRequest,
    CompilationSpan,
    CompilationTarget,
)


def _make_test_request(
    tmp_path: Path,
    num_spans: int = 3,
    frames_per_span: int = 30,
) -> tuple[CompilationRequest, CompilationTarget, EncoderConfig]:
    work_dir = tmp_path / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    audio_path = tmp_path / "narration.wav"
    audio_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00")

    asset_paths: dict[str, Path] = {}
    spans: list[CompilationSpan] = []
    current_frame = 0

    for i in range(num_spans):
        asset_id = f"asset_{i:02d}"
        img_path = tmp_path / f"img_{i:02d}.png"
        img_path.write_bytes(f"\x89PNG test image content {i}".encode())
        asset_paths[asset_id] = img_path

        end_frame = current_frame + frames_per_span
        spans.append(
            CompilationSpan(
                index=i,
                shot_id=f"shot_{i:02d}",
                start_frame=current_frame,
                end_frame=end_frame,
                asset_id=asset_id,
                zoom=1.05 + (i * 0.01),
                camera_motion="pan_right" if i % 2 == 0 else "zoom_in",
                metadata={"source_size": (1920, 1080)},
            )
        )
        current_frame = end_frame

    target = CompilationTarget(
        width=1920,
        height=1080,
        fps=30,
        pixel_format="yuv420p",
        color_range="tv",
    )

    encoder: EncoderConfig = {
        "video_codec": "libx264",
        "encoder_name": "libx264",
        "hwaccel": "none",
        "encoder_args": ["-preset", "fast", "-crf", "18"],
    }

    req = CompilationRequest(
        spans=tuple(spans),
        audio_path=audio_path,
        asset_paths=asset_paths,
        output_path=tmp_path / "output.mp4",
        profile=CompilationProfile.PREVIEW,
        target=target,
        work_dir=work_dir,
    )
    return req, target, encoder


def test_generation_fingerprint_deterministic_and_sensitive(tmp_path: Path) -> None:
    """Generation fingerprint must be deterministic and sensitive to all inputs."""
    req, target, encoder = _make_test_request(tmp_path)

    hash1 = compute_generation_fingerprint(req, target, encoder)
    hash2 = compute_generation_fingerprint(req, target, encoder)
    assert hash1 == hash2
    assert len(hash1) == 64

    # 1. Changing span frames must change hash
    modified_spans = list(req.spans)
    modified_spans[0] = CompilationSpan(
        index=0,
        shot_id="shot_00",
        start_frame=0,
        end_frame=40,  # was 30
        asset_id="asset_00",
    )
    req_mod = CompilationRequest(
        spans=tuple(modified_spans),
        audio_path=req.audio_path,
        asset_paths=req.asset_paths,
        output_path=req.output_path,
    )
    assert compute_generation_fingerprint(req_mod, target, encoder) != hash1

    # 2. Modifying asset content on disk must change hash
    req.asset_paths["asset_00"].write_bytes(b"\x89PNG altered bytes")
    hash_altered_asset = compute_generation_fingerprint(req, target, encoder)
    assert hash_altered_asset != hash1

    # 3. Modifying audio content must change hash
    req.audio_path.write_bytes(b"RIFF new audio bytes")
    hash_altered_audio = compute_generation_fingerprint(req, target, encoder)
    assert hash_altered_audio != hash_altered_asset

    # 4. Modifying target dimensions must change hash
    target_1440p = CompilationTarget(
        width=2560,
        height=1440,
        fps=30,
        pixel_format="yuv420p",
        color_range="tv",
    )
    assert compute_generation_fingerprint(req, target_1440p, encoder) != hash_altered_audio

    # 5. Modifying encoder settings must change hash
    qsv_encoder: EncoderConfig = {
        "video_codec": "h264_qsv",
        "encoder_name": "h264_qsv",
        "hwaccel": "qsv",
        "encoder_args": ["-preset", "veryfast"],
    }
    assert compute_generation_fingerprint(req, target, qsv_encoder) != hash_altered_audio


def test_journal_atomic_record_and_reload(tmp_path: Path) -> None:
    """RenderJournal must atomically record sidecars and recover state across reloads."""
    work_dir = tmp_path / "journal_test"
    work_dir.mkdir(parents=True, exist_ok=True)
    target = CompilationTarget(width=1920, height=1080, fps=30)
    generation = "test_gen_hash_12345"

    journal = RenderJournal(
        work_dir=work_dir,
        generation=generation,
        total_spans=2,
        profile="preview",
        target=target,
    )
    assert journal.completed_count == 0
    assert not journal.is_complete()

    # Create dummy clip 0
    clip_0 = work_dir / "clip_00000.mp4"
    clip_0.write_bytes(b"\x00" * 2048)
    clip_0_sha = get_file_sha256(clip_0)

    journal.record_clip(
        index=0,
        shot_id="shot_00",
        asset_id="asset_00",
        asset_sha256="asset_sha_0",
        duration_frames=30,
        clip_path=clip_0,
        clip_sha256=clip_0_sha,
        encoder="libx264",
        fps=30,
    )

    assert journal.completed_count == 1
    assert not journal.is_complete()

    # Verify sidecar and journal files exist on disk
    sidecar_0 = work_dir / "clip_00000.json"
    assert sidecar_0.is_file()
    sidecar_text = sidecar_0.read_text(encoding="utf-8")
    assert '  "version": 1' in sidecar_text  # Verify indent=2 standard
    sidecar_data = json.loads(sidecar_text)
    assert sidecar_data["generation"] == generation
    assert sidecar_data["clip_sha256"] == clip_0_sha
    assert sidecar_data["verified"] is True

    journal_file = work_dir / "_render_journal.json"
    assert journal_file.is_file()
    journal_text = journal_file.read_text(encoding="utf-8")
    assert '  "version": 1' in journal_text  # Verify indent=2 standard
    journal_data = json.loads(journal_text)
    assert journal_data["generation"] == generation
    assert journal_data["completed_clips"] == 1
    assert "0" in journal_data["clips"]

    # Verify ClipJournalEntry.from_dict deserialization helper
    entry_from_dict = ClipJournalEntry.from_dict(sidecar_data)
    assert entry_from_dict.index == 0
    assert entry_from_dict.encoder == "libx264"
    assert entry_from_dict.clip_sha256 == clip_0_sha

    # Reload fresh journal instance from disk
    reloaded = RenderJournal(
        work_dir=work_dir,
        generation=generation,
        total_spans=2,
        profile="preview",
        target=target,
    )
    assert reloaded.completed_count == 1
    entry = reloaded.get_entry(0)
    assert entry is not None
    assert entry.clip_sha256 == clip_0_sha

    # Test is_clip_valid
    assert reloaded.is_clip_valid(0, clip_0, "asset_sha_0", 30)
    # Different expected frames -> invalid
    assert not reloaded.is_clip_valid(0, clip_0, "asset_sha_0", 45)
    # Different asset sha -> invalid
    assert not reloaded.is_clip_valid(0, clip_0, "different_asset_sha", 30)

    # Test drifted generation invalidation
    drifted_journal = RenderJournal(
        work_dir=work_dir,
        generation="drifted_gen_99999",
        total_spans=2,
        profile="preview",
        target=target,
    )
    assert drifted_journal.completed_count == 0


def test_is_clip_valid_detects_file_corruption(tmp_path: Path) -> None:
    """RenderJournal must detect and invalidate corrupted on-disk artifacts."""
    work_dir = tmp_path / "corruption_test"
    work_dir.mkdir(parents=True, exist_ok=True)
    target = CompilationTarget(width=1920, height=1080, fps=30)
    generation = "gen_corrupt_test"

    journal = RenderJournal(
        work_dir=work_dir,
        generation=generation,
        total_spans=1,
        profile="preview",
        target=target,
    )

    clip = work_dir / "clip_00000.mp4"
    clip.write_bytes(b"initial valid video bytes")
    clip_sha = get_file_sha256(clip)

    journal.record_clip(
        index=0,
        shot_id="shot_00",
        asset_id="asset_00",
        asset_sha256="asset_sha",
        duration_frames=30,
        clip_path=clip,
        clip_sha256=clip_sha,
        encoder="libx264",
    )
    assert journal.is_clip_valid(0, clip, "asset_sha", 30)

    # Corrupt clip on disk
    clip.write_bytes(b"corrupted bytes!")
    # Must detect corruption and invalidate
    assert not journal.is_clip_valid(0, clip, "asset_sha", 30)
    assert journal.completed_count == 0


def test_compiler_restart_resumption_skips_already_verified_clips(tmp_path: Path) -> None:
    """Interrupted compilation resumes from first incomplete clip, reusing verified clips."""
    req, target, _ = _make_test_request(tmp_path, num_spans=3, frames_per_span=30)
    total_expected_frames = 90

    fake_runner = FakeMediaRunner(
            available_encoders=["libx264"],
            default_total_frames=90,
            default_duration=3.0,
            default_width=1920,
            default_height=1080,
            default_fps=30.0,
            default_pix_fmt="yuv420p",
        )
    # Register probe for final concatenated video
    fake_runner.register_probe(
        req.output_path,
        MediaProbeResult(
            duration=3.0,
            total_frames=total_expected_frames,
            width=1920,
            height=1080,
            fps=30.0,
            pix_fmt="yuv420p",
            color_range="tv",
            has_audio=True,
        ),
    )

    class InterruptedMediaRunner(FakeMediaRunner):
        def __init__(self, **kwargs: object) -> None:
            super().__init__(**kwargs)  # type: ignore[arg-type]
            self.clip_calls = 0
            self.should_fail = True

        def run_ffmpeg(
            self,
            args: list[str],
            *,
            cwd: Path | str | None = None,
            timeout: float | None = None,
        ) -> tuple[str, str]:
            if self.should_fail and "-frames:v" in args:
                self.clip_calls += 1
                if self.clip_calls == 3:
                    raise MediaExecutionError(
                        "Simulated midstream crash on clip 2",
                        cmd=args,
                        returncode=1,
                    )
            return super().run_ffmpeg(args, cwd=cwd, timeout=timeout)

    interrupted_runner = InterruptedMediaRunner(
        available_encoders=["libx264"],
        default_total_frames=90,
        default_duration=3.0,
        default_width=1920,
        default_height=1080,
        default_fps=30.0,
        default_pix_fmt="yuv420p",
    )
    interrupted_runner.register_probe(
        req.output_path,
        MediaProbeResult(
            duration=3.0,
            total_frames=total_expected_frames,
            width=1920,
            height=1080,
            fps=30.0,
            pix_fmt="yuv420p",
            color_range="tv",
            has_audio=True,
        ),
    )

    compiler = VideoCompiler(runner=interrupted_runner)

    # First compile run: should fail on clip 2
    with pytest.raises(CompilationError) as exc_info:
        compiler.compile(req)
    assert exc_info.value.clip_index == 2

    # Verify that clips 0 and 1 are recorded in the journal
    assert req.work_dir is not None
    journal_files = list(req.work_dir.rglob("_render_journal.json"))
    assert len(journal_files) == 1
    work_dir = journal_files[0].parent
    assert (work_dir / "_render_journal.json").is_file()
    assert (work_dir / "clip_00000.mp4").is_file()
    assert (work_dir / "clip_00001.mp4").is_file()
    assert not (work_dir / "clip_00002.mp4").exists()

    # Disable failure for restart
    interrupted_runner.should_fail = False
    interrupted_runner.commands_run.clear()

    # Restart compilation: should resume directly from clip 2!
    result = compiler.compile(req)

    assert result.verified is True
    assert result.clip_count == 3
    assert result.reused_clip_count == 2  # Clips 0 and 1 were reused!

    # Check commands executed during restart:
    # Exactly 1 clip encoding command (clip 2) + 1 concat command!
    clip_encode_cmds = [
        cmd for cmd in interrupted_runner.commands_run if "-frames:v" in cmd
    ]
    concat_cmds = [
        cmd for cmd in interrupted_runner.commands_run if "concat" in cmd
    ]

    assert len(clip_encode_cmds) == 1, (
        f"Expected exactly 1 clip encode command on resumption, got {len(clip_encode_cmds)}"
    )
    assert len(concat_cmds) == 1, "Expected 1 concat assembly command"
    # Verify clip 2 was the one compiled
    assert any("clip_00002" in " ".join(cmd) for cmd in clip_encode_cmds)


def test_compiler_full_rerun_zero_re_encodes(tmp_path: Path) -> None:
    """When all clips are completed, re-running compilation executes zero clip re-encodes."""
    req, target, _ = _make_test_request(tmp_path, num_spans=3, frames_per_span=30)
    fake_runner = FakeMediaRunner(
            available_encoders=["libx264"],
            default_total_frames=90,
            default_duration=3.0,
            default_width=1920,
            default_height=1080,
            default_fps=30.0,
            default_pix_fmt="yuv420p",
        )
    fake_runner.register_probe(
        req.output_path,
        MediaProbeResult(
            duration=3.0,
            total_frames=90,
            width=1920,
            height=1080,
            fps=30.0,
            pix_fmt="yuv420p",
            color_range="tv",
            has_audio=True,
        ),
    )

    compiler = VideoCompiler(runner=fake_runner)

    # Initial full compilation
    result1 = compiler.compile(req)
    assert result1.clip_count == 3
    assert result1.reused_clip_count == 0

    # Second compilation run on same request
    fake_runner.commands_run.clear()
    result2 = compiler.compile(req)

    assert result2.clip_count == 3
    assert result2.reused_clip_count == 3  # All 3 clips reused!

    # Zero clip ffmpeg commands executed
    clip_encode_cmds = [
        cmd for cmd in fake_runner.commands_run if "-frames:v" in cmd
    ]
    assert len(clip_encode_cmds) == 0


def test_compiler_corrupted_clip_re_encoded(tmp_path: Path) -> None:
    """Corrupting a single clip on disk causes only that clip to be re-encoded."""
    req, target, _ = _make_test_request(tmp_path, num_spans=3, frames_per_span=30)
    fake_runner = FakeMediaRunner(
            available_encoders=["libx264"],
            default_total_frames=90,
            default_duration=3.0,
            default_width=1920,
            default_height=1080,
            default_fps=30.0,
            default_pix_fmt="yuv420p",
        )
    fake_runner.register_probe(
        req.output_path,
        MediaProbeResult(
            duration=3.0,
            total_frames=90,
            width=1920,
            height=1080,
            fps=30.0,
            pix_fmt="yuv420p",
            color_range="tv",
            has_audio=True,
        ),
    )

    compiler = VideoCompiler(runner=fake_runner)
    result1 = compiler.compile(req)

    # Corrupt clip 1
    assert req.work_dir is not None
    work_dir = req.work_dir / result1.generation_hash
    clip_1 = work_dir / "clip_00001.mp4"
    assert clip_1.is_file()
    clip_1.write_bytes(b"corrupted video content!")

    fake_runner.commands_run.clear()
    result = compiler.compile(req)

    assert result.clip_count == 3
    assert result.reused_clip_count == 2  # Clips 0 and 2 were reused!

    clip_encode_cmds = [
        cmd for cmd in fake_runner.commands_run if "-frames:v" in cmd
    ]
    assert len(clip_encode_cmds) == 1
    assert any("clip_00001" in " ".join(cmd) for cmd in clip_encode_cmds)


def test_subtitle_content_invalidates_fingerprint_and_missing_fails_closed(
    tmp_path: Path,
) -> None:
    request, target, encoder = _make_test_request(tmp_path)
    subtitles = tmp_path / "dynamic_subtitles.ass"
    subtitles.write_bytes(
        b"[Events]\nDialogue: 0,0:00:00.000,0:00:01.000,Default,First\n"
    )
    request = replace(request, subtitles_path=subtitles)

    original_fingerprint = compute_generation_fingerprint(request, target, encoder)
    subtitles.write_bytes(
        b"[Events]\nDialogue: 0,0:00:00.000,0:00:01.000,Default,Edited\n"
    )
    edited_fingerprint = compute_generation_fingerprint(request, target, encoder)

    assert original_fingerprint != edited_fingerprint
    subtitles.unlink()
    with pytest.raises(FileNotFoundError, match="External subtitles not found"):
        compute_generation_fingerprint(request, target, encoder)
