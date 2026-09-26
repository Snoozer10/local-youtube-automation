import hashlib
import json

import pytest

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
    receipt = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert receipt["version"] == 2
    assert receipt["transport"] == "file"
    assert receipt["attempts"][0]["attachment"] == attached[0].name


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
