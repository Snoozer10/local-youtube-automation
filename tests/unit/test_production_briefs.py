import json

import pytest

from youtube_automation.production.briefs import analyze_script, ensure_brief, writing_prompt
from youtube_automation.production.contracts import Channel, fingerprint


@pytest.fixture
def channel():
    return Channel(
        channel_id="science",
        name="Science",
        audience="adults",
        language="Arabic",
        dialect="MSA",
        voice="saved-voice",
        tone="calm",
        style="editorial illustration",
        allowed_treatments=["subject_scene", "mechanism"],
    )


def response(**changes):
    data = {
        "topics": ["animals"],
        "form": "explanation",
        "proposition": "Animal perception",
        "narrative_strategy": "Observe then explain",
        "treatments": ["subject_scene"],
        "rationale": "An observable relationship",
    }
    data.update(changes)
    return json.dumps(data)


def test_identity_and_resume(tmp_path, channel):
    (tmp_path / "raw_transcript.txt").write_text("Animal perception", encoding="utf-8")
    brief = ensure_brief(tmp_path, channel, lambda _: response())
    resumed = ensure_brief(tmp_path, channel, lambda _: pytest.fail("Must use valid cached brief"))
    assert brief == resumed
    assert brief.profile_sha256 == fingerprint(channel)
    assert "MSA" in writing_prompt(brief, "translate")
    (tmp_path / "final_output.txt").write_text("translated", encoding="utf-8")
    (tmp_path / "raw_transcript.txt").write_text("Changed script", encoding="utf-8")
    with pytest.raises(ValueError, match="downstream"):
        ensure_brief(tmp_path, channel, lambda _: response())


def test_channel_policy_cannot_be_overridden(channel):
    with pytest.raises(ValueError, match="outside channel policy"):
        analyze_script("animals", channel, lambda _: response(treatments=["host"]))
    with pytest.raises(ValueError):
        analyze_script("animals", channel, lambda _: response(channel_id="imposter"))


def test_all_sections_are_analyzed(channel):
    calls = []

    def ask(prompt):
        calls.append(prompt)
        return response()

    analyze_script("begin " * 1800 + "UNIQUE_END", channel, ask)
    assert len(calls) == 3
    assert "UNIQUE_END" in calls[1]
    assert "Synthesize ALL" in calls[2]


def test_malformed_response_retries_are_bounded(channel):
    calls = []

    def ask(prompt):
        calls.append(prompt)
        return "not json"

    with pytest.raises(ValueError, match="3 attempts"):
        analyze_script("animals", channel, ask)
    assert len(calls) == 3


def test_profiles_change_writing_without_changing_source(channel):
    first = analyze_script("Animal perception", channel, lambda _: response())
    other = channel.model_copy(
        update={"channel_id": "comedy", "tone": "playful", "humor": "central"}
    )
    second = analyze_script("Animal perception", other, lambda _: response())
    assert first.source_sha256 == second.source_sha256
    assert first.profile_sha256 != second.profile_sha256
    assert writing_prompt(first, "refine") != writing_prompt(second, "refine")
