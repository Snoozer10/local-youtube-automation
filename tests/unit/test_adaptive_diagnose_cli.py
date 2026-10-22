"""Offline adaptive diagnose CLI uses bounded local evidence before production setup."""

import json

import pytest

from youtube_automation.core import failure_record
from youtube_automation.production import cli


@pytest.fixture(autouse=True)
def forbid_production_setup(monkeypatch):
    from youtube_automation.browser import network_health

    def forbidden(*_args, **_kwargs):
        pytest.fail("diagnose must not initialize production, ledger, browser, network or audio")

    for name in (
        "resource_database", "Ledger", "_run_stage_attempt", "_execute_stage",
        "_stage_recipe", "_stage_complete", "gemini_transport", "leased_resource",
    ):
        monkeypatch.setattr(cli, name, forbidden)
    monkeypatch.setattr(network_health, "require_healthy", forbidden)


def _record(message, *, stage="plan"):
    return {
        "stage": stage, "utc": "2026-10-15T00:00:00Z", "layer": "test",
        "kind": "runtime", "exception": "RuntimeError", "message": message,
        "frame": None, "sends_spent": 0, "known_issue": None, "evidence": [],
    }


@pytest.mark.parametrize("state", ["missing", "empty"])
def test_diagnose_last_without_run_directory_reads_empty_state(tmp_path, capsys, state):
    path = tmp_path / "failures.jsonl"
    if state == "empty":
        path.write_bytes(b"")
    cli.main(["diagnose", "--last", "--path", str(path)])
    assert capsys.readouterr().out == "No failure records.\n"
    assert not (tmp_path / "jobs.db").exists()


def test_diagnose_last_prints_only_current_bounded_tail_without_writes(tmp_path, capsys):
    path = tmp_path / "failures.jsonl"
    old = json.dumps(_record("obsolete failure"))
    current = json.dumps(_record("current bounded failure"))
    path.write_bytes(("x" * 70_000 + "\n" + old + "\n" + current + "\n").encode("utf-8"))
    before = path.read_bytes()
    cli.main(["diagnose", "--last", "--path", str(path)])
    output = capsys.readouterr().out
    assert "current bounded failure" in output
    assert "obsolete failure" not in output
    assert "sends spent: 0" in output
    assert path.read_bytes() == before
    assert len(output.splitlines()) <= 60


def test_diagnose_last_uses_existing_failure_path_environment(tmp_path, monkeypatch, capsys):
    path = tmp_path / "failures.jsonl"
    path.write_text(json.dumps(_record("configured latest failure")) + "\n", encoding="utf-8")
    monkeypatch.setenv(failure_record.FAILURES_PATH_ENV, str(path))
    cli.main(["diagnose", "--last"])
    assert "configured latest failure" in capsys.readouterr().out


def test_diagnose_last_does_not_substitute_old_record_for_malformed_latest(tmp_path, capsys):
    path = tmp_path / "failures.jsonl"
    path.write_text(json.dumps(_record("old failure")) + "\n{broken\n", encoding="utf-8")
    cli.main(["diagnose", "--last", "--path", str(path)])
    assert capsys.readouterr().out == "No failure records.\n"


def test_diagnose_requires_explicit_last():
    with pytest.raises(SystemExit) as caught:
        cli.main(["diagnose"])
    assert caught.value.code == 2


@pytest.mark.parametrize("stage", ["analyze", "generate-direction", "source-audio", "status"])
def test_existing_production_stages_still_require_explicit_run_directory(stage):
    with pytest.raises(SystemExit) as caught:
        cli.main([stage])
    assert caught.value.code == 2


@pytest.mark.parametrize("option", [["--last"], ["--path", "unused.jsonl"]])
def test_diagnostic_options_rejected_for_production_stages(tmp_path, option):
    with pytest.raises(SystemExit) as caught:
        cli.main(["status", "--run-dir", str(tmp_path), *option])
    assert caught.value.code == 2


def test_diagnose_last_redacts_credentials_from_loaded_historical_record(tmp_path, capsys):
    path = tmp_path / "failures.jsonl"
    record = _record("Authorization: Bearer fake-loaded-secret")
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    before = path.read_bytes()
    cli.main(["diagnose", "--last", "--path", str(path)])
    output = capsys.readouterr().out
    assert "fake-loaded-secret" not in output
    assert "RuntimeError" in output
    assert path.read_bytes() == before
