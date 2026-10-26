from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

import youtube_automation.video as video
from youtube_automation.video.engine import VideoCompiler
from youtube_automation.video.runner import FakeMediaRunner, MediaProbeResult
from youtube_automation.video.schema import (
    CompilationError,
    CompilationRequest,
    CompilationSpan,
    CompilationTarget,
)


def request(tmp_path: Path) -> CompilationRequest:
    audio = tmp_path / "audio.wav"
    image = tmp_path / "image.png"
    audio.write_bytes(b"narration")
    image.write_bytes(b"source image")
    return CompilationRequest(
        spans=(CompilationSpan(0, "shot", 0, 30, "image"),),
        audio_path=audio, asset_paths={"image": image},
        output_path=tmp_path / "accepted.mp4", work_dir=tmp_path / "work",
        target=CompilationTarget(128, 72), encoder_override="libx264",
    )


class ReceiptRunner(FakeMediaRunner):
    def __init__(self) -> None:
        super().__init__(available_encoders={"libx264"}, default_total_frames=30, default_duration=1.0)
        self.output_probe = MediaProbeResult(
            duration=1.0, total_frames=30, width=128, height=72, fps=30,
            pix_fmt="yuv420p", color_range="tv", has_audio=True,
            audio_duration=1.0, video_duration=1.0,
        )

    def probe(self, path: Path | str, *, require_audio: bool = False, timeout: float = 60.0) -> MediaProbeResult:
        if Path(path).suffix == ".wav":
            return MediaProbeResult(duration=1.0, total_frames=0, width=0, height=0, fps=0,
                                    pix_fmt="", color_range="", has_audio=True, audio_duration=1.0)
        return self.output_probe


def compiled(tmp_path: Path) -> tuple[CompilationRequest, Any]:
    req = request(tmp_path)
    result = VideoCompiler(ReceiptRunner()).compile(req)
    return req, result


def test_success_publishes_hash_bound_final_receipt(tmp_path: Path) -> None:
    req, result = compiled(tmp_path)
    assert getattr(result, "receipt_path", None) is not None
    assert result.receipt_path == video.verification_receipt_path(req.output_path)
    payload = video.verify_compilation_receipt(req.output_path)
    assert payload["sha256"] == result.sha256
    assert payload["size_bytes"] == req.output_path.stat().st_size
    assert payload["total_frames"] == result.total_frames == 30
    assert payload["fps"] == 30 and payload["duration"] == 1.0
    assert payload["width"] == 128 and payload["height"] == 72
    assert payload["pixel_format"] == "yuv420p" and payload["color_range"] == "tv"
    assert payload["has_audio"] is True
    assert result.receipt_path.name == result.sha256 + ".json"


def test_missing_receipt_rejects_existing_artifact(tmp_path: Path) -> None:
    req, result = compiled(tmp_path)
    result.receipt_path.rename(tmp_path / "saved-receipt.json")
    with pytest.raises(CompilationError, match="receipt"):
        video.verify_compilation_receipt(req.output_path)


def test_changed_artifact_cannot_reuse_previous_receipt(tmp_path: Path) -> None:
    req, result = compiled(tmp_path)
    original_receipt = result.receipt_path.read_bytes()
    req.output_path.write_bytes(b"different artifact bytes")
    with pytest.raises(CompilationError, match="receipt"):
        video.verify_compilation_receipt(req.output_path)
    assert result.receipt_path.read_bytes() == original_receipt


@pytest.mark.parametrize("field,value", [
    ("schema_version", True), ("schema_version", 99), ("size_bytes", 0),
    ("sha256", "0" * 64), ("total_frames", True), ("total_frames", 0),
    ("fps", float("nan")), ("duration", float("inf")), ("duration", 20.0),
    ("width", 0), ("height", 72.5), ("pixel_format", "nv12"),
    ("color_range", "pc"), ("has_audio", False), ("audio_duration", None),
    ("unexpected_field", "reject"),
])
def test_invalid_receipt_fails_closed(tmp_path: Path, field: str, value: Any) -> None:
    req, result = compiled(tmp_path)
    payload = json.loads(result.receipt_path.read_text())
    payload[field] = value
    result.receipt_path.write_text(json.dumps(payload))
    with pytest.raises(CompilationError, match="receipt"):
        video.verify_compilation_receipt(req.output_path)


def test_duplicate_json_fields_fail_closed(tmp_path: Path) -> None:
    req, result = compiled(tmp_path)
    original = result.receipt_path.read_text()
    result.receipt_path.write_text('{"schema_version":1,' + original[1:])
    with pytest.raises(CompilationError, match="receipt"):
        video.verify_compilation_receipt(req.output_path)


def test_oversized_receipt_fails_closed(tmp_path: Path) -> None:
    req, result = compiled(tmp_path)
    result.receipt_path.write_text(" " * 65537)
    with pytest.raises(CompilationError, match="receipt"):
        video.verify_compilation_receipt(req.output_path)


def test_receipt_write_failure_preserves_previous_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    req, result = compiled(tmp_path)
    before = req.output_path.read_bytes()
    saved_receipt = result.receipt_path.read_bytes()
    # A new byte sequence requires a distinct immutable receipt.
    runner = ReceiptRunner()
    original_run = runner.run_ffmpeg
    def changed_output(args: list[str], **kwargs: Any) -> tuple[str, str]:
        reply = original_run(args, **kwargs)
        if ".pending_" in str(args[-1]):
            Path(args[-1]).write_bytes(b"new compiled candidate")
        return reply
    runner.run_ffmpeg = changed_output
    import youtube_automation.video.receipt as receipt
    def fail_write(*args: Any, **kwargs: Any) -> None:
        raise OSError("receipt disk full")
    monkeypatch.setattr(receipt, "atomic_write_json", fail_write)
    with pytest.raises(CompilationError, match="receipt"):
        VideoCompiler(runner).compile(req)
    assert req.output_path.read_bytes() == before
    assert result.receipt_path.read_bytes() == saved_receipt
    assert video.verify_compilation_receipt(req.output_path)["sha256"] == result.sha256
    assert list(tmp_path.glob("accepted.pending_*.mp4"))


def test_interrupted_publication_retains_prior_pair_and_can_resume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    req, result = compiled(tmp_path)
    before = req.output_path.read_bytes()
    saved_receipt = result.receipt_path.read_bytes()
    runner = ReceiptRunner()
    original_run = runner.run_ffmpeg
    def new_candidate(args: list[str], **kwargs: Any) -> tuple[str, str]:
        reply = original_run(args, **kwargs)
        if ".pending_" in str(args[-1]):
            Path(args[-1]).write_bytes(b"new recoverable candidate")
        return reply
    runner.run_ffmpeg = new_candidate
    original_replace = Path.replace
    def interrupt(source: Path, target: Path | str) -> Path:
        if ".pending_" in source.name and Path(target) == req.output_path:
            raise KeyboardInterrupt("simulated interruption before publication")
        return original_replace(source, target)
    with monkeypatch.context() as scoped:
        scoped.setattr(Path, "replace", interrupt)
        with pytest.raises(KeyboardInterrupt):
            VideoCompiler(runner).compile(req)
    assert req.output_path.read_bytes() == before
    assert result.receipt_path.read_bytes() == saved_receipt
    assert video.verify_compilation_receipt(req.output_path)["sha256"] == result.sha256
    assert len(list(result.receipt_path.parent.glob("*.json"))) == 2
    resumed = VideoCompiler(runner).compile(req)
    assert video.verify_compilation_receipt(req.output_path)["sha256"] == resumed.sha256
    assert resumed.sha256 != result.sha256
    assert resumed.receipt_path != result.receipt_path


def test_conflicting_existing_receipt_is_preserved_and_rejected(tmp_path: Path) -> None:
    req, result = compiled(tmp_path)
    before = req.output_path.read_bytes()
    payload = json.loads(result.receipt_path.read_text())
    payload["width"] = 640
    result.receipt_path.write_text(json.dumps(payload))
    conflict = result.receipt_path.read_bytes()
    with pytest.raises(CompilationError, match="receipt"):
        VideoCompiler(ReceiptRunner()).compile(req)
    assert req.output_path.read_bytes() == before
    assert result.receipt_path.read_bytes() == conflict


def test_equivalent_profiles_share_identical_artifact_receipt(tmp_path: Path) -> None:
    req, result = compiled(tmp_path)
    before = result.receipt_path.read_bytes()
    from youtube_automation.video.schema import CompilationProfile
    second = VideoCompiler(ReceiptRunner()).compile(replace(req, profile=CompilationProfile.BROADCAST_MASTER))
    assert second.sha256 == result.sha256
    assert second.receipt_path == result.receipt_path
    assert second.receipt_path.read_bytes() == before


def test_receipt_directory_collision_preserves_existing_video(tmp_path: Path) -> None:
    req, result = compiled(tmp_path)
    before = req.output_path.read_bytes()
    result.receipt_path.parent.rename(tmp_path / "saved-evidence")
    (tmp_path / ".compilation-receipts").write_bytes(b"unrelated file")
    with pytest.raises(CompilationError, match="receipt"):
        VideoCompiler(ReceiptRunner()).compile(req)
    assert req.output_path.read_bytes() == before
    assert (tmp_path / ".compilation-receipts").read_bytes() == b"unrelated file"


def test_receipt_directory_symlink_rejects_before_publication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    req = request(tmp_path)
    req.output_path.write_bytes(b"previous output")
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path.name == ".compilation-receipts" or original(path))
    with pytest.raises(CompilationError, match="receipt.*symlink"):
        VideoCompiler(ReceiptRunner()).compile(req)
    assert req.output_path.read_bytes() == b"previous output"


def test_video_mutation_during_receipt_read_rejects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    req, result = compiled(tmp_path)
    import youtube_automation.video.receipt as receipt
    original = receipt._read_receipt
    def mutate(path: Path, digest: str, size: int) -> dict[str, Any]:
        payload = original(path, digest, size)
        req.output_path.write_bytes(b"mutated during verification")
        return payload
    monkeypatch.setattr(receipt, "_read_receipt", mutate)
    with pytest.raises(CompilationError, match="receipt.*changed"):
        video.verify_compilation_receipt(req.output_path)
    assert result.receipt_path.exists()


def test_same_parent_artifact_rename_preserves_receipt_lookup(tmp_path: Path) -> None:
    req, result = compiled(tmp_path)
    renamed = tmp_path / ("preview-" + result.sha256 + ".mp4")
    req.output_path.rename(renamed)
    assert video.verification_receipt_path(renamed) == result.receipt_path
    assert video.verify_compilation_receipt(renamed)["sha256"] == result.sha256


def test_interruption_after_video_replace_leaves_verifiable_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    req = request(tmp_path)
    original = Path.replace
    def replace_then_interrupt(source: Path, target: Path | str) -> Path:
        result = original(source, target)
        if ".pending_" in source.name and Path(target) == req.output_path:
            raise KeyboardInterrupt("simulated interruption after publication")
        return result
    with monkeypatch.context() as scoped:
        scoped.setattr(Path, "replace", replace_then_interrupt)
        with pytest.raises(KeyboardInterrupt):
            VideoCompiler(ReceiptRunner()).compile(req)
    assert video.verify_compilation_receipt(req.output_path)["total_frames"] == 30


def test_redirected_receipt_directory_rejects_before_publication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    req = request(tmp_path)
    req.output_path.write_bytes(b"previous output")
    redirected = tmp_path / "outside-receipts"
    original = Path.resolve
    def junction(path: Path, strict: bool = False) -> Path:
        if path.name == ".compilation-receipts":
            return redirected
        return original(path, strict=strict)
    monkeypatch.setattr(Path, "resolve", junction)
    with pytest.raises(CompilationError, match="receipt.*junction"):
        VideoCompiler(ReceiptRunner()).compile(req)
    assert req.output_path.read_bytes() == b"previous output"
    assert not redirected.exists()




def test_pairwise_av_drift_rejects_before_replacing_prior_artifact(tmp_path: Path) -> None:
    req, previous = compiled(tmp_path)
    accepted = req.output_path.read_bytes()
    receipt_bytes = previous.receipt_path.read_bytes()
    runner = ReceiptRunner()
    runner.output_probe = replace(runner.output_probe, video_duration=1.03, audio_duration=0.97)

    with pytest.raises(CompilationError, match="drift"):
        VideoCompiler(runner).compile(req)

    assert req.output_path.read_bytes() == accepted
    assert previous.receipt_path.read_bytes() == receipt_bytes
    assert video.verify_compilation_receipt(req.output_path)["sha256"] == previous.sha256
    assert list(tmp_path.glob("accepted.pending_*.mp4"))


def test_prior_receipt_with_pairwise_av_drift_fails_closed(tmp_path: Path) -> None:
    req, previous = compiled(tmp_path)
    accepted = req.output_path.read_bytes()
    payload = json.loads(previous.receipt_path.read_text(encoding="utf-8"))
    payload.update(video_duration=1.03, audio_duration=0.97)
    previous.receipt_path.write_text(json.dumps(payload), encoding="utf-8")
    contradictory_receipt = previous.receipt_path.read_bytes()

    with pytest.raises(CompilationError, match="drift"):
        video.verify_compilation_receipt(req.output_path)

    assert req.output_path.read_bytes() == accepted
    assert previous.receipt_path.read_bytes() == contradictory_receipt
