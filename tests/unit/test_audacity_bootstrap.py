"""Offline tests for Audacity script-pipe configuration and owned startup."""

import pytest

from youtube_automation.audio import audacity_client


def test_config_enables_only_module_section_and_preserves_bytes(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    cfg = tmp_path / "audacity" / "audacity.cfg"
    original = (
        b"\xef\xbb\xbf[Other]\r\n"
        b"mod-script-pipe=1\r\n"
        b"; keep this comment\r\n"
        b"[Module]\r\n"
        b"; keep setting comment\r\n"
        b"mod-script-pipe = 4\r\n"
        b"[Modules]\r\n"
        b"unrelated=keep\r\n"
    )
    cfg.parent.mkdir()
    cfg.write_bytes(original)

    audacity_client.ensure_audacity_script_pipe_enabled()

    expected = original.replace(
        b"mod-script-pipe = 4",
        b"mod-script-pipe=1",
    )
    assert cfg.read_bytes() == expected
    audacity_client.ensure_audacity_script_pipe_enabled()
    assert cfg.read_bytes() == expected


@pytest.mark.parametrize(
    "contents",
    [
        b"[Module]\nmod-script-pipe=1\n[Module]\nmod-script-pipe=1\n",
        b"[Module]\nmod-script-pipe=1\nmod-script-pipe=4\n",
    ],
)
def test_config_rejects_duplicate_module_or_setting_without_writing(
    tmp_path, monkeypatch, contents
):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    cfg = tmp_path / "audacity" / "audacity.cfg"
    cfg.parent.mkdir()
    cfg.write_bytes(contents)

    with pytest.raises(RuntimeError, match="duplicate"):
        audacity_client.ensure_audacity_script_pipe_enabled()

    assert cfg.read_bytes() == contents


def test_config_rejects_unreadable_encoding_without_writing(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    cfg = tmp_path / "audacity" / "audacity.cfg"
    cfg.parent.mkdir()
    cfg.write_bytes(b"[Module]\n\xff\n")

    with pytest.raises(RuntimeError, match="UTF-8"):
        audacity_client.ensure_audacity_script_pipe_enabled()

    assert cfg.read_bytes() == b"[Module]\n\xff\n"


def test_config_fails_closed_without_appdata(monkeypatch):
    monkeypatch.delenv("APPDATA", raising=False)

    with pytest.raises(RuntimeError, match="APPDATA"):
        audacity_client.ensure_audacity_script_pipe_enabled()


def test_config_rejects_inline_comment_without_writing(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    cfg = tmp_path / "audacity" / "audacity.cfg"
    cfg.parent.mkdir()
    original = b"[Module]\nmod-script-pipe=4 ; ambiguous\n"
    cfg.write_bytes(original)

    with pytest.raises(RuntimeError, match="inline comment"):
        audacity_client.ensure_audacity_script_pipe_enabled()

    assert cfg.read_bytes() == original


class _FakeProcess:
    def __init__(self, *exit_codes):
        self.exit_codes = iter(exit_codes or (None,))

    def poll(self):
        return next(self.exit_codes, None)


class _FakePipe:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_pipe_startup_fails_immediately_when_owned_child_exits():
    calls = []
    process = _FakeProcess(19)

    def open_pipe(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("pipe must not be opened after child exit")

    with pytest.raises(RuntimeError, match="exit code 19"):
        audacity_client._open_audacity_pipes(process, pipe_opener=open_pipe)

    assert calls == []


def test_pipe_startup_polls_child_exit_during_retry_delay(monkeypatch):
    sleeps = []
    monkeypatch.setattr(
        audacity_client.time, "sleep", lambda seconds: sleeps.append(seconds)
    )
    process = _FakeProcess(None, None, 23)

    def open_pipe(*_args, **_kwargs):
        raise OSError("pipe not ready")

    with pytest.raises(RuntimeError, match="exit code 23"):
        audacity_client._open_audacity_pipes(process, pipe_opener=open_pipe)

    assert sleeps == [0.1]


def test_pipe_startup_closes_partial_handle_and_retries(monkeypatch):
    monkeypatch.setattr(audacity_client.time, "sleep", lambda _seconds: None)
    first_writer = _FakePipe()
    final_writer = _FakePipe()
    final_reader = _FakePipe()
    outcomes = iter([first_writer, OSError("reader unavailable"), final_writer, final_reader])

    def open_pipe(*_args, **_kwargs):
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    writer, reader = audacity_client._open_audacity_pipes(
        _FakeProcess(), pipe_opener=open_pipe
    )

    assert first_writer.closed
    assert writer is final_writer
    assert reader is final_reader
