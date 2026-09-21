import json

import pytest

from youtube_automation.production.briefs import (
    analyze_script,
    ensure_brief,
    request_json,
    writing_prompt,
)
from youtube_automation.production.contracts import Analysis, Channel, fingerprint


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
        "claim_basis": "factual",
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
    assert brief.version == 2
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


def test_fictional_analysis_separates_continuity_from_evidence(channel):
    calls = []

    def bad_then_good(prompt):
        calls.append(prompt)
        if len(calls) == 1:
            return response(
                claim_basis="fictional",
                evidence_needs=["Show the floor literally cracking when her heart races"],
                figurative_phrases=["Her heartbeat cracked the floor"],
            )
        return response(
            claim_basis="fictional",
            evidence_needs=[],
            continuity_anchors=["The manager's child is waiting in the staff room"],
            figurative_phrases=["Her heartbeat cracked the floor"],
        )

    brief = analyze_script("A romantic comedy recap", channel, bad_then_good)
    assert len(calls) == 2
    assert "must be empty for fictional material" in calls[0]
    assert "Fictional narratives cannot request external factual evidence" in calls[1]
    assert brief.analysis.evidence_needs == []
    assert brief.analysis.continuity_anchors == [
        "The manager's child is waiting in the staff room"
    ]


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

    with pytest.raises(ValueError, match="response excerpt='not json'"):
        analyze_script("animals", channel, ask)
    assert len(calls) == 3


def test_request_json_accepts_bare_language_label(channel):
    parsed = request_json("prompt", lambda _: "JSON\n" + response(), Analysis)
    assert parsed.proposition == "Animal perception"


def test_request_json_accepts_non_structured_trailing_commentary(channel):
    parsed = request_json("prompt", lambda _: response() + "\nGenerated as requested.", Analysis)
    assert parsed.proposition == "Animal perception"


def test_request_json_rejects_multiple_structures(channel):
    with pytest.raises(ValueError, match="more than one JSON structure"):
        request_json("prompt", lambda _: response() + "\n" + response(), Analysis, attempts=1)


def test_request_json_retries_bounded_browser_transport_failure(channel):
    calls = []

    def ask(_prompt):
        calls.append(None)
        if len(calls) == 1:
            raise RuntimeError("transient Gemini error")
        return response()

    parsed = request_json("prompt", ask, Analysis)
    assert parsed.proposition == "Animal perception"
    assert len(calls) == 2


def test_request_json_preserves_transport_error_after_retry_budget(channel):
    with pytest.raises(RuntimeError, match="after 2 attempts"):
        request_json(
            "prompt",
            lambda _: (_ for _ in ()).throw(RuntimeError("offline")),
            Analysis,
            attempts=2,
        )


def test_profiles_change_writing_without_changing_source(channel):
    first = analyze_script("Animal perception", channel, lambda _: response())
    other = channel.model_copy(
        update={"channel_id": "comedy", "tone": "playful", "humor": "central"}
    )
    second = analyze_script("Animal perception", other, lambda _: response())
    assert first.source_sha256 == second.source_sha256
    assert first.profile_sha256 != second.profile_sha256
    assert writing_prompt(first, "refine") != writing_prompt(second, "refine")
