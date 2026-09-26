"""Source narration must remain bound to the selected script and WAV bytes."""

import json
import shutil
import wave
from contextlib import contextmanager

import pytest

from youtube_automation.production import source_narration
from youtube_automation.production.briefs import ensure_brief
from youtube_automation.production.contracts import Channel
from youtube_automation.production.source_narration import (
    import_source_narration,
    verify_source_narration,
)
from youtube_automation.production.writing import verify_written_episode, write_episode


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg unavailable"
)
def test_source_narration_import_is_exact_resumable_and_tamper_evident(tmp_path, monkeypatch):
    channel = Channel(
        channel_id="pilot",
        name="Pilot",
        audience="adults",
        language="English",
        dialect="English",
        voice=None,
        tone="clear",
        style="illustration",
        allowed_treatments=["subject_scene"],
    )
    raw = "The narrator says exactly these words.\n"
    (tmp_path / "raw_transcript.txt").write_text(raw, encoding="utf-8")
    ensure_brief(
        tmp_path,
        channel,
        lambda _: json.dumps(
            {
                "topics": ["narration"],
                "claim_basis": "factual",
                "form": "narrative",
                "proposition": "Exact speech",
                "narrative_strategy": "Follow the narrator",
                "treatments": ["subject_scene"],
                "rationale": "Preserve source",
            }
        ),
    )
    source = tmp_path / "owner-source.wav"
    with wave.open(str(source), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(48000)
        wav.writeframes(b"\x00\x00" * 144000)

    original_guard = source_narration.publication_guard

    @contextmanager
    def competing_publication():
        (tmp_path / "full_episode_voice.wav").write_bytes(b"other worker")
        with original_guard():
            yield

    monkeypatch.setattr(source_narration, "publication_guard", competing_publication)
    with pytest.raises(ValueError, match="appeared during import"):
        import_source_narration(tmp_path, source, start_seconds=0.5, end_seconds=2.5)
    assert (tmp_path / "full_episode_voice.wav").read_bytes() == b"other worker"
    assert not (tmp_path / "source_audio_receipt.json").exists()
    (tmp_path / "full_episode_voice.wav").unlink()
    monkeypatch.setattr(source_narration, "publication_guard", original_guard)

    receipt_writes = []
    original_write_json = source_narration.atomic_write_json

    def recording_write_json(path, value):
        receipt_writes.append(str(path))
        original_write_json(path, value)

    monkeypatch.setattr(source_narration, "atomic_write_json", recording_write_json)

    receipt = import_source_narration(tmp_path, source, start_seconds=0.5, end_seconds=2.5)
    assert receipt["mode"] == "source_preserved"
    assert receipt_writes[-1].endswith("source_audio_receipt.json")
    assert abs(receipt["audio_duration_seconds"] - 2) < 0.01
    assert (tmp_path / "refined_script.txt").read_text(encoding="utf-8") == raw
    assert verify_written_episode(tmp_path)
    assert import_source_narration(tmp_path, source, start_seconds=0.5, end_seconds=2.5) == receipt
    with pytest.raises(ValueError, match="cannot rewrite words"):
        write_episode(tmp_path, ensure_brief(tmp_path, channel, lambda _: pytest.fail()), lambda _: pytest.fail())
    with pytest.raises(ValueError, match="different source narration"):
        import_source_narration(tmp_path, source, start_seconds=0.2, end_seconds=2.5)

    audio = tmp_path / "full_episode_voice.wav"
    with audio.open("ab") as handle:
        handle.write(b"tamper")
    with pytest.raises(ValueError, match="receipt or WAV"):
        verify_source_narration(tmp_path)
    with pytest.raises(ValueError, match="receipt or WAV"):
        verify_written_episode(tmp_path)


def test_source_narration_requires_matching_caption_window(tmp_path):
    channel = Channel(
        channel_id="pilot", name="Pilot", audience="adults", language="English",
        dialect="English", voice=None, tone="clear", style="illustration",
        allowed_treatments=["subject_scene"],
    )
    (tmp_path / "raw_transcript.txt").write_text("one sentence\n", encoding="utf-8")
    ensure_brief(
        tmp_path, channel,
        lambda _: json.dumps({
            "topics": ["narration"], "claim_basis": "factual", "form": "narrative", "proposition": "Exact speech",
            "narrative_strategy": "Follow the narrator", "treatments": ["subject_scene"],
            "rationale": "Preserve source",
        }),
    )
    (tmp_path / "pilot_source.json").write_text(
        json.dumps({
            "channel_id": "pilot", "raw_transcript_sha256": "wrong",
            "start_seconds": 0, "end_seconds": 2,
        }), encoding="utf-8",
    )
    source = tmp_path / "source.wav"
    source.write_bytes(b"placeholder")
    with pytest.raises(ValueError, match="caption provenance"):
        import_source_narration(tmp_path, source, start_seconds=0, end_seconds=2)
    assert not (tmp_path / "full_episode_voice.wav").exists()


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg unavailable"
)
def test_source_narration_recovers_after_activation_crash_without_ffmpeg(tmp_path, monkeypatch):
    channel = Channel(
        channel_id="pilot", name="Pilot", audience="adults", language="English",
        dialect="English", voice=None, tone="clear", style="illustration",
        allowed_treatments=["subject_scene"],
    )
    raw = "The original narration remains unchanged.\n"
    (tmp_path / "raw_transcript.txt").write_text(raw, encoding="utf-8")
    ensure_brief(
        tmp_path, channel,
        lambda _: json.dumps({
            "topics": ["narration"], "claim_basis": "factual", "form": "narrative",
            "proposition": "Exact speech", "narrative_strategy": "Follow the narrator",
            "treatments": ["subject_scene"], "rationale": "Preserve source",
        }),
    )
    source = tmp_path / "source.wav"
    with wave.open(str(source), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(48000)
        wav.writeframes(b"\x00\x00" * 144000)

    real_write = source_narration.atomic_write_json
    failed = False

    def crash_before_source_receipt(path, value):
        nonlocal failed
        if str(path).endswith("source_audio_receipt.json") and not failed:
            failed = True
            raise OSError("injected source activation crash")
        real_write(path, value)

    monkeypatch.setattr(source_narration, "atomic_write_json", crash_before_source_receipt)
    with pytest.raises(OSError, match="activation crash"):
        import_source_narration(tmp_path, source, start_seconds=0.5, end_seconds=2.5)
    assert (tmp_path / "full_episode_voice.wav").is_file()
    assert not (tmp_path / "source_audio_receipt.json").exists()
    assert list((tmp_path / ".publication_journal" / "source_audio").glob("*.json"))

    monkeypatch.setattr(source_narration, "atomic_write_json", real_write)
    monkeypatch.setattr(
        source_narration.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("Recovery must not run FFmpeg or FFprobe"),
    )
    receipt = import_source_narration(tmp_path, source, start_seconds=0.5, end_seconds=2.5)
    assert receipt["mode"] == "source_preserved"
    assert verify_source_narration(tmp_path) == receipt
    assert verify_written_episode(tmp_path)
