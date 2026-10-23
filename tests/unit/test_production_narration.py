"""Adaptive narration never reuses chapters from another script or channel."""

import hashlib
import io
import wave
from pathlib import Path

import pytest

from youtube_automation.production.contracts import Analysis, Brief, Channel, fingerprint
from youtube_automation.production.narration import (
    prepare_manifest,
    require_unpolished_run,
    split_chapters,
)


def make_brief(*, voice="Nova"):
    channel = Channel(
        channel_id="science",
        name="Science",
        audience="curious adults",
        language="English",
        dialect="US",
        voice=voice,
        tone="precise",
        style="editorial illustration",
        allowed_treatments=["subject_scene"],
    )
    analysis = Analysis(
        topics=["orbits"],
        claim_basis="factual",
        form="explanation",
        proposition="An orbit follows gravity",
        narrative_strategy="Explain with concrete examples",
        treatments=["subject_scene"],
        rationale="Concrete subject scenes",
    )
    return Brief(
        source_sha256=fingerprint("raw"),
        profile_sha256=fingerprint(channel),
        channel=channel,
        analysis=analysis,
    )


def wav_bytes():
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(b"\0\0" * 240)
    return output.getvalue()


def test_partition_keeps_every_word_and_resolves_relative_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    script = "One two three four five six seven.\n\nEight nine ten eleven twelve."
    chapters = split_chapters("run", script, max_words=4)
    assert all(len(chapter["text"].split()) <= 4 for chapter in chapters)
    assert " ".join(chapter["text"] for chapter in chapters) == " ".join(script.split())
    assert Path(chapters[0]["audio_file"]).is_absolute()
    assert Path(chapters[0]["audio_file"]).parent == (tmp_path / "run" / "voice_chapters")


def test_adaptive_voice_resume_validates_recipe_and_completed_wav(tmp_path):
    brief = make_brief()
    script = "The planet follows an orbit."
    manifest = {"voice_config": {"voice": "Nova"}, "chapters": []}
    prepared = prepare_manifest(tmp_path, manifest, brief, script)
    assert prepared["gemini_completed"] is True
    assert prepare_manifest(tmp_path, prepared, brief, script)["chapters"] == prepared["chapters"]

    chapter = prepared["chapters"][0]
    path = Path(chapter["audio_file"])
    path.parent.mkdir()
    data = wav_bytes()
    path.write_bytes(data)
    chapter["audio_file"] = str(path.relative_to(tmp_path))  # audio manifest normalizes this.
    chapter["status"] = "COMPLETED"
    chapter["md5"] = hashlib.md5(data).hexdigest()
    assert prepare_manifest(tmp_path, prepared, brief, script)["chapters"][0]["status"] == "COMPLETED"

    path.write_bytes(data + b"tampered")
    with pytest.raises(ValueError, match="audio changed"):
        prepare_manifest(tmp_path, prepared, brief, script)


def test_adaptive_voice_rejects_legacy_and_changed_inputs(tmp_path):
    brief = make_brief()
    manifest = {"voice_config": {"voice": "Nova"}, "chapters": []}
    script = "A script for narration."
    prepared = prepare_manifest(tmp_path, manifest, brief, script)
    with pytest.raises(ValueError, match="matching adaptive recipe"):
        prepare_manifest(tmp_path, {**manifest, "chapters": prepared["chapters"]}, brief, script)
    with pytest.raises(ValueError, match="matching adaptive recipe"):
        prepare_manifest(tmp_path, prepared, brief, "A new script for narration.")
    with pytest.raises(ValueError, match="matching adaptive recipe"):
        prepare_manifest(tmp_path, prepared, make_brief(voice="Other"), script)
    with pytest.raises(ValueError, match="voice differs"):
        prepare_manifest(tmp_path, {**manifest, "voice_config": {"voice": "Other"}}, brief, script)


def test_completed_chapter_requires_digest_and_valid_wav(tmp_path):
    brief = make_brief()
    prepared = prepare_manifest(
        tmp_path, {"voice_config": {"voice": "Nova"}, "chapters": []}, brief, "Narration text."
    )
    chapter = prepared["chapters"][0]
    path = Path(chapter["audio_file"])
    path.parent.mkdir()
    path.write_bytes(b"not a wav")
    chapter["status"] = "COMPLETED"
    with pytest.raises(ValueError, match="missing its audio or digest"):
        prepare_manifest(tmp_path, prepared, brief, "Narration text.")
    chapter["md5"] = hashlib.md5(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="not valid WAV"):
        prepare_manifest(tmp_path, prepared, brief, "Narration text.")


def test_manifest_write_failure_is_propagated(tmp_path, monkeypatch):
    from youtube_automation.audio import tts_generator

    original = tmp_path / tts_generator.MANIFEST_FILE_NAME
    original.write_text('{"old": true}', encoding="utf-8")

    def fail_replace(*_args):
        raise OSError("disk full")

    monkeypatch.setattr(tts_generator.os, "replace", fail_replace)
    with pytest.raises(OSError, match="Failed to write manifest checkpoint"):
        tts_generator.save_manifest(str(tmp_path), {"new": True})
    assert original.read_text(encoding="utf-8") == '{"old": true}'


def test_voice_rerun_cannot_overwrite_polished_offsets(tmp_path):
    require_unpolished_run(tmp_path)
    polished = tmp_path / "polished_chapters"
    polished.mkdir()
    (polished / "Chapter_1.wav").write_bytes(b"candidate")
    with pytest.raises(ValueError, match="already has polished"):
        require_unpolished_run(tmp_path)
    (polished / "Chapter_1.wav").unlink()
    (tmp_path / "full_episode_voice.wav").write_bytes(b"accepted master")
    with pytest.raises(ValueError, match="already has polished"):
        require_unpolished_run(tmp_path)
