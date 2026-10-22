"""Offline direct-stage journal, exact narration identity and explicit human acceptance."""

import hashlib
import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from youtube_automation.production import cli
from youtube_automation.production import direction_stage as ds
from youtube_automation.production import voice_direction as vd
from youtube_automation.production.contracts import (
    Analysis,
    Brief,
    Channel,
    fingerprint,
    narration_fingerprint,
)
from youtube_automation.production.ledger import Ledger

SCRIPT = (
    "The patrol plane sighted a fleet of warships near the island.\n\n"
    "The escort carriers launched their aircraft and laid smoke to defend themselves.\n"
)


def _run(root, *, script=SCRIPT, source="A historical topic.", voice="Charon"):
    channel = Channel(
        channel_id="history", name="History", audience="adults", language="English",
        dialect="standard", voice=voice, tone="serious", style="illustration",
        humor="none", allowed_treatments=["subject_scene"],
    )
    brief = Brief(
        source_sha256=fingerprint(source), profile_sha256=fingerprint(channel), channel=channel,
        analysis=Analysis(topics=["history"], claim_basis="factual", form="chronology",
                          proposition="A historical topic", narrative_strategy="Follow events",
                          treatments=["subject_scene"], rationale="Chronology"),
    )
    (root / "raw_transcript.txt").write_bytes(source.encode("utf-8"))
    (root / "episode_brief.json").write_text(brief.model_dump_json(), encoding="utf-8")
    outputs = {}
    for name in ("breaked_paragraphs.txt", "final_output.txt", "refined_script.txt"):
        (root / name).write_bytes(script.encode("utf-8"))
        outputs[name] = fingerprint(script.replace("\r\n", "\n"))
    (root / "adaptive_writing_receipt.json").write_text(json.dumps({
        "brief_sha256": narration_fingerprint(brief), "outputs": outputs,
    }), encoding="utf-8")
    return brief


def _response(root, **overrides):
    identity = ds.direction_inputs(root)
    data = {key: identity[key] for key in ("channel_id", "voice", "model", "source_sha256", "script_sha256")}
    script = (root / "refined_script.txt").read_text(encoding="utf-8").strip()
    data.update(style="Measured documentary narrator, calm and restrained.",
                paragraphs=["<short pause> " + p for p in script.split("\n\n")])
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False, indent=2)


@pytest.fixture
def run(tmp_path, monkeypatch):
    monkeypatch.setenv("ADAPTIVE_TTS_MODEL", vd.FLASH_MODEL)
    monkeypatch.setattr(cli, "resource_database", lambda: tmp_path / "jobs.db")
    monkeypatch.setattr(cli, "gemini_transport", lambda **_: pytest.fail("No live Gemini requests"))
    _run(tmp_path)
    return tmp_path


def _candidate_hash(root):
    return hashlib.sha256((root / ds.CANDIDATE_FILE).read_bytes()).hexdigest()



def _seed_completed_transport_receipt(root, model="Flash"):
    prompt = ds.direction_prompt(root, generation_model=model)
    prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    receipt_dir = root / "direction_generation_receipts" / prompt_sha256
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_dir / f"{prompt_sha256}.json"
    response = _response(root)
    receipt_path.write_text(
        json.dumps(
            {
                "version": 1,
                "prompt_sha256": prompt_sha256,
                "model": model,
                "transport": "inline",
                "window": None,
                "attempts": [{"state": "completed", "response": response}],
            }
        ),
        encoding="utf-8",
    )
    return prompt, response, receipt_dir, receipt_path


def test_gemini_transport_is_a_context_manager_and_cleans_up_owned_page(monkeypatch):
    import sys
    from types import ModuleType

    events = []
    sends = []

    class Page:
        closed = False

        def goto(self, url, *, wait_until):
            events.append(("goto", url, wait_until))

        def close(self):
            self.closed = True
            events.append("page-close")

    page = Page()
    context = type("Context", (), {"new_page": lambda self: page})()
    browser = type("Browser", (), {"contexts": [context]})()
    playwright = type("Playwright", (), {
        "chromium": type("Chromium", (), {
            "connect_over_cdp": lambda self, url, *, timeout: browser,
        })(),
    })()

    @contextmanager
    def fake_sync_playwright():
        events.append("playwright-enter")
        try:
            yield playwright
        finally:
            events.append("playwright-exit")

    def fake_browser_ask(page_arg, model, **kwargs):
        assert page_arg is page
        assert model == "Pro"
        return lambda prompt: sends.append(prompt) or "unused"

    package = ModuleType("playwright")
    package.__path__ = []
    sync_api = ModuleType("playwright.sync_api")
    sync_api.sync_playwright = fake_sync_playwright
    monkeypatch.setitem(sys.modules, "playwright", package)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)
    monkeypatch.setattr(cli, "get_config_value", lambda name, default: default)
    monkeypatch.setattr(cli, "browser_ask", fake_browser_ask)

    transport = cli.gemini_transport(model_name="Pro")
    assert hasattr(transport, "__enter__")
    with transport as ask:
        assert callable(ask)
        assert not page.closed

    assert page.closed
    assert events == [
        "playwright-enter",
        ("goto", "https://gemini.google.com/app", "domcontentloaded"),
        "page-close",
        "playwright-exit",
    ]
    assert sends == []


def test_injected_transport_preserves_words_and_resumes_without_another_request(run):
    before = (run / "refined_script.txt").read_bytes()
    calls = []
    def ask(prompt):
        calls.append(prompt)
        return _response(run)
    candidate = ds.ensure_direction_candidate(run, ask)
    assert len(calls) == 1
    assert json.loads(calls[0])["narration"] == SCRIPT
    assert "approval" not in candidate
    assert not (run / vd.DIRECTION_FILE).exists()
    assert (run / "refined_script.txt").read_bytes() == before
    assert ds.ensure_direction_candidate(run, lambda _: pytest.fail("Do not repeat request")) == candidate
    assert ds.verify_direction_candidate(run) == candidate


def test_cli_direct_journals_candidate_and_accepts_only_explicit_exact_hash(run):
    response = run / "response.json"
    response.write_bytes(_response(run).encode("utf-8"))
    args = ["direct", "--run-dir", str(run), "--direction-response-file", str(response)]
    cli.main(args)
    candidate_before = (run / ds.CANDIDATE_FILE).read_bytes()
    row = Ledger(run / "jobs.db").get(cli._stage_key(run, "direct"))
    assert row["state"] == "SUCCEEDED"
    cli.main(args)
    assert (run / ds.CANDIDATE_FILE).read_bytes() == candidate_before
    assert not (run / vd.DIRECTION_FILE).exists()
    with pytest.raises(SystemExit):
        cli.main(["accept-direction", "--run-dir", str(run), "--reviewer", "owner",
                  "--direction-sha256", "0" * 64])
    assert not (run / vd.DIRECTION_FILE).exists()
    accept = ["accept-direction", "--run-dir", str(run), "--reviewer", "owner",
              "--direction-sha256", _candidate_hash(run)]
    cli.main(accept)
    raw = (run / vd.DIRECTION_FILE).read_bytes()
    assert vd.load_voice_direction(run, SCRIPT, channel_id="history") is not None
    cli.main(accept)
    assert (run / vd.DIRECTION_FILE).read_bytes() == raw


def test_tts_preparation_uses_approved_generated_direction(run):
    from youtube_automation.audio import tts_generator

    candidate = ds.ensure_direction_candidate(run, lambda _: _response(run))
    ds.accept_direction(
        run,
        reviewer="human owner",
        candidate_sha256=_candidate_hash(run),
    )
    brief = Brief.model_validate_json((run / "episode_brief.json").read_text(encoding="utf-8"))
    approved = vd.load_voice_direction(run, SCRIPT, channel_id="history")
    manifest = {
        "chapters": [
            {
                "chapter_num": 1,
                "text": SCRIPT,
                "status": "COMPLETED",
                "voice_model": vd.FLASH_MODEL,
                "voice_direction_sha256": approved.sha256,
            }
        ]
    }

    voice_config, direction, speech = tts_generator._prepare_adaptive_voice(
        str(run),
        manifest,
        brief,
        SCRIPT,
    )

    assert direction is not None
    assert direction.style == candidate["style"]
    assert voice_config["style"] == candidate["style"]
    assert voice_config["model"] == vd.FLASH_MODEL
    assert speech[1]


@pytest.mark.parametrize("output", ["I cannot help with that request.", "{broken", "{}", "[]", "null"])
def test_refusal_or_malformed_output_is_retained_and_never_published(run, output):
    with pytest.raises(vd.VoiceDirectionError):
        ds.ensure_direction_candidate(run, lambda _: output)
    assert not (run / ds.CANDIDATE_FILE).exists()
    assert not (run / vd.DIRECTION_FILE).exists()
    folder = next((run / "direction_attempts").iterdir())
    assert (folder / "response.txt").read_bytes() == output.encode("utf-8")
    assert json.loads((folder / "receipt.json").read_text())["state"] == "rejected"


@pytest.mark.parametrize("overrides", [
    {"channel_id": "other"}, {"voice": "Achird"}, {"model": vd.PRO_MODEL},
    {"source_sha256": "0" * 64}, {"script_sha256": "0" * 64},
    {"style": "   "}, {"style": "calm <sigh>"}, {"style": "x" * 601},
    {"paragraphs": ["Rewritten narration."]},
    {"paragraphs": ["The patrol plane sighted a fleet of battleships near the island.",
                    "The escort carriers launched their aircraft and laid smoke to defend themselves."]},
    {"paragraphs": ["<unknown> The patrol plane sighted a fleet of warships near the island.",
                    "The escort carriers launched their aircraft and laid smoke to defend themselves."]},
    {"approval": {"approved_by": "model", "statement": "APPROVED"}},
])
def test_identity_style_tags_and_word_changes_fail_closed(run, overrides):
    with pytest.raises(vd.VoiceDirectionError):
        ds.ensure_direction_candidate(run, lambda _: _response(run, **overrides))
    assert not (run / ds.CANDIDATE_FILE).exists()


def test_changed_source_archives_candidate_and_keeps_accepted_direction_and_takes(run):
    response = run / "response.json"
    response.write_bytes(_response(run).encode("utf-8"))
    args = ["direct", "--run-dir", str(run), "--direction-response-file", str(response)]
    cli.main(args)
    ds.accept_direction(run, reviewer="owner", candidate_sha256=_candidate_hash(run))
    accepted = (run / vd.DIRECTION_FILE).read_bytes()
    (run / "voice_chapters").mkdir()
    (run / "voice_chapters" / "take.wav").write_bytes(b"accepted audio bytes")
    prior = (run / ds.CANDIDATE_FILE).read_bytes()
    _run(run, source="A changed historical source.")
    response.write_bytes(_response(run).encode("utf-8"))
    cli.main(args)
    assert (run / vd.DIRECTION_FILE).read_bytes() == accepted
    assert (run / "voice_chapters" / "take.wav").read_bytes() == b"accepted audio bytes"
    archived = list((run / ".adaptive_history").rglob(ds.CANDIDATE_FILE))
    assert len(archived) == 1 and archived[0].read_bytes() == prior
    with pytest.raises(vd.VoiceDirectionError, match="accepted voice direction"):
        ds.accept_direction(run, reviewer="owner", candidate_sha256=_candidate_hash(run))


def test_changed_voice_invalidates_resume_and_changed_model_refuses_before_transport(run, monkeypatch):
    ds.ensure_direction_candidate(run, lambda _: _response(run))
    _run(run, voice="Achird")
    with pytest.raises(vd.VoiceDirectionError, match="stale"):
        ds.ensure_direction_candidate(run, lambda _: pytest.fail("No request for stale candidate"))
    monkeypatch.setenv("ADAPTIVE_TTS_MODEL", vd.PRO_MODEL)
    with pytest.raises(vd.VoiceDirectionError, match="must target"):
        ds.ensure_direction_candidate(run, lambda _: pytest.fail("Wrong model must not send"))


def test_null_voice_or_imported_narration_refuses_before_transport(run):
    _run(run, voice=None)
    with pytest.raises(vd.VoiceDirectionError, match="selected channel voice"):
        ds.ensure_direction_candidate(run, lambda _: pytest.fail("Null voice must not send"))
    _run(run)
    (run / "source_audio_receipt.json").write_text("{}")
    with pytest.raises(ValueError):
        ds.ensure_direction_candidate(run, lambda _: pytest.fail("Imported narration must not send"))


def test_candidate_tampering_and_unsafe_evidence_paths_block_acceptance(run):
    candidate = ds.ensure_direction_candidate(run, lambda _: _response(run))
    candidate["style"] = "Different valid style"
    (run / ds.CANDIDATE_FILE).write_text(json.dumps(candidate), encoding="utf-8")
    with pytest.raises(vd.VoiceDirectionError, match="differs"):
        ds.accept_direction(run, reviewer="owner", candidate_sha256=_candidate_hash(run))
    candidate["provenance"]["attempt"] = "../escape"
    (run / ds.CANDIDATE_FILE).write_text(json.dumps(candidate), encoding="utf-8")
    with pytest.raises(vd.VoiceDirectionError, match="attempt identity"):
        ds.verify_direction_candidate(run)
    assert not (run / vd.DIRECTION_FILE).exists()


def test_existing_take_and_manual_direction_are_never_overwritten(run):
    ds.ensure_direction_candidate(run, lambda _: _response(run))
    (run / "voice_chapters").mkdir()
    (run / "voice_chapters" / "take.wav").write_bytes(b"take")
    with pytest.raises(vd.VoiceDirectionError, match="Existing voice takes"):
        ds.accept_direction(run, reviewer="owner", candidate_sha256=_candidate_hash(run))
    manual = vd.build_direction(SCRIPT, channel_id="history", style="Manual direction",
                                paragraphs=SCRIPT.strip().split("\n\n"), approved_by="owner")
    (run / vd.DIRECTION_FILE).write_text(json.dumps(manual), encoding="utf-8")
    before = (run / vd.DIRECTION_FILE).read_bytes()
    with pytest.raises(vd.VoiceDirectionError, match="accepted voice direction"):
        ds.accept_direction(run, reviewer="owner", candidate_sha256=_candidate_hash(run))
    assert (run / vd.DIRECTION_FILE).read_bytes() == before
    with pytest.raises(vd.VoiceDirectionError, match="candidate provenance"):
        vd.load_voice_direction(run, SCRIPT, channel_id="history")


def test_cli_relative_response_and_no_default_provider_entry(run, monkeypatch):
    monkeypatch.chdir(run)
    Path("response.json").write_bytes(_response(run).encode("utf-8"))
    cli.main(["direct", "--run-dir", ".", "--direction-response-file", "response.json"])
    assert ds.verify_direction_candidate(run)
    with pytest.raises(SystemExit):
        cli.main(["direct", "--run-dir", "."])


def test_interrupted_candidate_publication_recovers_without_transport(run, monkeypatch):
    original = ds.atomic_write_json
    def interrupted(path, payload, **kwargs):
        if Path(path).name == ds.CANDIDATE_FILE:
            raise OSError("interrupted publication")
        return original(path, payload, **kwargs)
    monkeypatch.setattr(ds, "atomic_write_json", interrupted)
    with pytest.raises(OSError, match="interrupted"):
        ds.ensure_direction_candidate(run, lambda _: _response(run))
    assert (run / ds.PUBLICATION_FILE).is_file()
    monkeypatch.setattr(ds, "atomic_write_json", original)
    ds.ensure_direction_candidate(run, lambda _: pytest.fail("Recover exact response without sending"))
    assert ds.verify_direction_candidate(run)
    assert not (run / ds.PUBLICATION_FILE).exists()


def test_crlf_source_binding_and_exact_response_bytes(run):
    _run(run, script=SCRIPT.replace("\n", "\r\n"))
    response = _response(run).replace("\n", "\r\n")
    result = ds.ensure_direction_candidate(run, lambda _: response)
    folder = run / "direction_attempts" / result["provenance"]["attempt"]
    assert (folder / "response.txt").read_bytes() == response.encode("utf-8")
    assert ds.verify_direction_candidate(run) == result


def _install_browser_transport_mock(run, monkeypatch, *, response=None):
    from types import SimpleNamespace

    from youtube_automation.browser import gemini_utils
    from youtube_automation.production.briefs import BrowserTransport

    monkeypatch.setenv("IMAGE_PLANNER_MODEL", "Flash")
    monkeypatch.setattr(BrowserTransport, "_network_gate", lambda _self: None)
    monkeypatch.setattr(BrowserTransport, "_locator_count", lambda _self, _selector: 0)
    monkeypatch.setattr(BrowserTransport, "_optional_locator_count", lambda _self, _selector: 1)
    chat_url = "https://gemini.google.com/app/direction-test"
    monkeypatch.setattr(BrowserTransport, "_wait_for_bound_chat_url", lambda _self, **_kw: chat_url)
    monkeypatch.setattr(gemini_utils, "start_clean_gemini_chat", lambda _page: None)
    selected = []
    monkeypatch.setattr(gemini_utils, "select_gemini_model", lambda _page, model: selected.append(model) or True)
    monkeypatch.setattr(gemini_utils, "get_gemini_usage_limit_text", lambda _page: None)
    response = _response(run) if response is None else response
    monkeypatch.setattr(gemini_utils, "wait_for_gemini_response", lambda *_args, **_kw: response)
    transports = []
    requests = []

    def dispatch(_client, prompt):
        requests.append(prompt)
        assert json.loads(prompt)["generation_model"] == "Flash"
        prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        receipt_dir = run / "direction_generation_receipts" / prompt_sha256
        assert transports[-1] == ("Flash", receipt_dir)
        before_send = json.loads((receipt_dir / f"{prompt_sha256}.json").read_text())
        assert before_send["model"] == "Flash"
        assert before_send["attempts"][-1]["state"] == "submission_pending"
        return True, 0

    monkeypatch.setattr(gemini_utils.GeminiSessionClient, "dispatch_prompt", dispatch)

    @contextmanager
    def fake_transport(*, model_name=None, receipt_dir=None, **_kwargs):
        transports.append((model_name, receipt_dir))
        yield BrowserTransport(SimpleNamespace(url=chat_url), model_name, receipt_dir=receipt_dir)

    monkeypatch.setattr(cli, "gemini_transport", fake_transport)
    return response, selected, transports, requests


def test_cli_generate_direction_uses_bound_model_and_resumes_without_another_request(
    run, monkeypatch
):
    response, selected, transports, requests = _install_browser_transport_mock(run, monkeypatch)
    args = ["generate-direction", "--run-dir", str(run)]
    cli.main(args)

    candidate = ds.verify_direction_candidate(run)
    assert selected == ["Flash"]
    assert len(transports) == 1
    assert len(requests) == 1
    assert candidate["provenance"]["generation_model"] == "Flash"
    assert "approval" not in candidate
    assert not (run / vd.DIRECTION_FILE).exists()
    receipt_path = run / candidate["provenance"]["transport_receipt_path"]
    receipt = json.loads(receipt_path.read_text())
    assert receipt["attempts"][-1]["state"] == "completed"
    assert receipt["attempts"][-1]["response"] == response
    assert candidate["provenance"]["transport_receipt_sha256"] == hashlib.sha256(
        receipt_path.read_bytes()
    ).hexdigest()

    cli.main(args)
    assert len(transports) == 1
    assert len(requests) == 1
    assert Ledger(run / "jobs.db").get(cli._stage_key(run, "generate-direction"))["state"] == "SUCCEEDED"


@pytest.mark.parametrize(
    "blocked_path",
    [
        vd.DIRECTION_FILE,
        "voice_generation_manifest.json",
        "audio_manifest.json",
        "full_episode_voice.wav",
        "voice_chapters/Chapter_1.wav",
        "polished_chapters/Chapter_1.wav",
        "audacity_voice/Chapter_1.wav",
    ],
)
def test_cli_generate_direction_blocks_imports_and_audio_before_transport(run, blocked_path):
    target = run / blocked_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"existing protected artifact")
    before = target.read_bytes()

    with pytest.raises(SystemExit):
        cli.main(["generate-direction", "--run-dir", str(run)])

    assert not (run / "direction_attempts").exists()
    assert not (run / ds.CANDIDATE_FILE).exists()
    assert target.read_bytes() == before


def test_cli_generate_direction_retains_refusal_without_retry_or_candidate(run, monkeypatch):
    refusal = "I cannot help with that request."
    _response_text, _selected, transports, calls = _install_browser_transport_mock(
        run, monkeypatch, response=refusal
    )
    args = ["generate-direction", "--run-dir", str(run)]
    with pytest.raises(RuntimeError, match="provider soft refusal"):
        cli.main(args)

    assert len(calls) == 1
    assert not (run / ds.CANDIDATE_FILE).exists()
    attempt = next((run / "direction_attempts").iterdir())
    assert json.loads((attempt / "receipt.json").read_text())["state"] == "rejected"
    receipt_path = next((run / "direction_generation_receipts").glob("*/*.json"))
    transport_receipt = json.loads(receipt_path.read_text())
    assert transport_receipt["attempts"][-1]["state"] == "provider_refusal"
    assert transport_receipt["attempts"][-1]["response"] == refusal
    receipt_before = receipt_path.read_bytes()
    with pytest.raises(SystemExit):
        cli.main(args)
    assert len(calls) == 1
    assert len(transports) == 1
    assert receipt_path.read_bytes() == receipt_before
    assert len(list((run / "direction_attempts").iterdir())) == 1

def test_generate_direction_preserves_legacy_offline_pending_without_sending(run, monkeypatch):
    offline_candidate = ds.ensure_direction_candidate(run, lambda _: _response(run))
    candidate_path = run / ds.CANDIDATE_FILE
    pending_path = run / ds.PUBLICATION_FILE
    pending_path.write_bytes(candidate_path.read_bytes())
    candidate_path.unlink()
    pending_before = pending_path.read_bytes()
    attempt_count = len(list((run / "direction_attempts").iterdir()))

    monkeypatch.setenv("IMAGE_PLANNER_MODEL", "Flash")
    with pytest.raises(SystemExit):
        cli.main(["generate-direction", "--run-dir", str(run)])

    assert pending_path.read_bytes() == pending_before
    assert not candidate_path.exists()
    assert len(list((run / "direction_attempts").iterdir())) == attempt_count
    assert "generation_model" not in offline_candidate["provenance"]


def test_generate_direction_rejects_pending_candidate_from_another_model(run, monkeypatch):
    monkeypatch.setenv("IMAGE_PLANNER_MODEL", "Pro")
    _prompt, response, _receipt_dir, receipt_path = _seed_completed_transport_receipt(run, "Pro")
    ds.ensure_direction_candidate(
        run,
        lambda _prompt: response,
        generation_model="Pro",
        transport_receipt_path=receipt_path,
    )
    candidate_path = run / ds.CANDIDATE_FILE
    pending_path = run / ds.PUBLICATION_FILE
    pending_path.write_bytes(candidate_path.read_bytes())
    candidate_path.unlink()
    pending_before = pending_path.read_bytes()

    monkeypatch.setenv("IMAGE_PLANNER_MODEL", "Flash")
    with pytest.raises(SystemExit):
        cli.main(["generate-direction", "--run-dir", str(run)])

    assert pending_path.read_bytes() == pending_before
    assert not candidate_path.exists()


def test_generate_direction_recovers_same_model_pending_without_transport(run, monkeypatch):
    monkeypatch.setenv("IMAGE_PLANNER_MODEL", "Flash")
    _prompt, response, _receipt_dir, receipt_path = _seed_completed_transport_receipt(run, "Flash")
    expected = ds.ensure_direction_candidate(
        run,
        lambda _prompt: response,
        generation_model="Flash",
        transport_receipt_path=receipt_path,
    )
    candidate_path = run / ds.CANDIDATE_FILE
    pending_path = run / ds.PUBLICATION_FILE
    pending_path.write_bytes(candidate_path.read_bytes())
    candidate_path.unlink()
    receipt_before = receipt_path.read_bytes()

    cli.main(["generate-direction", "--run-dir", str(run)])

    assert ds.verify_direction_candidate(run) == expected
    assert not pending_path.exists()
    assert receipt_path.read_bytes() == receipt_before


def test_generate_direction_blocks_unresolved_transport_receipt_before_browser(run, monkeypatch):
    monkeypatch.setenv("IMAGE_PLANNER_MODEL", "Flash")
    prompt = ds.direction_prompt(run, generation_model="Flash")
    prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    receipt_dir = run / "direction_generation_receipts" / prompt_sha256
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_dir / f"{prompt_sha256}.json"
    receipt_path.write_text(
        json.dumps(
            {
                "version": 1,
                "prompt_sha256": prompt_sha256,
                "model": "Flash",
                "transport": "inline",
                "window": None,
                "attempts": [{"state": "submission_uncertain", "chat_url": "https://gemini.google.com/app/old"}],
            }
        ),
        encoding="utf-8",
    )
    receipt_before = receipt_path.read_bytes()

    with pytest.raises(SystemExit):
        cli.main(["generate-direction", "--run-dir", str(run)])

    assert receipt_path.read_bytes() == receipt_before
    assert not (run / ds.CANDIDATE_FILE).exists()
    assert not (run / "direction_attempts").exists()


def test_generate_direction_reuses_current_transport_completion_without_a_new_send(
    run, monkeypatch
):
    from youtube_automation.production.briefs import BrowserTransport

    monkeypatch.setenv("IMAGE_PLANNER_MODEL", "Flash")
    _prompt, response, receipt_dir, receipt_path = _seed_completed_transport_receipt(run, "Flash")
    receipt_before = receipt_path.read_bytes()
    monkeypatch.setattr(BrowserTransport, "_network_gate", lambda _self: None)
    transports = []

    @contextmanager
    def fake_transport(*, model_name=None, receipt_dir=None, **_kwargs):
        transports.append((model_name, receipt_dir))
        yield BrowserTransport(object(), model_name, receipt_dir=receipt_dir)

    monkeypatch.setattr(cli, "gemini_transport", fake_transport)
    cli.main(["generate-direction", "--run-dir", str(run)])

    candidate = ds.verify_direction_candidate(run)
    assert candidate["provenance"]["response_sha256"] == hashlib.sha256(
        response.encode("utf-8")
    ).hexdigest()
    assert transports == [("Flash", receipt_dir)]
    assert receipt_path.read_bytes() == receipt_before


@pytest.mark.parametrize("relative", [False, True])
def test_automated_direction_rejects_external_receipt_before_ask(run, relative):
    _prompt, response, _receipt_dir, receipt_path = _seed_completed_transport_receipt(run)
    outside = run.parent / f"{run.name}-outside-receipt.json"
    outside.write_bytes(receipt_path.read_bytes())
    supplied = Path("..") / outside.name if relative else outside
    calls = []
    with pytest.raises(vd.VoiceDirectionError, match="escapes"):
        ds.ensure_direction_candidate(
            run,
            lambda prompt: calls.append(prompt) or response,
            generation_model="Flash",
            transport_receipt_path=supplied,
        )
    assert calls == []
    assert not (run / "direction_attempts").exists()
    assert not (run / ds.CANDIDATE_FILE).exists()


def _directory_alias(link, target):
    import sys

    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        link.symlink_to(target, target_is_directory=True)


def test_automated_direction_rejects_directory_alias_escape_before_ask(run):
    _prompt, response, _receipt_dir, receipt_path = _seed_completed_transport_receipt(run)
    outside = run.parent / f"{run.name}-outside"
    outside.mkdir()
    (outside / "receipt.json").write_bytes(receipt_path.read_bytes())
    alias = run / "receipt_alias"
    _directory_alias(alias, outside)
    assert (alias / "receipt.json").resolve() == (outside / "receipt.json").resolve()
    calls = []
    with pytest.raises(vd.VoiceDirectionError, match="escapes"):
        ds.ensure_direction_candidate(
            run,
            lambda prompt: calls.append(prompt) or response,
            generation_model="Flash",
            transport_receipt_path=alias / "receipt.json",
        )
    assert calls == []
    assert not (run / "direction_attempts").exists()
    assert not (run / ds.CANDIDATE_FILE).exists()


def test_generate_direction_rejects_receipt_directory_alias_before_transport(run, monkeypatch):
    monkeypatch.setenv("IMAGE_PLANNER_MODEL", "Flash")
    outside = run.parent / f"{run.name}-outside"
    outside.mkdir()
    _directory_alias(run / "direction_generation_receipts", outside)
    with pytest.raises(SystemExit):
        cli.main(["generate-direction", "--run-dir", str(run)])
    assert list(outside.iterdir()) == []
    assert not (run / "direction_attempts").exists()
    assert not (run / ds.CANDIDATE_FILE).exists()


def test_automated_direction_missing_transport_receipt_raises_domain_error(run):
    missing = run / "missing-transport.json"
    response = _response(run)
    with pytest.raises(vd.VoiceDirectionError, match="receipt is unreadable"):
        ds.ensure_direction_candidate(
            run,
            lambda _prompt: response,
            generation_model="Flash",
            transport_receipt_path=missing,
        )
    attempt = next((run / "direction_attempts").iterdir())
    assert (attempt / "response.txt").read_text() == response
    assert json.loads((attempt / "receipt.json").read_text())["state"] == "rejected"
    assert not (run / ds.CANDIDATE_FILE).exists()

def _accept_generated_direction(run):
    ds.ensure_direction_candidate(run, lambda _: _response(run))
    ds.accept_direction(
        run,
        reviewer="human owner",
        candidate_sha256=_candidate_hash(run),
    )
    return run / vd.DIRECTION_FILE


def test_accepted_generated_direction_rejects_changed_style_after_approval(run):
    accepted_path = _accept_generated_direction(run)
    accepted = json.loads(accepted_path.read_text(encoding="utf-8"))
    accepted["style"] = "A different valid style"
    accepted_path.write_text(json.dumps(accepted), encoding="utf-8")

    with pytest.raises(vd.VoiceDirectionError, match="candidate"):
        vd.load_voice_direction(run, SCRIPT, channel_id="history")


def test_accepted_generated_direction_rejects_stale_profile_voice(run):
    _accept_generated_direction(run)
    brief_path = run / "episode_brief.json"
    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    brief["channel"]["voice"] = "Achird"
    brief["profile_sha256"] = fingerprint(brief["channel"])
    brief_path.write_text(json.dumps(brief), encoding="utf-8")
    writing_receipt_path = run / "adaptive_writing_receipt.json"
    writing_receipt = json.loads(writing_receipt_path.read_text(encoding="utf-8"))
    writing_receipt["brief_sha256"] = narration_fingerprint(Brief.model_validate(brief))
    writing_receipt_path.write_text(json.dumps(writing_receipt), encoding="utf-8")

    with pytest.raises(vd.VoiceDirectionError, match="candidate|provenance|stale"):
        vd.load_voice_direction(run, SCRIPT, channel_id="history")


def test_generated_direction_cannot_fall_back_to_manual_when_provenance_is_removed(run):
    accepted_path = _accept_generated_direction(run)
    accepted = json.loads(accepted_path.read_text(encoding="utf-8"))
    accepted.pop("provenance")
    accepted_path.write_text(json.dumps(accepted), encoding="utf-8")

    with pytest.raises(vd.VoiceDirectionError, match="candidate|provenance|automated"):
        vd.load_voice_direction(run, SCRIPT, channel_id="history")


@pytest.mark.parametrize("damage", ["deleted", "byte_modified"])
def test_accepted_generated_direction_requires_current_candidate_bytes(run, damage):
    _accept_generated_direction(run)
    candidate_path = run / ds.CANDIDATE_FILE
    if damage == "deleted":
        candidate_path.unlink()
    else:
        candidate_path.write_bytes(candidate_path.read_bytes() + b" ")

    with pytest.raises(vd.VoiceDirectionError, match="candidate"):
        vd.load_voice_direction(run, SCRIPT, channel_id="history")
