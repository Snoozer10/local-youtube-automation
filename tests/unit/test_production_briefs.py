import hashlib
import json

import pytest

from youtube_automation.production.briefs import (
    BrowserTransport,
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


def test_persistent_browser_transport_keeps_repairs_in_one_chat_and_receipts(
    tmp_path, monkeypatch, channel
):
    from youtube_automation.browser import gemini_utils

    starts = []
    submitted = []
    responses = ["not json", response()]

    class Page:
        url = "https://gemini.google.com/app/planner-chat"

    class Client:
        def __init__(self, _page, _model):
            pass

        def dispatch_prompt(self, prompt):
            submitted.append(prompt)
            return True, len(submitted) - 1

    monkeypatch.setattr(gemini_utils, "GeminiSessionClient", Client)
    monkeypatch.setattr(gemini_utils, "start_clean_gemini_chat", lambda _page: starts.append(1))
    monkeypatch.setattr(gemini_utils, "select_gemini_model", lambda _page, _model: True)
    monkeypatch.setattr(
        gemini_utils,
        "wait_for_gemini_response",
        lambda *_args, **_kwargs: responses.pop(0),
    )
    transport = BrowserTransport(
        Page(), "Pro", persistent_chat=True, receipt_dir=tmp_path, timeout_seconds=600
    )
    transport.begin_window(0, 575)
    parsed = request_json("plan window", transport, Analysis)
    assert parsed.proposition == "Animal perception"
    assert len(starts) == 1
    assert len(submitted) == 2
    assert "Repair the previous validation error" in submitted[1]
    receipts = [json.loads(path.read_text(encoding="utf-8")) for path in tmp_path.glob("*.json")]
    assert len(receipts) == 2
    assert all(item["window"] == [0, 575] for item in receipts)
    assert all(item["attempts"][-1]["state"] == "completed" for item in receipts)


def test_transport_retry_reuses_exact_prompt_and_content_bound_receipt(
    tmp_path, monkeypatch
):
    from youtube_automation.browser import gemini_utils

    starts = []
    submitted = []
    responses = ["", response()]

    class Page:
        url = "https://gemini.google.com/app/retry-chat"

    class Client:
        def __init__(self, _page, _model):
            pass

        def dispatch_prompt(self, prompt):
            submitted.append(prompt)
            return True, len(submitted) - 1

    monkeypatch.setattr(gemini_utils, "GeminiSessionClient", Client)
    monkeypatch.setattr(gemini_utils, "start_clean_gemini_chat", lambda _page: starts.append(1))
    monkeypatch.setattr(gemini_utils, "select_gemini_model", lambda _page, _model: True)
    monkeypatch.setattr(
        gemini_utils,
        "wait_for_gemini_response",
        lambda *_args, **_kwargs: responses.pop(0),
    )
    transport = BrowserTransport(Page(), "Pro", True, tmp_path, 600)
    transport.begin_window(0, 575)
    parsed = request_json("same prompt", transport, Analysis)
    assert parsed.proposition == "Animal perception"
    assert submitted == ["same prompt", "same prompt"]
    assert len(starts) == 1
    receipt_files = list(tmp_path.glob("*.json"))
    assert len(receipt_files) == 1
    attempts = json.loads(receipt_files[0].read_text(encoding="utf-8"))["attempts"]
    assert [attempt["state"] for attempt in attempts] == ["timed_out", "completed"]


def test_timed_out_response_is_recovered_from_its_bound_chat_without_resubmission(
    tmp_path, monkeypatch
):
    from youtube_automation.browser import gemini_utils

    submitted = []

    class Responses:
        def count(self):
            return 1

        def nth(self, _index):
            return self

        def evaluate(self, _expression, timeout):
            assert timeout == 4000
            return "Gemini said\n" + response()

    class Page:
        url = "https://gemini.google.com/app/late-chat"

        def wait_for_selector(self, selector, timeout):
            assert selector == gemini_utils.RESPONSE_SELECTOR
            assert timeout == 15000

        def locator(self, selector):
            assert selector == gemini_utils.RESPONSE_SELECTOR
            return Responses()

    class Client:
        def __init__(self, _page, _model):
            pass

        def dispatch_prompt(self, prompt):
            submitted.append(prompt)
            return True, 0

    waits = ["", response()]
    monkeypatch.setattr(gemini_utils, "GeminiSessionClient", Client)
    monkeypatch.setattr(gemini_utils, "start_clean_gemini_chat", lambda _page: None)
    monkeypatch.setattr(gemini_utils, "select_gemini_model", lambda _page, _model: True)
    monkeypatch.setattr(
        gemini_utils, "wait_for_gemini_response", lambda *_args, **_kwargs: waits.pop(0)
    )
    transport = BrowserTransport(Page(), "Pro", True, tmp_path, 600)
    transport.begin_window(0, 575)
    parsed = request_json("late prompt", transport, Analysis)
    assert parsed.proposition == "Animal perception"
    assert submitted == ["late prompt"]
    receipt = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert receipt["attempts"][0]["recovered_after_timeout"] is True
    assert receipt["attempts"][0]["recovered_from_state"] == "timed_out"


def test_interrupted_submitted_response_is_recovered_without_resubmission(
    tmp_path, monkeypatch
):
    from youtube_automation.browser import gemini_utils

    prompt = "interrupted prompt"
    prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    chat_url = "https://gemini.google.com/app/interrupted-chat"

    class Page:
        url = chat_url

        def wait_for_selector(self, selector, timeout):
            assert selector == gemini_utils.RESPONSE_SELECTOR
            assert timeout == 15000

    receipt_path = tmp_path / f"{prompt_sha256}.json"
    receipt_path.write_text(
        json.dumps(
            {
                "version": 1,
                "prompt_sha256": prompt_sha256,
                "model": "Pro",
                "window": [0, 575],
                "attempts": [
                    {
                        "submitted_at": 1.0,
                        "chat_url": chat_url,
                        "initial_response_count": 0,
                        "state": "submitted",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        gemini_utils,
        "wait_for_gemini_response",
        lambda _page, initial_count, timeout_seconds: (
            response() if initial_count == 0 and timeout_seconds == 15 else ""
        ),
    )
    monkeypatch.setattr(
        gemini_utils,
        "start_clean_gemini_chat",
        lambda _page: pytest.fail("recovery must not open a new chat"),
    )

    transport = BrowserTransport(Page(), "Pro", True, tmp_path, 600)
    transport.begin_window(0, 575)
    parsed = request_json(prompt, transport, Analysis)

    assert parsed.proposition == "Animal perception"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["attempts"][0]["state"] == "completed"
    assert receipt["attempts"][0]["recovered_from_state"] == "submitted"
    assert receipt["attempts"][0]["recovered_after_interruption"] is True


def test_profiles_change_writing_without_changing_source(channel):
    first = analyze_script("Animal perception", channel, lambda _: response())
    other = channel.model_copy(
        update={"channel_id": "comedy", "tone": "playful", "humor": "central"}
    )
    second = analyze_script("Animal perception", other, lambda _: response())
    assert first.source_sha256 == second.source_sha256
    assert first.profile_sha256 != second.profile_sha256
    assert writing_prompt(first, "refine") != writing_prompt(second, "refine")
