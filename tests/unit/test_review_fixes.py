"""Regressions for the 2026-10-09 independent review of the resilience and accepted-original changes."""

import json
from types import SimpleNamespace

import pytest

from youtube_automation.browser import network_health, ui_guard
from youtube_automation.production import briefs, cli, writing
from youtube_automation.production.briefs import ensure_brief
from youtube_automation.production.contracts import Channel, fingerprint

RAW = "First accepted paragraph.\n\nSecond accepted paragraph.\n"


def _accepted_run(tmp_path, *, bom=False):
    channel = Channel(
        channel_id="review-test",
        name="Review Test",
        audience="adults",
        language="English",
        dialect="neutral",
        voice="Charon",
        tone="serious",
        style="illustration",
        humor="none",
        allowed_treatments=["subject_scene"],
    )
    (tmp_path / "raw_transcript.txt").write_bytes(RAW.encode("utf-8"))
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
        "script_sha256": fingerprint(RAW),
        "accepted_by": "reviewer",
        "statement": "ACCEPTED",
    }
    data = json.dumps(acceptance).encode("utf-8")
    (tmp_path / writing.SCRIPT_ACCEPTANCE_FILE).write_bytes((b"\xef\xbb\xbf" if bom else b"") + data)
    return brief


def test_gemini_network_gate_runs_before_the_send_guarded_request(monkeypatch):
    order = []
    monkeypatch.setattr(network_health, "require_healthy", lambda url: order.append(("gate", url)))
    monkeypatch.setattr(
        briefs.BrowserTransport,
        "_request",
        lambda self, prompt, *, use_file: order.append(("request", use_file)) or "answer",
    )
    transport = object.__new__(briefs.BrowserTransport)
    transport.attachment_mode = "inline"
    assert transport("prompt") == "answer"
    assert order == [("gate", network_health.GEMINI_URL), ("request", False)]


def test_accepted_publication_refuses_a_pending_model_journal(tmp_path):
    brief = _accepted_run(tmp_path)
    journal = tmp_path / ".publication_journal" / "writing.json"
    journal.parent.mkdir()
    journal.write_text(
        json.dumps({"version": 1, "kind": "writing", "outputs": {}, "receipt": {"version": 1}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="pending non-accepted"):
        writing.publish_accepted_original(tmp_path, brief)
    assert not (tmp_path / "refined_script.txt").exists()


def test_acceptance_file_with_a_byte_order_mark_is_accepted(tmp_path):
    brief = _accepted_run(tmp_path, bom=True)
    receipt = writing.publish_accepted_original(tmp_path, brief)
    assert receipt["mode"] == writing.ACCEPTED_ORIGINAL_MODE
    assert writing.verify_written_episode(tmp_path)


def test_cli_write_publishes_an_accepted_script_without_browser_or_model(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "gemini_transport", lambda **_k: pytest.fail("no Gemini page"))
    monkeypatch.setattr(cli, "leased_resource", lambda *_a: pytest.fail("no browser lease"))
    monkeypatch.setattr(cli, "load_brief", lambda root: ("brief", root))
    monkeypatch.setattr(writing, "publish_accepted_original", lambda root, brief: calls.append(brief))
    (tmp_path / "script_acceptance.json").write_text("{}", encoding="utf-8")
    cli._execute_stage(SimpleNamespace(stage="write"), tmp_path, tmp_path / "db.sqlite3")
    assert calls == [("brief", tmp_path)]


def test_cli_skips_the_network_gate_for_an_accepted_write(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(network_health, "require_healthy", lambda _url: pytest.fail("no gate"))
    monkeypatch.setattr(cli, "_stage_complete", lambda _root, _args: False)
    monkeypatch.setattr(cli, "_run_stage_attempt", lambda *_a: calls.append("stage"))
    (tmp_path / "script_acceptance.json").write_text("{}", encoding="utf-8")
    cli.main(["write", "--run-dir", str(tmp_path)])
    assert calls == ["stage"]


def test_malformed_wait_limit_falls_back_to_the_default(monkeypatch):
    monkeypatch.setenv("NETWORK_HEALTH_GATE", "1")
    monkeypatch.setenv("NETWORK_MAX_WAIT_SECONDS", "fifteen minutes")
    healthy = network_health.NetworkProbe(True, 0.2, 0.5, 40_000, "ok")
    result = network_health.require_healthy(
        network_health.GEMINI_URL,
        probe_fn=lambda _url: healthy,
        sleep=lambda _s: None,
        clock=lambda: 0.0,
        log=lambda _line: None,
    )
    assert result is healthy


@pytest.mark.parametrize("label", ["ok", "okay", "done"])
def test_ambiguous_confirm_labels_are_not_safe_dismiss_labels(label):
    assert label not in ui_guard.SAFE_LABELS
