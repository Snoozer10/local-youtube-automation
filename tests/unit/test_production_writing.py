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


def _writing_brief(tmp_path, transcript="A historical journey."):
    channel = Channel(
        channel_id="writing-test",
        name="Writing Test",
        audience="adults",
        language="Arabic",
        dialect="MSA",
        voice="voice",
        tone="serious",
        style="illustration",
        humor="none",
        allowed_treatments=["subject_scene"],
    )
    (tmp_path / "raw_transcript.txt").write_text(transcript, encoding="utf-8")
    analysis = {
        "topics": ["history"],
        "claim_basis": "factual",
        "form": "chronology",
        "proposition": "A journey",
        "narrative_strategy": "Follow events",
        "treatments": ["subject_scene"],
        "rationale": "Chronology",
    }
    return ensure_brief(tmp_path, channel, lambda _: json.dumps(analysis))


def test_tagged_refinements_extract_only_for_publication_and_replay_from_cache(tmp_path):
    brief = _writing_brief(tmp_path)
    calls = []

    class Ask:
        model_name = "Flash"

        def __call__(self, prompt: str) -> str:
            calls.append(prompt)
            if len(calls) == 1:
                return json.dumps({"paragraphs": ["First.", "Second."]})
            if len(calls) in {3, 5}:
                return json.dumps({"text": f"<final_script>مصقول {len(calls)}</final_script>"})
            return json.dumps({"text": f"مترجم {len(calls)}"})

    ask = Ask()
    write_episode(tmp_path, brief, ask)

    raw_previous = "<final_script>مصقول 3</final_script>"
    assert raw_previous in calls[4]
    assert (tmp_path / "refined_script.txt").read_text(encoding="utf-8") == (
        "مصقول 3\n\nمصقول 5"
    )
    assert verify_written_episode(tmp_path)
    cache_dir = tmp_path / "adaptive_writing"
    cache_before = {path.name: path.read_bytes() for path in cache_dir.glob("*.json")}
    assert len(cache_before) == 5
    cached_responses = [
        json.loads(path.read_text(encoding="utf-8"))["response"]
        for path in cache_dir.glob("*.json")
    ]
    assert any(response.get("text") == raw_previous for response in cached_responses)

    class NeverAsk:
        model_name = "Flash"

        def __call__(self, _prompt: str) -> str:
            raise AssertionError("Cached reassembly must not request another model response")

    never_ask = NeverAsk()
    write_episode(tmp_path, brief, never_ask)
    cache_after = {path.name: path.read_bytes() for path in cache_dir.glob("*.json")}
    assert cache_after == cache_before
    assert (tmp_path / "refined_script.txt").read_text(encoding="utf-8") == (
        "مصقول 3\n\nمصقول 5"
    )


@pytest.mark.parametrize(
    "bad_wrapper",
    [
        "<final_script>one</final_script><final_script>two</final_script>",
        "<final_script>unclosed",
        "<final_script>  </final_script>",
        "<final_script>outer <final_script>inner</final_script></final_script>",
    ],
    ids=["multiple", "malformed", "empty", "nested"],
)
def test_invalid_final_script_wrappers_never_publish(tmp_path, bad_wrapper):
    from youtube_automation.production import writing

    brief = _writing_brief(tmp_path, transcript="One sentence.")
    calls = 0

    def ask(_prompt):
        nonlocal calls
        calls += 1
        if calls == 1:
            return json.dumps({"paragraphs": ["One sentence."]})
        if calls == 3:
            return json.dumps({"text": bad_wrapper})
        return json.dumps({"text": "translated"})

    with pytest.raises(ValueError, match="final_script"):
        write_episode(tmp_path, brief, ask)
    assert not (tmp_path / "refined_script.txt").exists()
    assert not (tmp_path / "adaptive_writing_receipt.json").exists()
    assert not writing._journal_path(tmp_path).exists()


def test_verify_rejects_tagged_refined_script_with_matching_receipt(tmp_path):
    from youtube_automation.production.contracts import narration_fingerprint

    brief = _writing_brief(tmp_path)
    outputs = {
        "breaked_paragraphs.txt": "Source paragraph.",
        "final_output.txt": "Translated paragraph.",
        "refined_script.txt": "<final_script>Tagged paragraph.</final_script>",
    }
    for name, text in outputs.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    receipt = {
        "version": 1,
        "brief_sha256": narration_fingerprint(brief),
        "outputs": {name: fingerprint(text) for name, text in outputs.items()},
    }
    (tmp_path / "adaptive_writing_receipt.json").write_text(
        json.dumps(receipt), encoding="utf-8"
    )

    with pytest.raises(ValueError, match=r"<final_script> markup"):
        verify_written_episode(tmp_path)


def test_pending_tagged_writing_journal_is_not_reactivated(tmp_path):
    from youtube_automation.production import writing
    from youtube_automation.production.contracts import narration_fingerprint

    brief = _writing_brief(tmp_path)
    outputs = {
        "breaked_paragraphs.txt": "Source paragraph.",
        "final_output.txt": "Translated paragraph.",
        "refined_script.txt": (
            "<final_script>First.</final_script>\n\n"
            "<final_script>Second.</final_script>"
        ),
    }
    receipt = {
        "version": 1,
        "brief_sha256": narration_fingerprint(brief),
        "outputs": {name: fingerprint(text) for name, text in outputs.items()},
    }
    journal = writing._journal_path(tmp_path)
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text(
        json.dumps({"version": 1, "kind": "writing", "outputs": outputs, "receipt": receipt}),
        encoding="utf-8",
    )

    assert writing._recover_pending_writing(tmp_path, brief) is None
    assert journal.is_file()
    assert not (tmp_path / "refined_script.txt").exists()
    assert not (tmp_path / "adaptive_writing_receipt.json").exists()
