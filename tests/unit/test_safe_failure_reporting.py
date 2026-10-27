"""Comprehensive tests for safe ledger failure summaries and historical diagnostic display.

Validates Issue #54 acceptance criteria:
AC 1: Safe terminal summary projection (no canaries, prompts, scripts in SQLite, JSONL, CLI).
AC 2: Non-regex authorization (value validation / allowlisted projection).
AC 3: Historical diagnostic protection without mutating source files.
AC 4: Operational transparency (timeouts, HTTP status codes, leases, circuits remain actionable).
AC 5: Traceback and original exception preservation in Python runtime.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from youtube_automation.core import failure_record as fr
from youtube_automation.production.cli import main as cli_main
from youtube_automation.production.ledger import Ledger, durable_stage


def test_durable_stage_omits_canaries_and_prose_from_sqlite_and_jsonl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC 1 & AC 2 & AC 5: Canaries and prompt prose are excluded from SQLite and JSONL, while original exc propagates."""
    jsonl_path = tmp_path / "failures.jsonl"
    db_path = tmp_path / "ledger.sqlite3"
    monkeypatch.setenv(fr.FAILURES_PATH_ENV, str(jsonl_path))

    canary_message = (
        "CANARY_PROMPT_99: Write a full script for YouTube narration. "
        "نص سري للغاية للكاناري "
        "def private_logic(): return 'classified' "
        "Authorization: Bearer secret-canary-token "
        "password=super-secret-password-12345"
    )

    original_exc = RuntimeError(canary_message)

    with pytest.raises(RuntimeError) as caught:
        with durable_stage(
            db_path,
            "stage:run_1:write",
            "recipe_v1",
            detail={
                "stage": "write",
                "run": str(tmp_path / "run_1"),
                "unauthorized_private_prompt": "private prompt body نص سري",
                "canary_field": "CANARY_VAL",
            },
        ) as execute:
            assert execute is True
            raise original_exc

    # AC 5: Original exception and its exact message and traceback propagate untouched
    assert caught.value is original_exc
    assert str(caught.value) == canary_message
    assert caught.value.__traceback__ is not None

    # Inspect SQLite jobs and events
    ledger = Ledger(db_path)
    jobs = ledger.status()
    assert len(jobs) == 1
    job = jobs[0]
    assert job["state"] == "FAILED"
    job_detail = json.loads(job["detail"])

    with ledger.connection() as conn:
        events = [dict(row) for row in conn.execute("SELECT * FROM events ORDER BY id")]
    assert len(events) >= 2  # RUNNING and FAILED
    failed_event = events[-1]
    assert failed_event["state"] == "FAILED"
    event_detail = json.loads(failed_event["detail"])

    # Inspect companion failures.jsonl
    assert jsonl_path.is_file()
    raw_jsonl_bytes = jsonl_path.read_bytes()
    raw_jsonl_text = raw_jsonl_bytes.decode("utf-8")
    records = fr.load_records(jsonl_path)
    assert len(records) == 1
    record = records[0]

    # Verify CANARIES are ABSENT from SQLite details and JSONL
    for target_text in (
        json.dumps(job_detail),
        json.dumps(event_detail),
        raw_jsonl_text,
    ):
        assert "CANARY_PROMPT_99" not in target_text
        assert "نص سري" not in target_text
        assert "private_logic" not in target_text
        assert "secret-canary-token" not in target_text
        assert "super-secret-password-12345" not in target_text
        assert "unauthorized_private_prompt" not in target_text
        assert "CANARY_VAL" not in target_text

    # Verify authorized diagnostic identity fields SURVIVE
    assert job_detail["stage"] == "write"
    assert job_detail["layer"] in {"code", "unknown"}
    assert job_detail["kind"] in {"code", "unknown"}
    assert job_detail["exception"] == "RuntimeError"
    assert "error" in job_detail
    assert "RuntimeError" in job_detail["error"]
    assert job_detail["run"] == "<external-path>"

    assert event_detail["stage"] == "write"
    assert event_detail["error"] == job_detail["error"]

    assert record["stage"] == "write"
    assert record["exception"] == "RuntimeError"
    assert record["run_dir"] == "<external-path>"
    assert record["message"] == job_detail["error"]


def test_cli_diagnose_last_safely_projects_without_leaking_canaries(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC 1 & AC 3: diagnose --last safely projects failures on console without leaking canaries."""
    path = tmp_path / "failures.jsonl"
    record = fr.build_record(
        RuntimeError("CANARY_PROMPT_FAIL: script draft نص سري token=secret123"),
        stage="write",
        run_dir=tmp_path / "run_dir",
    )
    fr.append_record(record, path)
    before_bytes = path.read_bytes()

    # CLI diagnose --last
    cli_main(["diagnose", "--last", "--path", str(path)])
    output = capsys.readouterr().out

    assert "CANARY" not in output
    assert "نص سري" not in output
    assert "script draft" not in output
    assert "secret123" not in output
    assert "stage: write" in output
    assert "RuntimeError" in output
    assert path.read_bytes() == before_bytes


def test_historical_record_safe_projection_preserves_file_bytes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC 3: Existing historical file containing raw canaries is safely projected in memory without mutating disk bytes."""
    path = tmp_path / "legacy_historical.jsonl"
    historical_raw_record = {
        "stage": "generate",
        "utc": "2026-10-20T12:00:00Z",
        "layer": "code",
        "kind": "code",
        "exception": "RuntimeError",
        "message": "Historical prompt canary: نص سري للغاية def secret(): return 'leaked'",
        "extra": {"canary_extra": "نص سري"},
    }
    raw_bytes = (json.dumps(historical_raw_record, ensure_ascii=False) + "\n").encode("utf-8")
    path.write_bytes(raw_bytes)

    # 1. Test load_records
    loaded_records = fr.load_records(path)
    assert len(loaded_records) == 1
    loaded = loaded_records[0]
    assert "نص سري" not in loaded["message"]
    assert "secret():" not in loaded["message"]
    assert "RuntimeError" in loaded["message"]

    # 2. Test load_last_record
    last = fr.load_last_record(path)
    assert last is not None
    assert "نص سري" not in last["message"]
    assert "secret():" not in last["message"]

    # 3. Test digest
    digest_text = fr.digest(historical_raw_record)
    assert "نص سري" not in digest_text
    assert "secret():" not in digest_text
    assert "RuntimeError" in digest_text

    # 4. Test CLI diagnose --last
    cli_main(["diagnose", "--last", "--path", str(path)])
    cli_output = capsys.readouterr().out
    assert "نص سري" not in cli_output
    assert "secret():" not in cli_output
    assert "RuntimeError" in cli_output

    # Crucial assertion: The file on disk was NOT modified at all
    assert path.read_bytes() == raw_bytes


@pytest.mark.parametrize(
    ("exc_type", "message", "expected_fragment"),
    [
        (TimeoutError, "BrowserType.connect_over_cdp: Timeout 180000ms exceeded", "connect_over_cdp"),
        (TimeoutError, "Page.goto: Timeout 30000ms exceeded", "Page.goto"),
        (RuntimeError, "Resource lease renewal failed", "Resource lease renewal failed"),
        (RuntimeError, "Lost production lease", "Lost production lease"),
        (RuntimeError, "Stage circuit is open after 3 failed attempts: stage:run:generate", "Stage circuit is open"),
        (RuntimeError, "TTS attempt ceiling reached", "TTS attempt ceiling reached"),
        (RuntimeError, "Existing voice chapters have no matching adaptive recipe", "matching adaptive recipe"),
        (RuntimeError, "AI Studio banner Http response at 400 or 500 level, http status code: 0", "http status code: 0"),
    ],
)
def test_operational_transparency_preserves_legitimate_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exc_type: type[BaseException],
    message: str,
    expected_fragment: str,
) -> None:
    """AC 4: Operational failures (timeouts, HTTP status, leases, circuits) remain actionable and clear."""
    db_path = tmp_path / "ledger.sqlite3"
    jsonl_path = tmp_path / "failures.jsonl"
    monkeypatch.setenv(fr.FAILURES_PATH_ENV, str(jsonl_path))

    with pytest.raises(exc_type):
        with durable_stage(
            db_path,
            "stage:test:operational",
            "recipe_op",
            detail={"stage": "operational", "run": str(tmp_path / "run")},
        ) as execute:
            assert execute is True
            raise exc_type(message)

    # Check SQLite detail
    ledger = Ledger(db_path)
    job = ledger.status()[0]
    detail = json.loads(job["detail"])
    assert expected_fragment in detail["error"]

    # Check failures.jsonl
    rec = fr.load_last_record(jsonl_path)
    assert rec is not None
    assert expected_fragment in rec["message"]

    # Check digest
    digest_text = fr.digest(rec)
    assert expected_fragment in digest_text
