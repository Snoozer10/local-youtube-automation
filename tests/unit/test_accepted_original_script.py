import json

import pytest

from youtube_automation.production.briefs import ensure_brief
from youtube_automation.production.contracts import Channel, fingerprint
from youtube_automation.production.narration import split_chapters
from youtube_automation.production.writing import (
    ACCEPTED_ORIGINAL_MODE,
    SCRIPT_ACCEPTANCE_FILE,
    publish_accepted_original,
    verify_written_episode,
)

RAW = "First paragraph of the original.\n\nSecond paragraph, written by a human.\n"
OUTPUTS = ("breaked_paragraphs.txt", "final_output.txt", "refined_script.txt")


def _setup(tmp_path, raw=RAW, **overrides):
    channel = Channel(
        channel_id="original-test",
        name="Original Test",
        audience="adults",
        language="English",
        dialect="neutral",
        voice="Charon",
        tone="serious",
        style="illustration",
        humor="none",
        allowed_treatments=["subject_scene"],
    )
    (tmp_path / "raw_transcript.txt").write_bytes(raw.encode("utf-8"))
    analysis = {
        "topics": ["history"],
        "claim_basis": "factual",
        "form": "chronology",
        "proposition": "A journey",
        "narrative_strategy": "Follow events",
        "treatments": ["subject_scene"],
        "rationale": "Chronology",
    }
    brief = ensure_brief(tmp_path, channel, lambda _: json.dumps(analysis))
    acceptance = {
        "version": 1,
        "kind": "accepted_original_script",
        "channel_id": channel.channel_id,
        "script_sha256": fingerprint(raw),
        "accepted_by": "reviewer",
        "statement": "I accept this script as written.",
    }
    acceptance.update(overrides)
    (tmp_path / SCRIPT_ACCEPTANCE_FILE).write_text(json.dumps(acceptance), encoding="utf-8")
    return brief, acceptance


def _no_outputs(tmp_path):
    assert not any((tmp_path / name).exists() for name in OUTPUTS)
    assert not (tmp_path / "adaptive_writing_receipt.json").exists()


def test_publish_accepted_original_is_verbatim_and_verifies(tmp_path):
    brief, acceptance = _setup(tmp_path)
    receipt = publish_accepted_original(tmp_path, brief)
    expected = RAW.strip() + "\n"
    for name in OUTPUTS:
        assert (tmp_path / name).read_text(encoding="utf-8") == expected
    assert receipt["mode"] == ACCEPTED_ORIGINAL_MODE
    assert receipt["acceptance_sha256"] == fingerprint(acceptance)
    assert verify_written_episode(tmp_path) is True


def test_second_publish_returns_same_receipt_without_rewriting(tmp_path):
    brief, _ = _setup(tmp_path)
    first = publish_accepted_original(tmp_path, brief)
    before = {n: (tmp_path / n).stat().st_mtime_ns for n in (*OUTPUTS, "adaptive_writing_receipt.json")}
    second = publish_accepted_original(tmp_path, brief)
    after = {n: (tmp_path / n).stat().st_mtime_ns for n in before}
    assert second == first
    assert before == after


def test_wrong_script_hash_is_rejected(tmp_path):
    brief, _ = _setup(tmp_path, script_sha256="0" * 64)
    with pytest.raises(ValueError, match="does not bind"):
        publish_accepted_original(tmp_path, brief)
    _no_outputs(tmp_path)


def test_wrong_channel_is_rejected(tmp_path):
    brief, _ = _setup(tmp_path, channel_id="other")
    with pytest.raises(ValueError, match="does not bind"):
        publish_accepted_original(tmp_path, brief)
    _no_outputs(tmp_path)


def test_final_script_markup_is_rejected(tmp_path):
    brief, _ = _setup(tmp_path, raw="Intro.\n\n<final_script>Body</final_script>\n")
    with pytest.raises(ValueError, match="final_script"):
        publish_accepted_original(tmp_path, brief)
    _no_outputs(tmp_path)


def test_source_narrated_run_is_rejected(tmp_path):
    brief, _ = _setup(tmp_path)
    (tmp_path / "source_audio_receipt.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Source-narrated"):
        publish_accepted_original(tmp_path, brief)
    _no_outputs(tmp_path)


def test_editing_acceptance_after_publish_breaks_verification(tmp_path):
    brief, acceptance = _setup(tmp_path)
    publish_accepted_original(tmp_path, brief)
    acceptance["statement"] = "Changed statement."
    (tmp_path / SCRIPT_ACCEPTANCE_FILE).write_text(json.dumps(acceptance), encoding="utf-8")
    with pytest.raises(ValueError, match="acceptance changed"):
        verify_written_episode(tmp_path)


def test_editing_output_after_publish_breaks_verification(tmp_path):
    brief, _ = _setup(tmp_path)
    publish_accepted_original(tmp_path, brief)
    (tmp_path / "refined_script.txt").write_text("Edited.\n", encoding="utf-8")
    with pytest.raises(ValueError):
        verify_written_episode(tmp_path)


def test_published_text_splits_into_one_verbatim_chapter(tmp_path):
    brief, _ = _setup(tmp_path)
    publish_accepted_original(tmp_path, brief)
    published = (tmp_path / "refined_script.txt").read_text(encoding="utf-8")
    chapters = split_chapters(tmp_path, published.strip())
    assert len(chapters) == 1
    assert chapters[0]["text"] == " ".join(RAW.split())
