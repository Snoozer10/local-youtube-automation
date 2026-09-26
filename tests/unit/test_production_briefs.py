import hashlib
import json

import pytest
from pydantic import BaseModel

from youtube_automation.production.briefs import (
    BrowserTransport,
    analyze_script,
    ensure_brief,
    is_visual_policy_update,
    rebind_visual_policy,
    request_json,
    writing_prompt,
)
from youtube_automation.production.contracts import (
    Analysis,
    Channel,
    EpisodeVisualStrategy,
    fingerprint,
    narration_fingerprint,
)


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


def test_version_three_channel_compiles_source_bound_episode_visual_strategy(channel):
    channel = channel.model_copy(
        update={
            "version": 3,
            "visual_directives": ["Use episode-specific visual systems"],
            "forbidden_motifs": ["generic productivity B-roll"],
        }
    )
    raw = "Why does attention fail at a doorway, and how can a visual challenge test it?"
    source_sha256 = fingerprint(raw)
    strategy = EpisodeVisualStrategy(
        source_sha256=source_sha256,
        topic="Everyday attention failures and a visual search challenge",
        viewer_question="Why does attention disappear at the moment we need it?",
        central_promise="Recognize the failure and try one concrete attention challenge",
        evidence_mode="demonstrative",
        emotional_arc=["recognition", "curiosity", "agency"],
        hook_archetype="cold_open_challenge",
        hook_microbeats=[
            {
                "beat_id": "problem",
                "function": "problem",
                "duration_seconds": 3,
                "viewer_takeaway": "My attention fails in familiar ways",
                "visual_mode": "human_context",
            },
            {
                "beat_id": "gap",
                "function": "curiosity",
                "duration_seconds": 3,
                "viewer_takeaway": "The failure has a testable pattern",
                "visual_mode": "kinetic_type",
                "local_ui": ["focus_sweep"],
            },
            {
                "beat_id": "promise",
                "function": "promise",
                "duration_seconds": 3,
                "viewer_takeaway": "I will try the challenge now",
                "visual_mode": "challenge_ui",
                "local_ui": ["timer", "highlight"],
            },
        ],
        visual_modes=["human_context", "kinetic_type", "challenge_ui"],
        local_ui_kit=["focus_sweep", "timer", "highlight"],
        pacing="Fast opening, then enough hold time to perform the challenge",
        motion_grammar=["Use motion only for focus and state change"],
    )
    calls = []

    def ask(prompt):
        calls.append(prompt)
        return response() if len(calls) == 1 else strategy.model_dump_json()

    brief = analyze_script(raw, channel, ask)

    assert brief.version == 3
    assert brief.visual_strategy == strategy
    assert len(calls) == 2
    assert source_sha256 in calls[1]
    assert "8-15 second hook" in calls[1]


def test_matching_legacy_brief_is_upgraded_when_v3_strategy_is_missing(
    tmp_path, channel
):
    raw = "Animal perception"
    channel = channel.model_copy(
        update={
            "version": 3,
            "visual_directives": ["Use episode-specific visual systems"],
            "forbidden_motifs": ["generic B-roll"],
        }
    )
    legacy = analyze_script(raw, channel.model_copy(update={"version": 2}), lambda _: response())
    legacy = legacy.model_copy(
        update={"channel": channel, "profile_sha256": fingerprint(channel)}
    )
    (tmp_path / "raw_transcript.txt").write_text(raw, encoding="utf-8")
    (tmp_path / "episode_brief.json").write_text(
        legacy.model_dump_json(), encoding="utf-8"
    )
    strategy = EpisodeVisualStrategy(
        source_sha256=fingerprint(raw),
        topic="Animal perception",
        viewer_question="What does an animal notice?",
        central_promise="See perception from another point of view",
        evidence_mode="observational",
        emotional_arc=["familiarity", "curiosity"],
        hook_archetype="mystery_gap",
        hook_microbeats=[
            {"beat_id": "p", "function": "problem", "duration_seconds": 3, "viewer_takeaway": "I miss signals", "visual_mode": "human_context"},
            {"beat_id": "c", "function": "curiosity", "duration_seconds": 3, "viewer_takeaway": "Animals see other signals", "visual_mode": "environmental_detail"},
            {"beat_id": "h", "function": "handoff", "duration_seconds": 3, "viewer_takeaway": "The episode will compare them", "visual_mode": "comparison"},
        ],
        visual_modes=["human_context", "environmental_detail", "comparison"],
        pacing="Quick question followed by observed examples",
        motion_grammar=["Use a focus sweep only to reveal missed detail"],
    )

    upgraded = ensure_brief(tmp_path, channel, lambda _: strategy.model_dump_json())

    assert upgraded.version == 3
    assert upgraded.visual_strategy == strategy


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


def test_request_json_recovers_one_complete_restart_after_broken_draft(channel):
    broken_then_restarted = (
        '{"topics": ["animals"], "proposition": "unfinished\n'
        "```json\n"
        + response()
    )
    parsed = request_json("prompt", lambda _: broken_then_restarted, Analysis, attempts=1)
    assert parsed.proposition == "Animal perception"


def test_request_json_rejects_multiple_complete_restarts(channel):
    ambiguous = "broken\n```json\n" + response() + "\n```json\n" + response()
    with pytest.raises(ValueError):
        request_json("prompt", lambda _: ambiguous, Analysis, attempts=1)


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


def test_request_json_preserves_first_candidate_across_multiple_repairs():
    class Payload(BaseModel):
        kept: str
        count: int

    class Transport:
        def __init__(self):
            self.repairs = []
            self.responses = [
                '{"count":"still invalid"}',
                '{"kept":"baseline value","count":2}',
            ]

        def __call__(self, _prompt):
            return '{"kept":"baseline value","count":"invalid"}'

        def repair_json(self, *args):
            self.repairs.append(args)
            return self.responses.pop(0)

        def reject_last_response(self, _error):
            pass

    transport = Transport()
    parsed = request_json("request", transport, Payload)

    assert parsed == Payload(kept="baseline value", count=2)
    assert len(transport.repairs) == 2
    assert '"kept":"baseline value"' in transport.repairs[1][2]
    assert '"kept"' not in transport.repairs[1][3]


def test_transport_failure_does_not_consume_schema_repair_budget():
    replies = iter(["not json", RuntimeError("provider error"), "still not json", response()])
    calls = []

    def ask(prompt):
        calls.append(prompt)
        reply = next(replies)
        if isinstance(reply, RuntimeError):
            raise reply
        return reply

    parsed = request_json("prompt", ask, Analysis, attempts=3)

    assert parsed.proposition == "Animal perception"
    assert len(calls) == 4
    assert "Repair the previous validation error" in calls[-1]


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
    assert "Repair the latest rejected JSON candidate" in submitted[1]
    receipts = [json.loads(path.read_text(encoding="utf-8")) for path in tmp_path.glob("*.json")]
    assert len(receipts) == 2
    assert all(item["window"] == [0, 575] for item in receipts)
    assert sorted(item["attempts"][-1]["state"] for item in receipts) == [
        "completed",
        "rejected",
    ]


def test_rejected_completed_receipt_is_not_replayed(tmp_path, monkeypatch):
    from youtube_automation.browser import gemini_utils

    submitted = []
    responses = ["not json", response()]

    class Page:
        url = "https://gemini.google.com/app/rejected-chat"

    class Client:
        def __init__(self, _page, _model):
            pass

        def dispatch_prompt(self, prompt):
            submitted.append(prompt)
            return True, len(submitted) - 1

    monkeypatch.setattr(gemini_utils, "GeminiSessionClient", Client)
    monkeypatch.setattr(gemini_utils, "start_clean_gemini_chat", lambda _page: None)
    monkeypatch.setattr(gemini_utils, "select_gemini_model", lambda _page, _model: True)
    monkeypatch.setattr(
        gemini_utils,
        "wait_for_gemini_response",
        lambda *_args, **_kwargs: responses.pop(0),
    )
    transport = BrowserTransport(Page(), "Pro", True, tmp_path, 600)
    transport.begin_window(0, 575)

    parsed = request_json("plan window", transport, Analysis)

    assert parsed.proposition == "Animal perception"
    receipts = [json.loads(path.read_text(encoding="utf-8")) for path in tmp_path.glob("*.json")]
    assert sorted(item["attempts"][-1]["state"] for item in receipts) == [
        "completed",
        "rejected",
    ]
    rejected = next(
        item for item in receipts if item["attempts"][-1]["state"] == "rejected"
    )
    assert "validation_error" in rejected["attempts"][-1]
    assert len(submitted) == 2


def test_transport_retry_reuses_exact_prompt_in_a_fresh_chat_and_content_bound_receipt(
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
    assert len(starts) == 2
    receipt_files = list(tmp_path.glob("*.json"))
    assert len(receipt_files) == 1
    attempts = json.loads(receipt_files[0].read_text(encoding="utf-8"))["attempts"]
    assert [attempt["state"] for attempt in attempts] == ["timed_out", "completed"]


def test_provider_soft_refusal_retries_exact_prompt_in_clean_chat(tmp_path, monkeypatch):
    from youtube_automation.browser import gemini_utils

    starts = []
    submitted = []
    responses = [
        "I'm having a hard time fulfilling your request. Can I help you with something else instead?",
        response(),
    ]

    class Page:
        url = "https://gemini.google.com/app/refusal-chat"

    class Client:
        def __init__(self, _page, _model):
            pass

        def dispatch_prompt(self, prompt):
            submitted.append(prompt)
            return True, 0

    monkeypatch.setattr(gemini_utils, "GeminiSessionClient", Client)
    monkeypatch.setattr(
        gemini_utils, "start_clean_gemini_chat", lambda _page: starts.append(1)
    )
    monkeypatch.setattr(gemini_utils, "select_gemini_model", lambda _page, _model: True)
    monkeypatch.setattr(
        gemini_utils,
        "wait_for_gemini_response",
        lambda *_args, **_kwargs: responses.pop(0),
    )
    transport = BrowserTransport(Page(), "Flash", True, tmp_path, 600)
    transport.begin_window(0, 575)

    parsed = request_json("same request", transport, Analysis)

    assert parsed.proposition == "Animal perception"
    assert submitted == ["same request", "same request"]
    assert len(starts) == 2
    receipt = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert [attempt["state"] for attempt in receipt["attempts"]] == [
        "provider_refusal",
        "completed",
    ]


@pytest.mark.parametrize(
    "message",
    [
        "I'm having hard time fulfilling request. Can I help you with something else instead?",
        "I encountered an error doing what you asked. Could you try again?",
        "I encountered error doing what you asked. Could you try again?",
        "I seem to be encountering an error. Can I try something else for you?",
        "I seem be encountering an error. Can I try something else for you?",
    ],
)
def test_known_provider_error_cards_are_transport_failures(message):
    from youtube_automation.production.briefs import _is_provider_soft_refusal

    assert _is_provider_soft_refusal(message)


def test_file_attachment_transport_submits_short_bound_instruction(
    tmp_path, monkeypatch
):
    from youtube_automation.browser import gemini_utils

    submitted = []
    attached = []

    class Page:
        url = "https://gemini.google.com/app/file-chat"

    class Client:
        def __init__(self, _page, _model):
            pass

        def dispatch_prompt(self, prompt):
            submitted.append(prompt)
            return True, 0

    monkeypatch.setattr(gemini_utils, "GeminiSessionClient", Client)
    monkeypatch.setattr(gemini_utils, "start_clean_gemini_chat", lambda _page: None)
    monkeypatch.setattr(gemini_utils, "select_gemini_model", lambda _page, _model: True)
    monkeypatch.setattr(
        gemini_utils, "wait_for_gemini_response", lambda *_args, **_kwargs: response()
    )
    transport = BrowserTransport(
        Page(),
        "Flash",
        persistent_chat=True,
        receipt_dir=tmp_path,
        timeout_seconds=600,
        attachment_mode="file",
    )
    monkeypatch.setattr(transport, "_attach_prompt_file", lambda path: attached.append(path))
    transport.begin_window(1156, 1734)

    result = transport("large planning payload")

    assert result == response()
    assert len(attached) == 1
    assert attached[0].read_text(encoding="utf-8") == "large planning payload"
    assert submitted[0].startswith("Read the attached UTF-8 planning request completely")
    assert "large planning payload" not in submitted[0]
    assert "SHA-256" not in submitted[0]
    assert attached[0].name.startswith("visual-plan-")
    assert len(attached[0].stem.removeprefix("visual-plan-")) == 8
    assert "Request ID:" in submitted[0]
    receipt = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert receipt["version"] == 2
    assert receipt["transport"] == "file"
    assert receipt["attempts"][0]["attachment"] == attached[0].name


def test_file_validation_repair_uses_a_bound_repair_attachment(tmp_path, monkeypatch):
    from youtube_automation.browser import gemini_utils

    starts = []
    attached = []
    submitted = []
    long_invalid = "not json " + ("x" * 5000)
    responses = [long_invalid, response()]

    class Locator:
        def count(self):
            return 0

    class Page:
        url = "https://gemini.google.com/app/file-repair"

        def locator(self, _selector):
            return Locator()

    class Client:
        def __init__(self, _page, _model):
            pass

        def dispatch_prompt(self, prompt):
            submitted.append(prompt)
            return True, len(submitted) - 1

    monkeypatch.setattr(gemini_utils, "GeminiSessionClient", Client)
    monkeypatch.setattr(
        gemini_utils, "start_clean_gemini_chat", lambda _page: starts.append(1)
    )
    monkeypatch.setattr(gemini_utils, "select_gemini_model", lambda _page, _model: True)
    monkeypatch.setattr(
        gemini_utils,
        "wait_for_gemini_response",
        lambda *_args, **_kwargs: responses.pop(0),
    )
    transport = BrowserTransport(
        Page(), "Flash", True, tmp_path, 600, attachment_mode="file"
    )
    monkeypatch.setattr(transport, "_attach_prompt_file", lambda path: attached.append(path))

    parsed = request_json("large request", transport, Analysis)

    assert parsed.proposition == "Animal perception"
    assert len(starts) == 1
    assert len(attached) == 2
    assert "Request ID:" in submitted[0]
    assert "Request ID:" in submitted[1]
    repair_packet = attached[1].read_text(encoding="utf-8")
    assert repair_packet.startswith("Repair the latest rejected JSON candidate")
    assert "Baseline JSON candidate:\nnot json" in repair_packet
    assert "Latest rejected JSON candidate:\nnot json" in repair_packet
    assert "restore every unaffected field" in repair_packet
    assert "Exact JSON schema:" in repair_packet
    assert "large request" not in repair_packet
    repair_receipt = next(
        receipt
        for receipt in (
            json.loads(path.read_text(encoding="utf-8")) for path in tmp_path.glob("*.json")
        )
        if receipt["prompt_sha256"] == hashlib.sha256(repair_packet.encode()).hexdigest()
    )
    assert len(repair_packet) > 4096
    assert repair_receipt["attempts"][0]["query_text"] == submitted[1]


def test_repair_refuses_to_write_into_an_unrelated_chat(tmp_path, monkeypatch):
    class Page:
        url = "https://gemini.google.com/app/unrelated-chat"

    transport = BrowserTransport(
        Page(), "Pro", True, tmp_path, 600, attachment_mode="file"
    )
    prompt_sha256 = "a" * 64
    transport._last_prompt_sha256 = prompt_sha256
    transport._chat_ready = True
    receipt = transport._load_receipt(prompt_sha256)
    receipt["attempts"].append(
        {
            "state": "rejected",
            "chat_url": "https://gemini.google.com/app/rejected-chat",
        }
    )
    transport._save_receipt(receipt)
    calls = []
    monkeypatch.setattr(
        transport,
        "_request",
        lambda prompt, *, use_file: calls.append((prompt, use_file)) or "fresh",
    )

    result = transport.repair_json("original", "error", "base", "latest", "{}")

    assert result == "fresh"
    assert calls == [("original", True)]
    assert transport._chat_ready is False


def test_submission_is_journaled_before_uncertain_send_failure(tmp_path, monkeypatch):
    from youtube_automation.browser import gemini_utils

    class Locator:
        def count(self):
            return 0

    class Page:
        url = "https://gemini.google.com/app/journal-chat"

        def locator(self, _selector):
            return Locator()

    class Client:
        def __init__(self, _page, _model):
            pass

        def dispatch_prompt(self, _prompt):
            raise RuntimeError("renderer closed after send boundary")

    monkeypatch.setattr(gemini_utils, "GeminiSessionClient", Client)
    monkeypatch.setattr(gemini_utils, "start_clean_gemini_chat", lambda _page: None)
    monkeypatch.setattr(gemini_utils, "select_gemini_model", lambda _page, _model: True)
    transport = BrowserTransport(Page(), "Flash", True, tmp_path, 600)

    with pytest.raises(RuntimeError, match="renderer closed"):
        transport("journal me")

    receipt = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    attempt = receipt["attempts"][0]
    assert attempt["state"] == "submission_uncertain"
    assert attempt["initial_response_count"] == 0
    assert attempt["chat_url"] == Page.url
    assert transport._chat_ready is False


def test_attachment_ready_wait_requires_stable_non_busy_samples(tmp_path):
    states = [
        {"mounted": True, "busy": True},
        {"mounted": True, "busy": False},
        {"mounted": True, "busy": True},
        {"mounted": True, "busy": False},
        {"mounted": True, "busy": False},
        {"mounted": True, "busy": False},
        {"mounted": True, "busy": False},
    ]

    class Page:
        def __init__(self):
            self.waits = []
            self.expressions = []

        def evaluate(self, expression, filename):
            self.expressions.append((expression, filename))
            return states.pop(0)

        def wait_for_timeout(self, milliseconds):
            self.waits.append(milliseconds)

    page = Page()
    transport = BrowserTransport(page, "Flash", timeout_seconds=30)
    attachment = tmp_path / "planner-request.txt"

    transport._wait_for_attachment_ready(attachment)

    assert len(page.expressions) == 7
    assert page.waits == [250] * 6
    expression, filename = page.expressions[0]
    assert filename == attachment.name
    assert '[role="progressbar"]' in expression
    assert '[aria-busy="true"]' in expression
    assert "upload-spinner" in expression
    assert "composer.querySelectorAll('[aria-describedby]')" in expression
    assert "document.querySelectorAll('[aria-describedby]')" not in expression


def test_page_ready_wait_requires_complete_stable_unblocked_surface():
    states = [
        {
            "document_complete": False,
            "composer": True,
            "navigation": True,
            "blocking_busy": True,
        },
        {
            "document_complete": True,
            "composer": True,
            "navigation": True,
            "blocking_busy": False,
        },
    ]
    counts = iter([(0, 0), (0, 0), (0, 0), (0, 0), (0, 0), (0, 0)])

    class Locator:
        def __init__(self, page, index):
            self.page = page
            self.index = index

        def count(self):
            if self.index == 0:
                self.page.current_counts = next(counts)
            return self.page.current_counts[self.index]

    class Page:
        url = "https://gemini.google.com/app"

        def __init__(self):
            self.current_counts = (0, 0)
            self.waits = []
            self.polls = 0

        def evaluate(self, expression):
            assert 'document.readyState === \'complete\'' in expression
            state = states[min(self.polls, len(states) - 1)]
            self.polls += 1
            return state

        def locator(self, selector):
            from youtube_automation.browser.gemini_utils import RESPONSE_SELECTOR

            return Locator(self, 0 if selector == RESPONSE_SELECTOR else 1)

        def wait_for_timeout(self, milliseconds):
            self.waits.append(milliseconds)

    page = Page()
    BrowserTransport(page, "Flash", timeout_seconds=30)._wait_for_page_ready()

    assert page.polls == 5
    assert page.waits == [500] * 4


def test_attachment_ready_wait_times_out_before_dispatch(tmp_path, monkeypatch):
    class Page:
        def evaluate(self, _expression, _filename):
            return {"mounted": True, "busy": True}

        def wait_for_timeout(self, _milliseconds):
            pass

    ticks = iter([0.0, 31.0])
    monkeypatch.setattr(
        "youtube_automation.production.briefs.time.monotonic", lambda: next(ticks)
    )
    transport = BrowserTransport(Page(), "Flash", timeout_seconds=30)

    with pytest.raises(RuntimeError, match="did not finish uploading"):
        transport._wait_for_attachment_ready(tmp_path / "planner-request.txt")


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


def test_file_recovery_reads_response_paired_to_exact_user_turn(tmp_path, monkeypatch):
    from youtube_automation.browser import gemini_utils

    expected_query = "Read attached request. Request ID: ABCD2345"

    class Item:
        def __init__(self, text):
            self.text = text

        def evaluate(self, _expression, timeout):
            assert timeout == 4000
            return self.text

    class Items:
        def __init__(self, values):
            self.values = values

        def count(self):
            return len(self.values)

        def nth(self, index):
            return Item(self.values[index])

    class Page:
        url = "https://gemini.google.com/app/exact-turn"

        def locator(self, selector):
            if selector == gemini_utils.USER_QUERY_SELECTOR:
                return Items([expected_query, "later unrelated request"])
            return Items(["Gemini said\n" + response(), "Gemini said\nwrong later reply"])

        def wait_for_selector(self, _selector, timeout):
            assert timeout == 15000

    monkeypatch.setattr(
        gemini_utils,
        "wait_for_gemini_response",
        lambda *_args, **_kwargs: "wrong later reply",
    )
    payload = {
        "version": 2,
        "prompt_sha256": "a" * 64,
        "model": "Flash",
        "transport": "file",
        "window": [0, 575],
        "attempts": [
            {
                "state": "timed_out",
                "chat_url": Page.url,
                "initial_response_count": 0,
                "user_query_index": 0,
                "query_text": expected_query,
            }
        ],
    }
    transport = BrowserTransport(
        Page(), "Flash", True, tmp_path, 600, attachment_mode="file"
    )

    recovered = transport._recover_late_response(payload)

    assert json.loads(recovered)["proposition"] == "Animal perception"
    assert payload["attempts"][0]["response"] == response()


def test_file_recovery_rejects_wrong_user_turn_and_recovered_refusal(tmp_path, monkeypatch):
    from youtube_automation.browser import gemini_utils

    class Item:
        def __init__(self, text):
            self.text = text

        def evaluate(self, _expression, timeout):
            assert timeout == 4000
            return self.text

    class Items:
        def __init__(self, values):
            self.values = values

        def count(self):
            return len(self.values)

        def nth(self, index):
            return Item(self.values[index])

    class Page:
        url = "https://gemini.google.com/app/refusal-recovery"

        def __init__(self, query):
            self.query = query

        def locator(self, selector):
            if selector == gemini_utils.USER_QUERY_SELECTOR:
                return Items([self.query])
            return Items(["I encountered an error doing what you asked. Could you try again?"])

        def wait_for_selector(self, _selector, timeout):
            assert timeout == 15000

    monkeypatch.setattr(
        gemini_utils,
        "wait_for_gemini_response",
        lambda *_args, **_kwargs: "I encountered an error doing what you asked.",
    )

    def payload():
        return {
            "version": 2,
            "prompt_sha256": "b" * 64,
            "model": "Flash",
            "transport": "file",
            "window": [0, 575],
            "attempts": [
                {
                    "state": "timed_out",
                    "chat_url": Page.url,
                    "initial_response_count": 0,
                    "user_query_index": 0,
                    "query_text": "Request ID: RIGHT123",
                }
            ],
        }

    wrong = payload()
    assert (
        BrowserTransport(
            Page("Request ID: WRONG999"),
            "Flash",
            True,
            tmp_path,
            600,
            attachment_mode="file",
        )._recover_late_response(wrong)
        is None
    )

    refused = payload()
    transport = BrowserTransport(
        Page("Request ID: RIGHT123"),
        "Flash",
        True,
        tmp_path,
        600,
        attachment_mode="file",
    )
    assert transport._recover_late_response(refused) is None
    assert refused["attempts"][0]["state"] == "provider_refusal"
    assert transport._chat_ready is False


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


def test_transport_binds_conversation_url_and_persists_keyboard_interrupt(
    tmp_path, monkeypatch
):
    from youtube_automation.browser import gemini_utils

    class Page:
        def __init__(self):
            self.url = "https://gemini.google.com/app"
            self.waits = []

        def wait_for_timeout(self, timeout_ms):
            self.waits.append(timeout_ms)
            self.url = "https://gemini.google.com/app/bound-professor-chat"

    class Client:
        def __init__(self, _page, _model):
            pass

        def dispatch_prompt(self, _prompt):
            return True, 0

    page = Page()
    monkeypatch.setattr(gemini_utils, "GeminiSessionClient", Client)
    monkeypatch.setattr(gemini_utils, "start_clean_gemini_chat", lambda _page: None)
    monkeypatch.setattr(gemini_utils, "select_gemini_model", lambda _page, _model: True)

    def interrupt(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(gemini_utils, "wait_for_gemini_response", interrupt)
    transport = BrowserTransport(page, "Pro", True, tmp_path, 600)
    transport.begin_window(0, 575)

    with pytest.raises(KeyboardInterrupt):
        transport("interrupted bound prompt")

    receipt = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    attempt = receipt["attempts"][0]
    assert page.waits
    assert attempt["state"] == "interrupted"
    assert attempt["chat_url"] == "https://gemini.google.com/app/bound-professor-chat"
    assert attempt["transient_url"] is None


def test_profiles_change_writing_without_changing_source(channel):
    first = analyze_script("Animal perception", channel, lambda _: response())
    other = channel.model_copy(
        update={"channel_id": "comedy", "tone": "playful", "humor": "central"}
    )
    second = analyze_script("Animal perception", other, lambda _: response())
    assert first.source_sha256 == second.source_sha256
    assert first.profile_sha256 != second.profile_sha256
    assert writing_prompt(first, "refine") != writing_prompt(second, "refine")


def test_visual_policy_rebind_preserves_verified_writing_and_analysis(tmp_path, channel):
    from youtube_automation.production.writing import verify_written_episode

    raw = "Animal perception"
    (tmp_path / "raw_transcript.txt").write_text(raw, encoding="utf-8")
    existing = ensure_brief(tmp_path, channel, lambda _: response())
    outputs = {
        "breaked_paragraphs.txt": raw,
        "final_output.txt": raw,
        "refined_script.txt": raw,
    }
    for name, text in outputs.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    (tmp_path / "adaptive_writing_receipt.json").write_text(
        json.dumps(
            {
                "version": 1,
                "brief_sha256": narration_fingerprint(existing),
                "outputs": {name: fingerprint(text) for name, text in outputs.items()},
            }
        ),
        encoding="utf-8",
    )
    upgraded = channel.model_copy(
        update={
            "version": 2,
            "visual_directives": ["Use observable human contexts"],
            "forbidden_motifs": ["glowing brain"],
            "forbidden_visual_families": ["mechanical_cognition"],
            "repetition_limited_visual_families": ["generic_desk_task"],
            "max_visual_family_repetitions": 2,
        }
    )

    assert is_visual_policy_update(tmp_path, upgraded)
    rebound = rebind_visual_policy(tmp_path, upgraded)
    assert rebound.analysis == existing.analysis
    assert rebound.channel == upgraded
    assert narration_fingerprint(rebound) == narration_fingerprint(existing)
    assert verify_written_episode(tmp_path)


def test_visual_policy_rebind_rejects_identity_or_voice_change(tmp_path, channel):
    (tmp_path / "raw_transcript.txt").write_text("Animal perception", encoding="utf-8")
    ensure_brief(tmp_path, channel, lambda _: response())
    changed = channel.model_copy(update={"voice": "different-voice"})
    assert not is_visual_policy_update(tmp_path, changed)
    with pytest.raises(ValueError, match="not limited"):
        rebind_visual_policy(tmp_path, changed)
