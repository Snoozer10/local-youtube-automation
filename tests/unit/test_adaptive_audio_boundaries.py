"""Offline gates for adaptive Audacity output and exact physical chapter stitching."""

import io
import json
import threading
import wave

import pytest

from youtube_automation.audio import audacity_client, chapter_stitcher, tts_generator


def write_wav(path, *, frames=24000, rate=24000):
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b"\0\0" * frames)


def test_adaptive_audacity_manifest_uses_gapless_physical_offsets(tmp_path):
    polished = tmp_path / "polished_chapters"
    polished.mkdir()
    write_wav(polished / "Chapter_1.wav", frames=24000)
    write_wav(polished / "Chapter_2.wav", frames=48000)
    audio_manifest = tmp_path / "audio_manifest.json"
    audio_manifest.write_text(
        json.dumps(
            {
                "silence_padding_sec": 0.3,
                "segments": [
                    {"index": 1, "status": "COMPLETED", "duration": 7, "start_time": 0, "end_time": 7},
                    {"index": 2, "status": "COMPLETED", "duration": 8, "start_time": 7.3, "end_time": 15.3},
                ],
            }
        ),
        encoding="utf-8",
    )
    voice_manifest = tmp_path / "voice_generation_manifest.json"
    voice_manifest.write_text('{"raw_checkpoint": true}', encoding="utf-8")
    result = audacity_client.sync_polished_audio_manifest(str(tmp_path), strict=True)
    assert result["silence_padding_sec"] == 0.0
    assert [(s["start_time"], s["end_time"]) for s in result["segments"]] == [(0.0, 1.0), (1.0, 3.0)]
    assert result["cumulative_duration_sec"] == 3.0
    assert result["format"]["sample_rate"] == 24000
    assert result["format"]["bit_depth"] == 16
    assert all(len(segment["md5"]) == 32 for segment in result["segments"])
    assert voice_manifest.read_text(encoding="utf-8") == '{"raw_checkpoint": true}'
    assert audacity_client.verify_adaptive_polished_manifest(str(tmp_path)) == result

    before = audio_manifest.read_bytes()
    write_wav(polished / "Chapter_2.wav", frames=48001)
    with pytest.raises(ValueError, match="no longer match"):
        audacity_client.verify_adaptive_polished_manifest(str(tmp_path))
    assert audio_manifest.read_bytes() == before
    (polished / "Chapter_2.wav").unlink()
    with pytest.raises(ValueError, match="Missing or invalid polished chapter"):
        audacity_client.sync_polished_audio_manifest(str(tmp_path), strict=True)
    assert audio_manifest.read_bytes() == before


def test_adaptive_audacity_refuses_unowned_open_session(tmp_path, monkeypatch):
    monkeypatch.setattr(audacity_client, "audacity_is_running", lambda: True)
    monkeypatch.setattr(
        audacity_client.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("Must not taskkill a user-owned Audacity process"),
    )
    with pytest.raises(RuntimeError, match="already open"):
        audacity_client._process_run(str(tmp_path), adaptive=True, expected_chapters=1)


def test_legacy_audacity_also_refuses_unowned_open_session(tmp_path, monkeypatch):
    monkeypatch.setattr(audacity_client, "audacity_is_running", lambda: True)
    monkeypatch.setattr(
        audacity_client.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("Must not taskkill a user-owned Audacity process"),
    )
    with pytest.raises(RuntimeError, match="user-owned session"):
        audacity_client._process_run(str(tmp_path), adaptive=False)


@pytest.mark.parametrize(
    "response",
    ["BatchCommand finished: Failed\n\n", "BatchCommand finished.\n\n", ""],
)
def test_adaptive_audacity_requires_explicit_command_success(response):
    with pytest.raises(RuntimeError, match="did not confirm success"):
        audacity_client.send_audacity_command(
            io.StringIO(), io.StringIO(response), "Normalize:", strict=True
        )
    assert audacity_client.send_audacity_command(
        io.StringIO(), io.StringIO("BatchCommand finished: OK\n\n"),
        "Normalize:", strict=True,
    )


def test_adaptive_audacity_pipe_exchange_has_a_deadline():
    release = threading.Event()

    class StalledReader:
        def readline(self):
            release.wait(2)
            return ""

    try:
        with pytest.raises(TimeoutError, match="command timed out"):
            audacity_client.send_audacity_command(
                io.StringIO(), StalledReader(), "Normalize:", strict=True,
                timeout_sec=0.05,
            )
    finally:
        release.set()


def test_atomic_stitch_preserves_existing_master_on_bad_chapter(tmp_path):
    first = tmp_path / "Chapter_1.wav"
    second = tmp_path / "Chapter_2.wav"
    master = tmp_path / "full_episode_voice.wav"
    write_wav(first)
    write_wav(second, rate=44100)
    write_wav(master, frames=1200)
    old = master.read_bytes()
    with pytest.raises(ValueError, match="format mismatch"):
        chapter_stitcher.stitch_files([str(first), str(second)], str(master))
    assert master.read_bytes() == old
    write_wav(second, frames=48000)
    chapter_stitcher.stitch_files([str(first), str(second)], str(master))
    with wave.open(str(master), "rb") as audio:
        assert audio.getnframes() == 72000


def test_adaptive_stitch_rejects_partial_polish_without_raw_fallback(tmp_path, monkeypatch):
    from youtube_automation.production import contracts, ledger, narration, writing

    raw = tmp_path / "voice_chapters"
    polished = tmp_path / "polished_chapters"
    raw.mkdir()
    polished.mkdir()
    write_wav(raw / "Chapter_1.wav")
    write_wav(raw / "Chapter_2.wav")
    write_wav(polished / "Chapter_1.wav")
    old_master = tmp_path / "full_episode_voice.wav"
    write_wav(old_master, frames=100)
    original = old_master.read_bytes()
    (tmp_path / "episode_brief.json").write_text("{}", encoding="utf-8")
    (tmp_path / "voice_generation_manifest.json").write_text("{}", encoding="utf-8")
    (tmp_path / "refined_script.txt").write_text("Script", encoding="utf-8")
    monkeypatch.setattr(chapter_stitcher.sys, "argv", ["stitch_chapters.py", str(tmp_path)])
    monkeypatch.setattr(ledger, "resource_database", lambda: tmp_path / "ledger.sqlite3")
    monkeypatch.setattr(writing, "verify_written_episode", lambda _root: True)
    monkeypatch.setattr(contracts, "load_brief", lambda _root: object())
    monkeypatch.setattr(
        narration,
        "prepare_manifest",
        lambda *_args: {"chapters": [{"status": "COMPLETED"}, {"status": "COMPLETED"}]},
    )
    with pytest.raises(ValueError, match="Partial polished chapter"):
        chapter_stitcher.main()
    assert old_master.read_bytes() == original

    write_wav(polished / "Chapter_2.wav")
    manifest_path = tmp_path / "audio_manifest.json"
    manifest_path.write_text(
        json.dumps({"segments": [
            {"index": 1, "status": "COMPLETED"},
            {"index": 2, "status": "COMPLETED"},
        ]}),
        encoding="utf-8",
    )
    audacity_client.sync_polished_audio_manifest(str(tmp_path), strict=True)
    saved_manifest = manifest_path.read_bytes()
    write_wav(polished / "Chapter_2.wav", frames=24001)
    with pytest.raises(ValueError, match="no longer match"):
        chapter_stitcher.main()
    assert old_master.read_bytes() == original
    assert manifest_path.read_bytes() == saved_manifest


def test_adaptive_audio_entrypoints_require_explicit_run(tmp_path, monkeypatch):
    (tmp_path / "episode_brief.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(audacity_client.sys, "argv", ["automate_audacity.py"])
    monkeypatch.setattr(audacity_client, "get_latest_run_folder", lambda: str(tmp_path))
    with pytest.raises(ValueError, match="explicit run directory"):
        audacity_client.main()
    monkeypatch.setattr(chapter_stitcher.sys, "argv", ["stitch_chapters.py"])
    monkeypatch.setattr(chapter_stitcher, "get_latest_run_folder", lambda: str(tmp_path))
    with pytest.raises(ValueError, match="explicit run directory"):
        chapter_stitcher.main()
    monkeypatch.setattr(tts_generator.sys, "argv", ["generate_voice.py"])
    monkeypatch.setattr(tts_generator, "get_latest_run_folder", lambda: str(tmp_path))
    monkeypatch.setattr(tts_generator, "read_voice_options", lambda: {"voice": "Nova"})
    with pytest.raises(ValueError, match="explicit run directory"):
        tts_generator.main()
