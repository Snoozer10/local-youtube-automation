import json

import pytest

from youtube_automation.production.briefs import ensure_brief
from youtube_automation.production.contracts import Channel, fingerprint
from youtube_automation.production.writing import verify_written_episode, write_episode


def test_channel_writing_resume_and_tamper_detection(tmp_path):
    channel = Channel(
        channel_id="history",
        name="History",
        audience="adults",
        language="Arabic",
        dialect="MSA",
        voice="voice",
        tone="serious",
        style="illustration",
        humor="none",
        allowed_treatments=["subject_scene"],
    )
    (tmp_path / "raw_transcript.txt").write_text("A historical journey.", encoding="utf-8")
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
    calls = []

    def ask(prompt):
        calls.append(prompt)
        if '"paragraphs"' in prompt:
            return json.dumps({"paragraphs": ["A historical journey."]})
        return json.dumps({"text": "رحلة تاريخية محفوظة المعنى."})

    write_episode(tmp_path, brief, ask)
    assert len(calls) == 3
    assert all('"humor":"none"' in p for p in calls)
    assert verify_written_episode(tmp_path)
    write_episode(tmp_path, brief, lambda _: pytest.fail("Do not repeat validated turns"))
    (tmp_path / "refined_script.txt").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="output changed"):
        verify_written_episode(tmp_path)


def test_failed_writing_never_publishes_partial_episode(tmp_path):
    channel = Channel(
        channel_id="one",
        name="One",
        audience="adults",
        language="Arabic",
        dialect="MSA",
        voice="voice",
        tone="calm",
        style="illustration",
        allowed_treatments=["subject_scene"],
    )
    (tmp_path / "raw_transcript.txt").write_text("A topic", encoding="utf-8")
    analysis = {
        "topics": ["topic"],
        "claim_basis": "factual",
        "form": "explanation",
        "proposition": "Topic",
        "narrative_strategy": "Explain",
        "treatments": ["subject_scene"],
        "rationale": "Concrete",
    }
    brief = ensure_brief(tmp_path, channel, lambda _: json.dumps(analysis))
    with pytest.raises(RuntimeError):
        write_episode(tmp_path, brief, lambda _: (_ for _ in ()).throw(RuntimeError("offline")))
    assert not (tmp_path / "refined_script.txt").exists()
    assert not (tmp_path / "adaptive_writing_receipt.json").exists()


def test_valid_json_cache_tampering_is_detected(tmp_path):
    from youtube_automation.production.writing import WrittenParagraph, _cached_response

    _cached_response(tmp_path, "prompt", lambda _: '{"text":"original"}', WrittenParagraph)
    cache = next(tmp_path.glob("*.json"))
    value = json.loads(cache.read_text())
    value["response"]["text"] = "Different but schema-valid content"
    cache.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="cache content mismatch"):
        _cached_response(
            tmp_path,
            "prompt",
            lambda _: pytest.fail("Must reject corrupted cache"),
            WrittenParagraph,
        )


def test_interrupted_writing_publication_recovers_without_browser(tmp_path, monkeypatch):
    from youtube_automation.production import writing

    channel = Channel(
        channel_id="one",
        name="One",
        audience="adults",
        language="Arabic",
        dialect="MSA",
        voice="voice",
        tone="calm",
        style="illustration",
        allowed_treatments=["subject_scene"],
    )
    (tmp_path / "raw_transcript.txt").write_text("A topic", encoding="utf-8")
    brief = ensure_brief(
        tmp_path,
        channel,
        lambda _: json.dumps(
            {
                "topics": ["topic"],
                "claim_basis": "factual",
                "form": "explanation",
                "proposition": "Topic",
                "narrative_strategy": "Explain",
                "treatments": ["subject_scene"],
                "rationale": "Concrete",
            }
        ),
    )
    answers = iter(
        [
            json.dumps({"paragraphs": ["source"]}),
            json.dumps({"text": "translated"}),
            json.dumps({"text": "refined"}),
        ]
    )
    real_atomic_text = writing.atomic_text
    writes = []

    def fail_mid_publication(path, text):
        writes.append(path.name)
        if len(writes) == 2:
            raise OSError("injected process death")
        real_atomic_text(path, text)

    monkeypatch.setattr(writing, "atomic_text", fail_mid_publication)
    with pytest.raises(OSError, match="injected process death"):
        write_episode(tmp_path, brief, lambda _: next(answers))
    assert (tmp_path / ".publication_journal" / "writing.json").is_file()
    assert not (tmp_path / "adaptive_writing_receipt.json").exists()

    monkeypatch.setattr(writing, "atomic_text", real_atomic_text)
    receipt = write_episode(
        tmp_path,
        brief,
        lambda _: pytest.fail("Recovery must not revisit the browser"),
    )
    assert receipt["brief_sha256"] == fingerprint(brief)
    assert verify_written_episode(tmp_path)
    assert not (tmp_path / ".publication_journal" / "writing.json").exists()
