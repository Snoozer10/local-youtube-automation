import importlib.util
import json
from pathlib import Path

import pytest

from youtube_automation.core import failure_record as fr

ROOT = Path(__file__).resolve().parents[2]


def _exc(name, msg="boom", base=Exception):
    return type(name, (base,), {})(msg)


@pytest.mark.parametrize(
    ("name", "msg", "layer"),
    [
        ("TTSProviderError", "x", "provider"),
        ("GeminiUsageLimitError", "x", "provider"),
        ("NetworkDegradedError", "slow", "network"),
        ("URLError", "x", "network"),
        ("TTSWorkspaceUnavailableError", "x", "browser.ui"),
        ("RuntimeError", "BrowserType.connect_over_cdp: Timeout", "browser.cdp"),
        ("RuntimeError", "TTS attempt ceiling reached", "budget"),
        ("ValidationError", "bad", "contract"),
        ("RuntimeError", "plain", "unknown"),
    ],
)
def test_classify_layer(name, msg, layer):
    assert fr.classify_layer(_exc(name, msg), "s") == layer


def test_error_kind():
    assert fr.error_kind(_exc("X", "b"), "budget") == "budget"
    assert fr.error_kind(_exc("NetworkDegradedError", "slow"), "network") == "transient"


def test_innermost_frame_and_code_layer(monkeypatch, tmp_path):
    try:
        raise ValueError("x")
    except ValueError as exc:
        assert fr.innermost_project_frame(exc) is None  # tests/unit is not src/ or .runtime/
        assert fr.classify_layer(exc, "s", {"file": "src/a.py", "line": 1, "function": "f"}) == "code"

    checkout = tmp_path / "checkout"
    source = checkout / "src" / "pkg" / "mod.py"
    runtime = checkout / ".runtime" / "failure.py"
    outside_source = tmp_path / "neighbor" / "src" / "mod.py"
    outside_runtime = tmp_path / "neighbor-runtime" / ".runtime" / "failure.py"
    for path in (source, runtime, outside_source, outside_runtime):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# fixture\n", encoding="utf-8")

    monkeypatch.setattr(fr, "_repo_root", lambda: checkout)
    assert fr._rel_frame_path(str(source)) == "src/pkg/mod.py"
    assert fr._rel_frame_path(str(runtime)) == ".runtime/failure.py"
    assert fr._rel_frame_path(str(outside_source)) is None
    assert fr._rel_frame_path(str(outside_runtime)) is None
    outside_cwd = tmp_path / "outside-cwd"
    outside_cwd.mkdir()
    monkeypatch.chdir(outside_cwd)
    assert fr._rel_frame_path("src/pkg/mod.py") == "src/pkg/mod.py"
    assert fr._rel_frame_path(".runtime/failure.py") == ".runtime/failure.py"
    assert fr._rel_frame_path("../neighbor/src/mod.py") is None
    assert fr._rel_frame_path(str(checkout / ".." / "neighbor" / "src" / "mod.py")) is None

def test_redaction_and_truncation():
    msg = "GET https://x.test/a?token=abc123&k=1 mail me@example.com cookie: SID=zz " + "w " * 400
    rec = fr.build_record(RuntimeError(msg), stage="s")
    assert "abc123" not in rec["message"] and "me@example.com" not in rec["message"]
    assert "SID=zz" not in rec["message"] and len(rec["message"]) <= 300


SAMPLES = {
    "CDP-ATTACH-HANG": (
        "TimeoutError",
        "BrowserType.connect_over_cdp: Timeout 180000ms exceeded",
        None,
    ),
    "VOICE-RECIPE-NEWLINES": (
        "RuntimeError",
        "Existing voice chapters have no matching adaptive recipe",
        None,
    ),
    "AISTUDIO-OVERLAY": (
        "TTSWorkspaceUnavailableError",
        "cdk-overlay-container subtree intercepts pointer events",
        None,
    ),
    "AISTUDIO-STATUS-0": (
        "TTSProviderError",
        "AI Studio banner Http response at 400 or 500 level, http status code: 0",
        None,
    ),
    "NETWORK-DEGRADED": (
        "NetworkDegradedError",
        "proxy path timed out during the diagnostic",
        None,
    ),
    "TTS-CEILING": (
        "RuntimeError",
        "TTS attempt ceiling reached",
        None,
    ),
    "IMPORT-DURING-EDIT": (
        "SyntaxError",
        "invalid syntax",
        ROOT / "src" / "youtube_automation" / "production" / "writing.py",
    ),
}


@pytest.mark.parametrize("issue_id", sorted(SAMPLES))
def test_known_issue_matching(issue_id):
    name, msg, frame_path = SAMPLES[issue_id]
    frame = (
        {"file": str(frame_path), "line": 12, "function": "stage"}
        if frame_path is not None
        else None
    )
    rec = fr.build_record(_exc(name, msg), stage="s", frame=frame)
    assert rec["known_issue"]["id"] == issue_id
    assert rec["known_issue"]["observed_signature"]
    assert rec["known_issue"]["cause_status"] in {"observed", "hypothesis"}
    assert rec["known_issue"]["confidence"] in {"low", "medium", "high"}

def test_known_issue_false_positive_boundaries():
    issues = {issue["id"]: issue for issue in fr._load_issues()}
    cases = [
        ("CDP-ATTACH-HANG", {"exception": "RuntimeError", "message": "Page.goto: Timeout", "layer": "browser.cdp"}),
        ("AISTUDIO-OVERLAY", {"exception": "TTSWorkspaceUnavailableError", "message": "Locator.click: Timeout", "layer": "browser.ui"}),
        ("AISTUDIO-STATUS-0", {"exception": "TTSProviderError", "message": "http status code: 500", "layer": "provider"}),
        ("NETWORK-DEGRADED", {"exception": "TimeoutError", "message": "Page.goto: Timeout", "layer": "network"}),
        ("TTS-CEILING", {"exception": "RuntimeError", "message": "generic attempt ceiling reached", "layer": "budget"}),
        ("IMPORT-DURING-EDIT", {"exception": "SyntaxError", "message": "invalid syntax", "layer": "code", "frame": {"file": "src/youtube_automation/production/cli.py"}}),
    ]
    for issue_id, record in cases:
        assert fr.match_known_issue(record, [issues[issue_id]]) is None


def test_build_record_redacts_and_bounds_context(tmp_path):
    record = fr.build_record(
        RuntimeError("token=secret"),
        stage="plan user@example.com",
        run_dir=tmp_path,
        evidence=[tmp_path / f"evidence-{index}.json" for index in range(20)],
        extra={f"key-{index}": "x" * 500 for index in range(20)},
        frame={"file": str(tmp_path / "private.py"), "line": 3, "function": "private"},
    )
    assert record["stage"] == "plan [email]"
    assert record["run_dir"] == "<external-path>"
    assert record["frame"] is None
    assert record["evidence"] == ["<external-path>"]
    assert len(record["extra"]) == 10
    assert len(json.dumps(record, ensure_ascii=False).encode("utf-8")) <= 16_384


def test_load_last_record_reads_bounded_tail(tmp_path):
    path = tmp_path / "failures.jsonl"
    old = json.dumps({"stage": "old"}) + "\n"
    latest = json.dumps({"stage": "latest"}) + "\n"
    path.write_bytes((old + ("x" * 70_000) + "\n" + latest).encode("utf-8"))
    assert fr.load_last_record(path) == {"stage": "latest"}


def test_load_last_record_rejects_truncated_latest_record(tmp_path):
    path = tmp_path / "failures.jsonl"
    path.write_bytes((json.dumps({"stage": "old"}) + "\n" + ("x" * 70_000)).encode())
    assert fr.load_last_record(path) is None


def test_durable_stage_records_nested_failure_once(tmp_path, monkeypatch):
    path = tmp_path / "failures.jsonl"
    monkeypatch.setenv(fr.FAILURES_PATH_ENV, str(path))
    from youtube_automation.production.ledger import durable_stage

    error = RuntimeError("stage failed")
    with pytest.raises(RuntimeError) as caught:
        with durable_stage(
            tmp_path / "ledger.sqlite3",
            "stage:test:plan",
            "recipe",
            detail={"stage": "plan", "run": str(tmp_path / "run")},
        ) as execute:
            assert execute
            with fr.capture("nested"):
                raise error
    assert caught.value is error
    records = fr.load_records(path)
    assert len(records) == 1
    assert records[0]["stage"] == "plan"
    assert records[0]["run_dir"] == "<external-path>"


def test_capture_appends_one_and_reraises(tmp_path, monkeypatch):
    path = tmp_path / "f.jsonl"
    monkeypatch.setenv(fr.FAILURES_PATH_ENV, str(path))
    error = RuntimeError("TTS attempt ceiling reached")
    with pytest.raises(RuntimeError, match="ceiling") as raised:
        with fr.capture("tts", sends_spent=3):
            raise error
    assert raised.value is error
    frames = []
    tb = error.__traceback__
    while tb is not None:
        frames.append(tb.tb_frame.f_code.co_name)
        tb = tb.tb_next
    assert "test_capture_appends_one_and_reraises" in frames
    recs = fr.load_records(path)
    assert len(recs) == 1 and recs[0]["known_issue"]["id"] == "TTS-CEILING"
    assert recs[0]["sends_spent"] == 3


def test_capture_survives_unwritable_path(tmp_path, monkeypatch):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setenv(fr.FAILURES_PATH_ENV, str(blocker / "sub" / "f.jsonl"))
    with pytest.raises(KeyError):
        with fr.capture("s"):
            raise KeyError("k")


def test_digest_bounded():
    rec = fr.build_record(
        RuntimeError("x"), stage="s", evidence=[f"p{i}" for i in range(200)], extra={"a": 1}
    )
    assert len(fr.digest(rec).splitlines()) <= 60


def _cli():
    path = ROOT / "tools" / "diagnose_failures.py"
    spec = importlib.util.spec_from_file_location("diagnose_failures", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cli_log_mode(tmp_path, capsys):
    log = tmp_path / "run.log"
    log.write_text(
        "noise\nTraceback (most recent call last):\n"
        f'  File "{ROOT.as_posix()}/src/youtube_automation/audio/tts_generator.py", line 10, in send\n'
        "    raise RuntimeError\n"
        "RuntimeError: TTS attempt ceiling reached\n",
        encoding="utf-8",
    )
    assert _cli().main(["--log", str(log), "--stage", "tts"]) == 0
    out = capsys.readouterr().out
    assert "TTS-CEILING" in out and "tts_generator.py:10 send" in out


def test_cli_last_empty(tmp_path, capsys):
    assert _cli().main(["--last", "--path", str(tmp_path / "none.jsonl")]) == 0
    assert "No failure records." in capsys.readouterr().out


def test_cli_json(tmp_path, capsys):
    path = tmp_path / "f.jsonl"
    fr.append_record(fr.build_record(RuntimeError("a"), stage="s"), path)
    _cli().main(["--json", "--path", str(path)])
    assert json.loads(capsys.readouterr().out)["stage"] == "s"



def test_redacts_complete_auth_and_cookie_headers_from_saved_and_read_records(
    tmp_path, monkeypatch
):
    path = tmp_path / "failures.jsonl"
    monkeypatch.setenv(fr.FAILURES_PATH_ENV, str(path))
    messages = (
        "HTTP/1.1 401 Unauthorized\\nAuthorization: Bearer fake-bearer-secret",
        "Proxy-Authorization: Basic fake-basic-secret",
        '{"Authorization":"Bearer fake-json-bearer-secret",'
        '"Cookie":"sid=fake-json-cookie-secret"}',
        "Cookie: sid=fake-header-cookie-secret\\n"
        "Set-Cookie: session=fake-set-cookie-secret; HttpOnly; Secure",
    )
    secrets = (
        "fake-bearer-secret",
        "fake-basic-secret",
        "fake-json-bearer-secret",
        "fake-json-cookie-secret",
        "fake-header-cookie-secret",
        "fake-set-cookie-secret",
    )

    for message in messages:
        try:
            with fr.capture("redaction-test"):
                raise RuntimeError(message)
        except RuntimeError:
            pass
        else:
            raise AssertionError("capture must preserve the original exception")

    raw = path.read_text(encoding="utf-8")
    records = fr.load_records(path)
    latest = fr.load_last_record(path)
    exposed = raw + repr(records) + repr(latest) + fr.digest(latest)
    for secret in secrets:
        assert secret not in exposed


def test_cli_last_uses_bounded_loader(monkeypatch, tmp_path, capsys):
    cli = _cli()
    target = tmp_path / "large.jsonl"
    expected = {"stage": "latest"}
    calls = []

    def load_last(path):
        calls.append(path)
        return expected

    def reject_full_load(_path):
        raise AssertionError("--last must not load the full JSONL file")

    monkeypatch.setattr(cli.fr, "load_last_record", load_last)
    monkeypatch.setattr(cli.fr, "load_records", reject_full_load)
    monkeypatch.setattr(cli.fr, "digest", lambda _record: "latest-record-digest")

    assert cli.main(["--last", "--path", str(target)]) == 0
    assert calls == [str(target)]
    assert "latest-record-digest" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("header", "label_quote", "value_quote"),
    [
        (header, label_quote, value_quote)
        for header in (
            "Authorization",
            "Proxy-Authorization",
            "Cookie",
            "Set-Cookie",
        )
        for label_quote in ("", '"', "'")
        for value_quote in ("", '"', "'")
    ],
)
def test_cli_redacts_loaded_long_quoted_header_without_changing_bytes(
    tmp_path, capsys, header, label_quote, value_quote
):
    path = tmp_path / "long-auth.jsonl"
    secret = "s" * 5000
    if header in ("Authorization", "Proxy-Authorization"):
        value = f"Bearer {secret}"
    else:
        value = f"session={secret}"
    record = {
        "stage": "plan",
        "exception": "RuntimeError",
        "message": f"{label_quote}{header}{label_quote}: {value_quote}{value}{value_quote}",
    }
    raw = (json.dumps(record) + "\n").encode("utf-8")
    path.write_bytes(raw)
    cli = _cli()

    assert cli.main(["--path", str(path), "--last"]) == 0
    text_output = capsys.readouterr().out
    assert "s" * 32 not in text_output
    assert "[redacted]" in text_output.lower()
    assert path.read_bytes() == raw

    assert cli.main(["--path", str(path), "--last", "--json"]) == 0
    json_output = capsys.readouterr().out
    loaded = json.loads(json_output)
    assert len(loaded["message"]) <= 4096
    assert "s" * 32 not in json_output
    assert "[redacted]" in loaded["message"].lower()
    assert path.read_bytes() == raw


def test_cli_json_scrubs_loaded_legacy_record_without_changing_bytes(tmp_path, capsys):
    path = tmp_path / "legacy.jsonl"
    record = {
        "stage": "plan", "exception": "RuntimeError", "sends_spent": 1,
        "message": "Authorization: Bearer fake-legacy-message-secret",
        "headers": {
            "Authorization": "Bearer fake-header-secret",
            "Cookie": "sid=fake-cookie-secret",
            "X-Custom": "fake-other-header-value",
        },
        "context": {"api_key": "fake-structured-key-secret", "retry": 0, "enabled": True},
    }
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    before = path.read_bytes()
    assert _cli().main(["--last", "--json", "--path", str(path)]) == 0
    text = capsys.readouterr().out
    for secret in (
        "fake-legacy-message-secret", "fake-header-secret", "fake-cookie-secret",
        "fake-other-header-value", "fake-structured-key-secret",
    ):
        assert secret not in text
    shown = json.loads(text)
    assert shown["stage"] == "plan"
    assert shown["sends_spent"] == 1
    assert shown["context"]["retry"] == 0
    assert shown["context"]["enabled"] is True
    assert all(value == "[redacted]" for value in shown["headers"].values())
    assert path.read_bytes() == before


def test_sanitize_record_copies_and_bounds_keys_values_and_collections():
    record = {
        "stage": "audio", "sends_spent": 0, "enabled": False, "value": None,
        "large": ["x" * 5000 for _ in range(100)],
        "k" * 1000: "Authorization: Bearer fake-value-secret",
    }
    before = json.dumps(record)
    result = fr.sanitize_record(record)
    assert json.dumps(record) == before
    assert result["stage"] == "audio"
    assert result["sends_spent"] == 0 and result["enabled"] is False
    assert result["value"] is None
    assert len(result["large"]) == 64
    assert all(len(value) <= 300 for value in result["large"])
    assert max(map(len, result)) <= 80
    assert "fake-value-secret" not in json.dumps(result)


def test_sanitize_record_bounds_recursion_and_total_nodes():
    deep = "never-render-this-deep-value"
    for _ in range(30):
        deep = {"child": deep}
    bounded_deep = fr.sanitize_record({"context": deep})
    assert "[truncated]" in json.dumps(bounded_deep)
    assert "never-render-this-deep-value" not in json.dumps(bounded_deep)
    wide = {f"group{index}": [{"Authorization": "secret"} for _ in range(64)] for index in range(64)}
    bounded = fr.sanitize_record(wide)

    def count_nodes(value):
        if isinstance(value, dict):
            return 1 + sum(count_nodes(child) for child in value.values())
        if isinstance(value, list):
            return 1 + sum(count_nodes(child) for child in value)
        return 1

    assert count_nodes(bounded) <= 512
    assert "secret" not in json.dumps(bounded)

@pytest.mark.parametrize(
    ("assignment", "secret"),
    [
        ('password="fake password phrase"', "fake password phrase"),
        ("passwd='fake passwd phrase'", "fake passwd phrase"),
        ("secret=unquoted-secret-value", "unquoted-secret-value"),
        ('secret="fake malformed phrase with spaces', "fake malformed phrase with spaces"),
    ],
)
def test_redacts_credential_assignments_from_jsonl_and_last_cli(
    tmp_path, capsys, assignment, secret
):
    path = tmp_path / "assignment.jsonl"
    fr.append_record(fr.build_record(RuntimeError(assignment), stage="test"), path)
    saved = path.read_bytes()
    assert secret.encode() not in saved

    cli = _cli()
    assert cli.main(["--path", str(path), "--last"]) == 0
    assert secret not in capsys.readouterr().out
    assert cli.main(["--path", str(path), "--last", "--json"]) == 0
    assert secret not in capsys.readouterr().out


@pytest.mark.parametrize(
    ("key", "secret"),
    [
        ("password", "extra-password-secret"),
        ("passwd", "extra-passwd-secret"),
        ("Secret", "extra-secret-value"),
    ],
)
def test_redacts_sensitive_extra_keys_from_jsonl_and_last_cli(
    tmp_path, capsys, key, secret
):
    path = tmp_path / "extra.jsonl"
    record = fr.build_record(RuntimeError("failure"), stage="test", extra={key: secret})
    fr.append_record(record, path)
    saved = path.read_bytes()
    assert secret.encode() not in saved

    cli = _cli()
    assert cli.main(["--path", str(path), "--last"]) == 0
    assert secret not in capsys.readouterr().out
    assert cli.main(["--path", str(path), "--last", "--json"]) == 0
    output = capsys.readouterr().out
    assert secret not in output
    assert json.loads(output)["extra"]


def test_historical_known_issue_untrusted_signature_redacted():
    """F2: Untrusted historical known_issue free-text signature must be redacted and never projected."""
    secret = "Our acquisition target is Orion"
    raw = {
        "message": "failure",
        "exception": "RuntimeError",
        "known_issue": {
            "id": "example",
            "observed_signature": secret,
        },
    }
    sanitized = fr.sanitize_record(raw)
    assert secret not in sanitized["message"]
    assert secret not in sanitized["known_issue"]["observed_signature"]
    assert sanitized["message"] == "[example] Known issue matched"
    assert sanitized["known_issue"]["observed_signature"] == "[redacted]"
